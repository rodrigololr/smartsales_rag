"""B04 wiring: SQL candidates -> RecommendationEngine -> Product Cards (RN01, RN04-RN06)."""

import asyncio
from collections.abc import AsyncIterator, Sequence
from contextlib import asynccontextmanager
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
from app.recommendation.models import DomainInputError
from app.recommendation.service import (
    CrossSellRelation,
    RecommendationLookupError,
    RecommendationService,
)
from pydantic import ValidationError

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
        current: CatalogProduct | None = None,
        similarity: float = 0.5,
    ) -> None:
        self.current = {current.sku: current} if current else {}
        self.similarity = similarity
        self.upsells = list(upsells)
        self.relations = list(relations)
        self.failure = failure
        self.similarity_skus: list[str] = []

    @asynccontextmanager
    async def snapshot(self) -> AsyncIterator["FakeCatalog"]:
        yield self

    async def current_product(self, sku: str) -> CatalogProduct | None:
        return self.current.get(sku)

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
        return {sku: self.similarity for sku in skus}


def cards(
    catalog: FakeCatalog,
    base: CatalogProduct = BASE,
    *,
    allow_upsell: bool = True,
    embedding: Sequence[float] | None = (0.1, 0.2),
    base_in_sql: bool = True,
) -> list[dict[str, object]]:
    if base_in_sql:  # by default SQL still holds the row the turn started with
        catalog.current.setdefault(base.sku, base)
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


def _invalid_row_error() -> ValidationError:
    with pytest.raises(ValidationError) as caught:
        CatalogProduct.model_validate({})
    return caught.value


@pytest.mark.parametrize(
    "failure",
    [
        RecommendationLookupError("db down"),
        DomainInputError("tier_rank must be between 1 and 5"),
        _invalid_row_error(),
    ],
)
def test_any_recommendation_failure_yields_no_cards_instead_of_breaking_the_answer(
    failure: Exception,
) -> None:
    assert cards(FakeCatalog(failure=failure)) == []


def test_non_finite_similarity_yields_no_cards() -> None:
    # pgvector answers NaN for a zero vector; the engine rejects it as a domain error.
    assert cards(FakeCatalog(similarity=float("nan"))) == []


def test_primary_card_uses_the_base_row_of_this_instant_not_the_turn_snapshot() -> None:
    repriced = BASE.model_copy(update={"price": Decimal("519.90"), "stock_quantity": 2})
    primary = cards(FakeCatalog(current=repriced), BASE)[0]
    assert (primary["price"], primary["stock_quantity"]) == (519.9, 2)


def test_base_sold_out_during_the_turn_is_not_a_primary_card() -> None:
    sold_out_now = BASE.model_copy(update={"stock_quantity": 0})
    assert roles(cards(FakeCatalog(current=sold_out_now), BASE)) == [
        ("UPSELL", "AF-550-220V"),
        ("CROSS_SELL", "KIT-SIL-01"),
    ]


def test_upsell_ceiling_follows_the_current_base_price() -> None:
    cheaper_now = BASE.model_copy(update={"price": Decimal("400.00")})  # ceiling: 540.00
    assert roles(cards(FakeCatalog(current=cheaper_now), BASE)) == [
        ("PRIMARY", "AF-400-220V"),
        ("CROSS_SELL", "KIT-SIL-01"),
    ]


def test_base_removed_or_deactivated_during_the_turn_yields_no_cards() -> None:
    assert cards(FakeCatalog(), base_in_sql=False) == []
    assert cards(FakeCatalog(current=BASE.model_copy(update={"is_active": False}))) == []


def test_upsell_justification_groups_thousands_in_brazilian_format() -> None:
    notebook = catalog_product("NB-1", "3999.00", capacity_liters=None)
    better = catalog_product("NB-2", "5299.00", capacity_liters=None, tier_rank=2)
    assert "por R$ 1.300,00 a mais (+33%)." in upsell_justification(notebook, better)


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
        "Tem uma maior?",
        "Comporta 5 porções de batata?",
    ],
)
def test_capacity_or_comparison_questions_ask_for_an_upgrade(question: str) -> None:
    assert wants_upgrade(question)


@pytest.mark.parametrize(
    "question",
    [
        "Posso usar papel alumínio no cesto?",
        "Qual a voltagem?",
        "Como limpar o cesto?",
        "Qual a maior temperatura que ela atinge?",
        "Como ela se comporta em 127V?",
        "A potência é suficiente para pão de queijo?",
        "Não preciso de uma maior, qual a voltagem?",
    ],
)
def test_plain_technical_questions_do_not_ask_for_an_upgrade(question: str) -> None:
    assert not wants_upgrade(question)


@pytest.mark.parametrize("question", [
    "Não quero um modelo maior, só saber a voltagem.",
    "Não preciso de mais capacidade.",
    "Sem upgrade, por favor.",
    "Não quero comparar modelos.",
    "A alça protege as pessoas de queimaduras?",
])
def test_explicitly_declined_upgrade_and_incidental_people_do_not_trigger(question: str) -> None:
    assert not wants_upgrade(question)


