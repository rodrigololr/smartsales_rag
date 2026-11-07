"""Pure RN01/RN04/RN05 eligibility and Decimal ranking.

Callers supply current SQL snapshots, verified compatibility and similarities
from active manual chunks. This module performs no retrieval or open generation
and does not build SSE cards or certify catalog freshness.
"""

from collections.abc import Sequence
from decimal import Decimal

from .models import (
    ONE,
    ZERO,
    Product,
    Recommendation,
    RecommendationCandidate,
    Voltage,
    validate_voltage,
)

UPSELL_MAX_PRICE_RATIO = Decimal("1.35")
UPSELL_MAX_PRICE_INCREASE = Decimal("0.35")
CROSS_SELL_MAX_PRICE_RATIO = Decimal("0.40")
UPSELL_SIMILARITY_WEIGHT = Decimal("0.50")
UPSELL_GAIN_WEIGHT = Decimal("0.30")
UPSELL_PRICE_WEIGHT = Decimal("0.20")
CROSS_RELATION_WEIGHT = Decimal("0.60")
CROSS_SIMILARITY_WEIGHT = Decimal("0.25")
CROSS_PRICE_WEIGHT = Decimal("0.15")
CATEGORY_AFFINITY = Decimal("0.50")
TIER_GAIN_SCALE = Decimal("4")


def _unit_interval(value: Decimal) -> Decimal:
    return min(ONE, max(ZERO, value))


def _similarity(candidate: RecommendationCandidate) -> Decimal:
    return _unit_interval(max(candidate.similarities, default=ZERO))


def _available(product: Product) -> bool:
    return product.is_active and product.stock_quantity > 0


def _voltage_matches(voltage: Voltage, preference: Voltage | None) -> bool:
    # N/A = unpowered product (cosmetic, accessory): any outlet preference fits it.
    return preference is None or voltage in (preference, "BIVOLT", "N/A")


def _resolved_voltage(base: Product, preference: Voltage | None) -> Voltage:
    if preference is not None:
        validate_voltage(preference)
    return base.voltage if preference is None else preference


def _gain(base: Product, candidate: Product) -> Decimal:
    if (
        base.capacity_liters is not None
        and base.capacity_liters > ZERO
        and candidate.capacity_liters is not None
        and candidate.capacity_liters > ZERO
    ):
        return _unit_interval(
            (candidate.capacity_liters - base.capacity_liters) / base.capacity_liters
        )
    return _unit_interval(Decimal(candidate.tier_rank - base.tier_rank) / TIER_GAIN_SCALE)


def _superior(base: Product, candidate: Product) -> bool:
    capacity_increases = (
        base.capacity_liters is not None
        and candidate.capacity_liters is not None
        and candidate.capacity_liters > base.capacity_liters
    )
    return candidate.tier_rank > base.tier_rank or capacity_increases


def _upsell_eligible(base: Product, candidate: Product, voltage: Voltage) -> bool:
    return (
        candidate.sku != base.sku
        and _available(candidate)
        and candidate.category == base.category
        and candidate.subcategory == base.subcategory
        and base.price < candidate.price <= base.price * UPSELL_MAX_PRICE_RATIO
        and _voltage_matches(candidate.voltage, voltage)
        and _superior(base, candidate)
    )


def _upsell_score(base: Product, candidate: RecommendationCandidate) -> Decimal:
    pricefit = _unit_interval(
        ONE - (candidate.product.price - base.price) / (UPSELL_MAX_PRICE_INCREASE * base.price)
    )
    return (
        UPSELL_SIMILARITY_WEIGHT * _similarity(candidate)
        + UPSELL_GAIN_WEIGHT * _gain(base, candidate.product)
        + UPSELL_PRICE_WEIGHT * pricefit
    )


def _affinity(base: Product, candidate: RecommendationCandidate) -> Decimal | None:
    proof = candidate.compatibility
    if proof is None or proof.base_sku != base.sku or proof.candidate_sku != candidate.product.sku:
        return None
    if proof.source == "COMPLEMENTARY_CATEGORY":
        return CATEGORY_AFFINITY
    return proof.affinity_weight


def _cross_eligible(base: Product, candidate: Product, voltage: Voltage) -> bool:
    return (
        candidate.sku != base.sku
        and _available(candidate)
        and candidate.price <= CROSS_SELL_MAX_PRICE_RATIO * base.price
        and _voltage_matches(candidate.voltage, voltage)
    )


def _cross_score(
    base: Product,
    candidate: RecommendationCandidate,
    affinity: Decimal,
) -> Decimal:
    pricefit = ONE - candidate.product.price / (CROSS_SELL_MAX_PRICE_RATIO * base.price)
    return (
        CROSS_RELATION_WEIGHT * affinity
        + CROSS_SIMILARITY_WEIGHT * _similarity(candidate)
        + CROSS_PRICE_WEIGHT * pricefit
    )


def _best(recommendations: Sequence[Recommendation]) -> Recommendation | None:
    return min(
        recommendations,
        key=lambda item: (-item.score, item.product.price, item.product.sku),
        default=None,
    )


class RecommendationEngine:
    """Select at most one item per role; no intent or technical-fact inference.

    An unavailable base is retained for comparison, never emitted as PRIMARY.
    If buying voltage is omitted, secondary offers must match the base voltage.
    N/A accessories remain eligible only with supplied physical compatibility.
    Pass allow_upsell=False for a direct-purchase/technical-question-only turn.
    """

    def select_upsell(
        self,
        base: Product,
        candidates: Sequence[RecommendationCandidate],
        *,
        requested_voltage: Voltage | None = None,
    ) -> Recommendation | None:
        voltage = _resolved_voltage(base, requested_voltage)
        return _best(
            [
                Recommendation(candidate.product, "UPSELL", _upsell_score(base, candidate))
                for candidate in candidates
                if _upsell_eligible(base, candidate.product, voltage)
            ]
        )

    def select_cross_sell(
        self,
        base: Product,
        candidates: Sequence[RecommendationCandidate],
        *,
        requested_voltage: Voltage | None = None,
    ) -> Recommendation | None:
        voltage = _resolved_voltage(base, requested_voltage)
        recommendations: list[Recommendation] = []
        for candidate in candidates:
            affinity = _affinity(base, candidate)
            if affinity is not None and _cross_eligible(base, candidate.product, voltage):
                recommendations.append(
                    Recommendation(
                        candidate.product,
                        "CROSS_SELL",
                        _cross_score(base, candidate, affinity),
                    )
                )
        return _best(recommendations)

    def recommend(
        self,
        base: Product,
        upsell_candidates: Sequence[RecommendationCandidate],
        cross_sell_candidates: Sequence[RecommendationCandidate],
        *,
        requested_voltage: Voltage | None = None,
        allow_upsell: bool = True,
    ) -> tuple[Recommendation, ...]:
        _resolved_voltage(base, requested_voltage)
        recommendations: list[Recommendation] = []
        if _available(base) and _voltage_matches(base.voltage, requested_voltage):
            recommendations.append(Recommendation(base, "PRIMARY", ZERO))
        if allow_upsell:
            selected = self.select_upsell(
                base, upsell_candidates, requested_voltage=requested_voltage
            )
            if selected is not None:
                recommendations.append(selected)
        selected_cross = self.select_cross_sell(
            base,
            cross_sell_candidates,
            requested_voltage=requested_voltage,
        )
        if selected_cross is not None:
            recommendations.append(selected_cross)
        return tuple(recommendations)
