"""Application service of B04: SQL candidates -> RecommendationEngine -> Product Cards.

Every figure of a card comes from the rows read here at answer time (RN01, RN06),
the consulted product included: the turn's own snapshot predates the generation.
Any failure yields no cards: recommendations never break a technical answer.
"""

import logging
from collections.abc import Sequence
from contextlib import AbstractAsyncContextManager
from dataclasses import dataclass
from decimal import Decimal
from typing import Protocol

from pydantic import ValidationError

from app.models.schemas import CatalogProduct
from app.recommendation.cards import ProductCard, build_card, upsell_justification
from app.recommendation.engine import RecommendationEngine
from app.recommendation.models import (
    CompatibilityEvidence,
    DomainInputError,
    Product,
    Recommendation,
    RecommendationCandidate,
    Voltage,
)

logger = logging.getLogger(__name__)


class RecommendationLookupError(Exception):
    """The catalog could not be read for recommendation candidates."""


@dataclass(frozen=True)
class CrossSellRelation:
    """A CROSS_SELL row of product_relations with its related product (RN05)."""

    product: CatalogProduct
    affinity_weight: Decimal
    justification_template: str


class RecommendationCatalog(Protocol):
    def snapshot(self) -> AbstractAsyncContextManager["RecommendationCatalog"]: ...

    async def current_product(self, sku: str) -> CatalogProduct | None: ...

    async def upsell_candidates(self, base: CatalogProduct) -> list[CatalogProduct]: ...

    async def cross_sell_relations(self, sku: str) -> list[CrossSellRelation]: ...

    async def max_similarities(
        self, skus: Sequence[str], embedding: Sequence[float]
    ) -> dict[str, float]: ...


def _engine_product(product: CatalogProduct) -> Product:
    return Product(
        sku=product.sku,
        category=product.category,
        subcategory=product.subcategory,
        price=product.price,
        stock_quantity=product.stock_quantity,
        is_active=product.is_active,
        voltage=product.voltage,
        tier_rank=product.tier_rank,
        capacity_liters=product.capacity_liters,
    )


def _similarity(similarities: dict[str, float], sku: str) -> tuple[Decimal, ...]:
    if sku not in similarities:
        return ()
    return (Decimal(str(similarities[sku])),)


def _fits(product: CatalogProduct, capacity_min: Decimal | None, budget_max: Decimal | None) -> bool:
    within_budget = budget_max is None or product.price <= budget_max
    enough_capacity = capacity_min is None or (
        product.capacity_liters is not None and product.capacity_liters >= capacity_min
    )
    return within_budget and enough_capacity


class RecommendationService:
    def __init__(
        self, catalog: RecommendationCatalog, engine: RecommendationEngine | None = None
    ) -> None:
        self._catalog = catalog
        self._engine = engine or RecommendationEngine()

    async def cards(
        self,
        base: CatalogProduct,
        *,
        query_embedding: Sequence[float] | None,
        allow_upsell: bool,
        requested_voltage: Voltage | None = None,
        category: str | None = None,
        capacity_min: Decimal | None = None,
        budget_max: Decimal | None = None,
        allow_secondary: bool = True,
    ) -> list[ProductCard]:
        """At most 3 cards (PRIMARY, UPSELL, CROSS_SELL), all in stock at this instant.

        `base` only names the consulted product; its row is read again here.
        """
        try:
            async with self._catalog.snapshot() as catalog:
                return await self._current_cards(
                    catalog, base.sku, query_embedding, allow_upsell, requested_voltage,
                    category, capacity_min, budget_max, allow_secondary
                )
        except (RecommendationLookupError, DomainInputError, ValidationError):
            logger.exception("recommendation_failed", extra={"sku": base.sku})
            return []

    async def _current_cards(
        self,
        catalog: RecommendationCatalog,
        sku: str,
        query_embedding: Sequence[float] | None,
        allow_upsell: bool,
        requested_voltage: Voltage | None,
        category: str | None,
        capacity_min: Decimal | None,
        budget_max: Decimal | None,
        allow_secondary: bool,
    ) -> list[ProductCard]:
        base = await catalog.current_product(sku)
        if base is None or not base.is_active:
            return []
        incompatible = requested_voltage is not None and base.voltage not in (
            requested_voltage, "BIVOLT", "N/A"
        )
        if category is not None and base.category != category:
            return []
        insufficient = capacity_min is not None and (
            base.capacity_liters is None or base.capacity_liters < capacity_min
        )
        allow_upsell = allow_secondary and (
            allow_upsell or base.stock_quantity <= 0 or incompatible or insufficient
        )
        upsells = await catalog.upsell_candidates(base) if allow_upsell else []
        upsells = [p for p in upsells if _fits(p, capacity_min, budget_max)]
        relations = [r for r in await catalog.cross_sell_relations(base.sku)
                     if _fits(r.product, None, budget_max)] if allow_secondary else []
        similarities = await self._similarities(catalog, upsells, relations, query_embedding)
        selected = self._engine.recommend(
            _engine_product(base),
            [
                RecommendationCandidate(_engine_product(p), _similarity(similarities, p.sku))
                for p in upsells
            ],
            [self._cross_candidate(base, r, similarities) for r in relations],
            requested_voltage=requested_voltage,
            allow_upsell=allow_upsell,
        )
        rows = {p.sku: p for p in [base, *upsells, *(r.product for r in relations)]}
        templates = {r.product.sku: r.justification_template for r in relations}
        return [self._card(base, rows[item.product.sku], item, templates) for item in selected
                if item.recommendation_type != "PRIMARY" or _fits(base, capacity_min, budget_max)]

    async def _similarities(
        self,
        catalog: RecommendationCatalog,
        upsells: Sequence[CatalogProduct],
        relations: Sequence[CrossSellRelation],
        query_embedding: Sequence[float] | None,
    ) -> dict[str, float]:
        skus = [p.sku for p in upsells] + [r.product.sku for r in relations]
        if query_embedding is None or not skus:
            return {}
        return await catalog.max_similarities(skus, query_embedding)

    @staticmethod
    def _cross_candidate(
        base: CatalogProduct, relation: CrossSellRelation, similarities: dict[str, float]
    ) -> RecommendationCandidate:
        return RecommendationCandidate(
            _engine_product(relation.product),
            _similarity(similarities, relation.product.sku),
            CompatibilityEvidence(
                base_sku=base.sku,
                candidate_sku=relation.product.sku,
                source="CROSS_SELL_RELATION",
                affinity_weight=relation.affinity_weight,
            ),
        )

    @staticmethod
    def _card(
        base: CatalogProduct,
        product: CatalogProduct,
        item: Recommendation,
        templates: dict[str, str],
    ) -> ProductCard:
        if item.recommendation_type == "UPSELL":
            return build_card(product, "UPSELL", upsell_justification(base, product))
        return build_card(product, item.recommendation_type, templates.get(product.sku, ""))