def test_stock_refresh_opens_alternatives_even_when_initial_turn_did_not() -> None:
    current = BASE.model_copy(update={"stock_quantity": 0})
    assert ("UPSELL", FAMILY.sku) in roles(cards(FakeCatalog(current=current), allow_upsell=False))


def test_voltage_incompatibility_opens_alternatives_without_a_capacity_request() -> None:
    compatible = FAMILY.model_copy(update={"voltage": "127V"})
    catalog = FakeCatalog(upsells=[compatible], current=BASE)
    found = asyncio.run(RecommendationService(catalog).cards(
        BASE, query_embedding=None, allow_upsell=False, requested_voltage="127V",
    ))
    assert ("UPSELL", FAMILY.sku) in roles(found)
    assert all(card["voltage"] in {"127V", "BIVOLT", "N/A"} for card in found)


def test_ranking_does_not_round_similarity_before_selecting() -> None:
    class CloseScores(FakeCatalog):
        async def max_similarities(self, skus: Sequence[str], embedding: Sequence[float]) -> dict[str, float]:
            return {"A": 0.9000001, "Z": 0.9000002}
    lower = FAMILY.model_copy(update={"sku": "A"})
    higher = FAMILY.model_copy(update={"sku": "Z"})
    found = cards(CloseScores(upsells=[lower, higher], relations=[]))
    assert next(card for card in found if card["recommendation_type"] == "UPSELL")["sku"] == "Z"


@pytest.mark.parametrize("constraints, expected", [
    ({"budget_max": Decimal("600.00")}, [("PRIMARY", BASE.sku), ("CROSS_SELL", KIT.sku)]),
    ({"capacity_min": Decimal("5")}, [("UPSELL", FAMILY.sku), ("CROSS_SELL", KIT.sku)]),
    ({"category": "Cosméticos"}, []),
])
def test_resolved_purchase_constraints_filter_before_ranking(
    constraints: dict[str, object], expected: list[tuple[str, str]],
) -> None:
    catalog = FakeCatalog(current=BASE)
    found = asyncio.run(RecommendationService(catalog).cards(
        BASE, query_embedding=None, allow_upsell=False, **constraints,  # type: ignore[arg-type]
    ))
    assert roles(found) == expected


def test_minimum_capacity_filters_out_the_best_but_insufficient_upsell() -> None:
    big = FAMILY.model_copy(update={"sku": "BIG", "capacity_liters": Decimal("6")})
    catalog = FakeCatalog(upsells=[FAMILY, big], current=BASE)
    found = asyncio.run(RecommendationService(catalog).cards(
        BASE, query_embedding=None, allow_upsell=True, capacity_min=Decimal("6"),
    ))
    assert ("UPSELL", "BIG") in roles(found)
    assert all(card['sku'] != BASE.sku for card in found)


@pytest.mark.parametrize('question', [
    'Não atende 5 pessoas, tem uma maior?',
    'Não quero mais potência, mas preciso de mais capacidade.',
])
def test_decline_in_one_clause_does_not_hide_a_positive_need_in_another(question: str) -> None:
    assert wants_upgrade(question)


def test_budget_applies_to_each_accessory_and_the_primary() -> None:
    found = asyncio.run(RecommendationService(FakeCatalog(current=BASE)).cards(
        BASE, query_embedding=None, allow_upsell=True, budget_max=Decimal('70'),
    ))
    assert found == []


def test_restocked_base_does_not_force_an_unrequested_upgrade() -> None:
    old = BASE.model_copy(update={"stock_quantity": 0})
    catalog = FakeCatalog(current=BASE)
    assert ("UPSELL", FAMILY.sku) not in roles(cards(catalog, old, allow_upsell=False))


def test_explicit_primary_only_request_never_emits_secondary_offers() -> None:
    found = asyncio.run(RecommendationService(FakeCatalog(current=BASE)).cards(
        BASE, query_embedding=None, allow_upsell=True, allow_secondary=False,
    ))
    assert roles(found) == [('PRIMARY', BASE.sku)]


def test_technical_only_word_does_not_suppress_secondary_cards() -> None:
    from app.recommendation.intent import only_consulted_product
    assert not only_consulted_product('Somente o cesto pode ser lavado?')
    assert only_consulted_product('Mostre apenas o produto consultado.')


@pytest.mark.parametrize("question", [
    "Somos seis pessoas; mostre uma Airfryer maior sem subir mais de 35% do preço.",
    "Quero uma cafeteira com reservatório maior sem passar de 35% a mais.",
    "Quero uma Airfryer maior que a de 5.5L, em 220V e dentro de +35%.",
    "Somos 6 pessoas, qual comprar?",
])
def test_bigger_product_or_household_size_requests_ask_for_an_upgrade(question: str) -> None:
    assert wants_upgrade(question)
