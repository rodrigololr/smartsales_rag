"""B04 wiring: SQL candidates -> RecommendationEngine -> Product Cards (RN01, RN04-RN06)."""

import asyncio
from collections.abc import Sequence
from decimal import Decimal

import pytest
from app.models.schemas import CatalogProduct
from app.recommendation.cards import (
    CROSS_SELL_BADGE,
    PRIMARY_BADGE,
    UPSELL_BADGE,
    build_card,
    upsell_justification,
)
from app.recommendation.intent import wants_upgrade
from app.recommendation.service import (
    CrossSellRelation,
    RecommendationLookupError,
    RecommendationService,
)

CARD_FIELDS = {
    "sku",
    "name",
    "price",
    "stock_quantity",
    "voltage",
    "capacity_liters",
    "power_watts",
    "image_url",
    "marketplace",
    "checkout_url",
    "recommendation_type",
    "badge_label",
    "justification",
}


def catalog_product(sku: str, price: str, **overrides: object) -> CatalogProduct:
    fields: dict[str, object] = {
        "sku": sku,
        "name": f"Produto {sku}",
        "category": "Eletroportáteis",
        "subcategory": "Fritadeiras Elétricas",
        "brand": "SmartChef",
        "price": price,
        "stock_quantity": 5,
        "voltage": "220V",
        "capacity_liters": "4.0",
        "power_watts": 1500,
        "image_url": f"/images/{sku}.svg",
        "checkout_url": f"https://example.com/{sku}",
    }
    fields.update(overrides)
    return CatalogProduct.model_validate(fields)


BASE = catalog_product("AF-400-220V", "499.90", name="Airfryer SmartChef 4L")
FAMILY = catalog_product("AF-550-220V", "629.90", capacity_liters="5.5", tier_rank=2)
TOO_EXPENSIVE = catalog_product("AF-1000-220V", "899.90", capacity_liters="10.0", tier_rank=4)
SOLD_OUT = catalog_product("AF-600-220V", "599.90", capacity_liters="6.0", stock_quantity=0)
KIT = catalog_product(
    "KIT-SIL-01",
    "79.90",
    category="Acessórios",
    subcategory="Acessórios para Airfryer",
    voltage="N/A",
    capacity_liters=None,
    power_watts=None,
)
KIT_RELATION = CrossSellRelation(KIT, Decimal("0.950"), "Formas compatíveis com cestos de 4L a 8L.")


class FakeCatalog:
    def __init__(
        self,
        upsells: Sequence[CatalogProduct] = (FAMILY, TOO_EXPENSIVE, SOLD_OUT),
        relations: Sequence[CrossSellRelation] = (KIT_RELATION,),
        failure: Exception | None = None,
    ) -> None:
        self.upsells = list(upsells)
        self.relations = list(relations)
        self.failure = failure
        self.similarity_skus: list[str] = []

    async def upsell_candidates(self, base: CatalogProduct) -> list[CatalogProduct]:
        if self.failure:
            raise self.failure
        return self.upsells

    async def cross_sell_relations(self, sku: str) -> list[CrossSellRelation]:
        return self.relations

    async def max_similarities(
        self, skus: Sequence[str], embedding: Sequence[float]
    ) -> dict[str, float]:
        self.similarity_skus = list(skus)
        return {sku: 0.5 for sku in skus}


def cards(
    catalog: FakeCatalog,
    base: CatalogProduct = BASE,
    *,
    allow_upsell: bool = True,
    embedding: Sequence[float] | None = (0.1, 0.2),
) -> list[dict[str, object]]:
    service = RecommendationService(catalog)
    return asyncio.run(
        service.cards(base, query_embedding=embedding, allow_upsell=allow_upsell)
    )


def roles(found: list[dict[str, object]]) -> list[tuple[object, object]]:
    return [(card["recommendation_type"], card["sku"]) for card in found]


