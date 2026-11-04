"""Synthetic domain fixtures: these are not a real catalog or a RAGAS set."""

from dataclasses import replace
from decimal import Decimal

import pytest
from app.recommendation import (
    CompatibilityEvidence,
    DomainInputError,
    Product,
    RecommendationCandidate,
    RecommendationEngine,
)


def product(sku: str = "SYNTH-BASE", price: str = "500.00") -> Product:
    return Product(
        sku=sku,
        category="appliance",
        subcategory="airfryer",
        price=Decimal(price),
        stock_quantity=5,
        is_active=True,
        voltage="220V",
        tier_rank=1,
        capacity_liters=Decimal("4"),
    )


def upsell(sku: str = "SYNTH-UP", price: str = "625.00") -> RecommendationCandidate:
    return RecommendationCandidate(
        replace(product(sku, price), capacity_liters=Decimal("5.5")),
        similarities=(Decimal("0.8"),),
    )


def accessory(
    sku: str = "SYNTH-KIT", price: str = "79.90", weight: str = "0.95"
) -> RecommendationCandidate:
    return RecommendationCandidate(
        replace(product(sku, price), category="accessory", subcategory="basket", voltage="N/A"),
        similarities=(Decimal("0.8"),),
        compatibility=CompatibilityEvidence(
            base_sku="SYNTH-BASE",
            candidate_sku=sku,
            source="CROSS_SELL_RELATION",
            affinity_weight=Decimal(weight),
        ),
    )


def test_ut_b04_01_rejects_overpriced_and_out_of_stock_upsells() -> None:
    engine = RecommendationEngine()
    available = upsell()
    unavailable = replace(
        upsell("SYNTH-EMPTY", "600"),
        product=replace(upsell("SYNTH-EMPTY", "600").product, stock_quantity=0),
    )
    chosen = engine.select_upsell(
        product(), [upsell("SYNTH-EXPENSIVE", "800"), unavailable, available]
    )
    assert chosen is not None
    assert chosen.product.sku == "SYNTH-UP"
    assert chosen.recommendation_type == "UPSELL"


def test_ut_b04_03_upsell_price_limit_is_inclusive_and_exact() -> None:
    chosen = RecommendationEngine().select_upsell(
        product(), [upsell("SYNTH-OVER", "675.01"), upsell("SYNTH-EDGE", "675.00")]
    )
    assert chosen is not None
    assert chosen.product.price == Decimal("675.00")


@pytest.mark.parametrize("price", ["499.99", "500.00", "675.01"])
def test_upsell_requires_a_strict_increase_within_35_percent(price: str) -> None:
    assert RecommendationEngine().select_upsell(product(), [upsell(price=price)]) is None


@pytest.mark.parametrize(
    "change",
    [
        {"stock_quantity": 0},
        {"stock_quantity": -1},
        {"is_active": False},
        {"voltage": "127V"},
        {"category": "monitor"},
        {"subcategory": "coffee"},
        {"capacity_liters": Decimal("4"), "tier_rank": 1},
    ],
)
def test_upsell_filters_hard_ineligible_candidates(change: dict[str, object]) -> None:
    candidate = upsell()
    assert (
        RecommendationEngine().select_upsell(
            product(), [replace(candidate, product=replace(candidate.product, **change))]
        )
        is None
    )


def test_upsell_tier_fallback_does_not_invent_liters_for_monitor() -> None:
    base = replace(product(), category="monitor", subcategory="display", capacity_liters=None)
    candidate = RecommendationCandidate(
        replace(base, sku="SYNTH-MONITOR", price=Decimal("570"), tier_rank=3)
    )
    chosen = RecommendationEngine().select_upsell(base, [candidate])
    assert chosen is not None
    assert chosen.score == Decimal("0.27")  # .3*(2/4) + .2*(1-70/175)
    assert chosen.product.capacity_liters is None


def test_capacity_gain_and_pricefit_use_exact_decimal_without_rounding() -> None:
    candidate = replace(
        upsell(price="570"),
        product=replace(upsell(price="570").product, capacity_liters=Decimal("6")),
        similarities=(Decimal("0.2"), Decimal("0.8")),
    )
    chosen = RecommendationEngine().select_upsell(product(), [candidate])
    assert chosen is not None
    assert chosen.score == Decimal("0.67")  # .5*.8 + .3*.5 + .2*.6


def test_similarity_is_zero_without_chunks_and_clamped_to_unit_interval() -> None:
    candidate = upsell(price="570")
    engine = RecommendationEngine()
    negative = engine.select_upsell(
        product(), [replace(candidate, similarities=(Decimal("-0.8"),))]
    )
    absent = engine.select_upsell(product(), [replace(candidate, similarities=())])
    clamped = engine.select_upsell(product(), [replace(candidate, similarities=(Decimal("1.2"),))])
    assert negative is not None and absent is not None and clamped is not None
    assert negative.score == absent.score == Decimal("0.2325")
    assert clamped.score == Decimal("0.7325")


def test_ut_b04_02_and_04_cross_sell_uses_affinity_and_rejects_empty_or_expensive() -> None:
    empty = accessory("SYNTH-EMPTY", "49.90")
    chosen = RecommendationEngine().select_cross_sell(
        product(),
        [
            replace(empty, product=replace(empty.product, stock_quantity=0)),
            accessory("SYNTH-CHEAP", "49.90", "0.60"),
            accessory("SYNTH-OVER", "210"),
            accessory(),
        ],
    )
    assert chosen is not None
    assert chosen.product.sku == "SYNTH-KIT"
    assert chosen.recommendation_type == "CROSS_SELL"
    assert chosen.score == Decimal("0.860075")


@pytest.mark.parametrize("price,eligible", [("200.00", True), ("200.01", False)])
def test_cross_sell_40_percent_boundary(price: str, eligible: bool) -> None:
    chosen = RecommendationEngine().select_cross_sell(product(), [accessory(price=price)])
    assert (chosen is not None) is eligible


@pytest.mark.parametrize(
    "evidence",
    [
        None,
        CompatibilityEvidence("OTHER-BASE", "SYNTH-KIT", "CROSS_SELL_RELATION", Decimal("0.95")),
        CompatibilityEvidence("SYNTH-BASE", "OTHER-KIT", "CROSS_SELL_RELATION", Decimal("0.95")),
    ],
)
def test_cross_sell_requires_proof_for_this_base_and_candidate(
    evidence: CompatibilityEvidence | None,
) -> None:
    assert (
        RecommendationEngine().select_cross_sell(
            product(), [replace(accessory(), compatibility=evidence)]
        )
        is None
    )


def test_category_compatibility_uses_fixed_weight_half() -> None:
    candidate = replace(
        accessory(price="100"),
        compatibility=CompatibilityEvidence("SYNTH-BASE", "SYNTH-KIT", "COMPLEMENTARY_CATEGORY"),
    )
    chosen = RecommendationEngine().select_cross_sell(product(), [candidate])
    assert chosen is not None
    assert chosen.score == Decimal("0.575")


@pytest.mark.parametrize(
    "change", [{"stock_quantity": 0}, {"is_active": False}, {"voltage": "127V"}]
)
def test_cross_sell_filters_stock_active_and_electrical_mismatch(change: dict[str, object]) -> None:
    candidate = accessory()
    assert (
        RecommendationEngine().select_cross_sell(
            product(), [replace(candidate, product=replace(candidate.product, **change))]
        )
        is None
    )


def test_recommend_limits_orders_and_preserves_sql_product_values() -> None:
    base = product()
    selected = RecommendationEngine().recommend(
        base, [upsell(), upsell("SYNTH-UP2")], [accessory(), accessory("SYNTH-KIT2")]
    )
    assert [item.recommendation_type for item in selected] == ["PRIMARY", "UPSELL", "CROSS_SELL"]
    assert selected[0].product is base
    assert selected[0].product.price == Decimal("500.00")
    assert selected[0].product.voltage == "220V"


@pytest.mark.parametrize("change", [{"stock_quantity": 0}, {"is_active": False}])
def test_primary_never_offers_inactive_or_unavailable_base(change: dict[str, object]) -> None:
    assert RecommendationEngine().recommend(replace(product(), **change), [], []) == ()


def test_requested_voltage_restricts_primary_and_upsell_and_accepts_bivolt() -> None:
    engine = RecommendationEngine()
    assert engine.recommend(product(), [], [], requested_voltage="127V") == ()
    assert engine.select_upsell(product(), [upsell()], requested_voltage="127V") is None
    universal = replace(upsell(), product=replace(upsell().product, voltage="BIVOLT"))
    chosen = engine.select_upsell(product(), [universal], requested_voltage="127V")
    assert chosen is not None and chosen.product.voltage == "BIVOLT"


def test_upsell_can_be_disabled_for_direct_purchase_intent() -> None:
    selected = RecommendationEngine().recommend(
        product(), [upsell()], [accessory()], allow_upsell=False
    )
    assert [item.recommendation_type for item in selected] == ["PRIMARY", "CROSS_SELL"]


def test_stable_ranking_uses_score_then_price_then_sku() -> None:
    engine = RecommendationEngine()
    # Equal score: A pays more but has exactly enough extra similarity to offset pricefit.
    expensive = replace(upsell("SYNTH-A", "640"), similarities=(Decimal("0.16"),))
    cheap_z = replace(upsell("SYNTH-Z", "570"), similarities=(Decimal("0"),))
    cheap_b = replace(cheap_z, product=replace(cheap_z.product, sku="SYNTH-B"))
    for candidates in ([expensive, cheap_z, cheap_b], [cheap_b, cheap_z, expensive]):
        chosen = engine.select_upsell(product(), candidates)
        assert chosen is not None and chosen.product.sku == "SYNTH-B"


@pytest.mark.parametrize(
    "price", [Decimal("NaN"), Decimal("Infinity"), Decimal("0"), Decimal("-1"), 500.0]
)
def test_invalid_money_fails_closed(price: object) -> None:
    with pytest.raises(DomainInputError):
        replace(product(), price=price)


@pytest.mark.parametrize("similarity", [Decimal("NaN"), Decimal("-Infinity"), 0.8])
def test_invalid_similarity_fails_closed(similarity: object) -> None:
    with pytest.raises(DomainInputError):
        replace(upsell(), similarities=(similarity,))


def test_duplicate_skus_cannot_occupy_multiple_recommendation_slots() -> None:
    candidate = upsell()
    same_sku_accessory = replace(
        candidate,
        compatibility=CompatibilityEvidence(
            "SYNTH-BASE", "SYNTH-UP", "CROSS_SELL_RELATION", Decimal("1")
        ),
    )
    # It is also over the cross-sell cap and must not be emitted twice.
    selected = RecommendationEngine().recommend(
        product(), [candidate, candidate], [same_sku_accessory]
    )
    assert [item.product.sku for item in selected] == ["SYNTH-BASE", "SYNTH-UP"]