def test_it_b04_01_scenario_returns_primary_upsell_and_cross_sell() -> None:
    catalog = FakeCatalog()
    found = cards(catalog)

    assert roles(found) == [
        ("PRIMARY", "AF-400-220V"),
        ("UPSELL", "AF-550-220V"),
        ("CROSS_SELL", "KIT-SIL-01"),
    ]
    assert all(set(card) == CARD_FIELDS for card in found)  # openapi.yaml ProductCard
    assert set(catalog.similarity_skus) == {"AF-550-220V", "AF-1000-220V", "AF-600-220V", "KIT-SIL-01"}


def test_cards_carry_sql_price_stock_and_voltage_never_text() -> None:
    primary, upsell, cross = cards(FakeCatalog())
    assert (primary["price"], primary["stock_quantity"], primary["voltage"]) == (499.9, 5, "220V")
    assert (upsell["price"], upsell["capacity_liters"], upsell["power_watts"]) == (629.9, 5.5, 1500)
    assert cross["capacity_liters"] is None and cross["power_watts"] is None
    assert cross["justification"] == KIT_RELATION.justification_template
    assert [c["badge_label"] for c in (primary, upsell, cross)] == [
        PRIMARY_BADGE,
        UPSELL_BADGE,
        CROSS_SELL_BADGE,
    ]


def test_technical_question_only_turn_offers_no_upsell() -> None:
    assert roles(cards(FakeCatalog(), allow_upsell=False)) == [
        ("PRIMARY", "AF-400-220V"),
        ("CROSS_SELL", "KIT-SIL-01"),
    ]


def test_sold_out_base_is_never_a_card_but_its_substitutes_are() -> None:
    sold_out_base = BASE.model_copy(update={"stock_quantity": 0})
    assert roles(cards(FakeCatalog(), sold_out_base)) == [
        ("UPSELL", "AF-550-220V"),
        ("CROSS_SELL", "KIT-SIL-01"),
    ]


def test_without_query_embedding_similarity_is_zero_and_sql_is_not_asked() -> None:
    catalog = FakeCatalog()
    assert len(cards(catalog, embedding=None)) == 3
    assert catalog.similarity_skus == []


def test_lookup_failure_yields_no_cards_instead_of_breaking_the_answer() -> None:
    assert cards(FakeCatalog(failure=RecommendationLookupError("db down"))) == []


def test_upsell_justification_uses_only_sql_numbers() -> None:
    text = upsell_justification(BASE, FAMILY)
    assert text == (
        "Capacidade de 5,5 L, contra 4 L do modelo consultado, por R$ 130,00 a mais (+26%). "
        "Voltagem: 220V."
    )


def test_upsell_justification_without_capacity_talks_about_the_line() -> None:
    monitor = BASE.model_copy(update={"capacity_liters": None})
    better = FAMILY.model_copy(update={"capacity_liters": None, "voltage": "BIVOLT"})
    assert upsell_justification(monitor, better) == (
        "Linha superior ao modelo consultado, por R$ 130,00 a mais (+26%). Voltagem: BIVOLT."
    )


def test_primary_card_states_stock_and_voltage() -> None:
    card = build_card(BASE, "PRIMARY", "ignored for primary")
    assert card["justification"] == "Produto consultado, disponível em estoque. Voltagem: 220V."


@pytest.mark.parametrize(
    "question",
    [
        "Essa de 4L atende uma família de 5 pessoas?",
        "Tem um modelo maior?",
        "Qual a diferença para a de 5.5L?",
        "Vale a pena comparar com outra?",
        "Preciso de mais capacidade",
    ],
)
def test_capacity_or_comparison_questions_ask_for_an_upgrade(question: str) -> None:
    assert wants_upgrade(question)


@pytest.mark.parametrize(
    "question",
    ["Posso usar papel alumínio no cesto?", "Qual a voltagem?", "Como limpar o cesto?"],
)
def test_plain_technical_questions_do_not_ask_for_an_upgrade(question: str) -> None:
    assert not wants_upgrade(question)
