"""B03: verify SQL facts and the actual cited evidence before publishing a sentence."""

from decimal import Decimal

import pytest
from app.guardrails.output import technical_claims
from app.guardrails.publication import ConsultativeVerifier, SentenceVerifier
from app.models.schemas import CatalogProduct, ProductRecommendation
from test_orchestrator import PRODUCT, Catalog, ChatModel, chunk, names, run


@pytest.mark.parametrize(
    "answer,manual",
    [
        ("Este modelo custa R$ 349,90.", "Preço antigo: R$ 349,90."),
        ("Este modelo custa 349,90 reais.", "Manual de uso."),
        ("Este modelo custa 349,90.", "Manual de uso."),
        ("O preço é de 349,90.", "O preço é de 349,90."),
        ("Este modelo funciona em 127V.", "Este modelo funciona em 127V."),
        ("Pode usar plástico no cesto.", "É proibido usar plástico no cesto."),
        ("O AF-550-220V custa R$ 499,90.", "Manual de uso."),
        ("A voltagem é 1500 W e a potência é 220V.", "Manual de uso."),
        ("Este modelo funciona em 4 L.", "Manual de uso."),
        ("A capacidade é 5000 mL.", "A capacidade é 5000 mL."),
        ("A potência é 3 kW.", "A potência é 3 kW."),
        ("Suporta até 1,2 kg [Fonte: Manual inexistente, p. 99].", "Suporta até 1,2 kg."),
    ],
)
def test_unsupported_facts_never_reach_the_published_stream(answer: str, manual: str) -> None:
    events = run(Catalog(PRODUCT, [chunk(content=manual)]), ChatModel([answer]))
    assert names(events) == ["error", "end"]


def test_a_number_on_another_retrieved_page_does_not_support_the_cited_page() -> None:
    evidence = chunk()
    unrelated = chunk(content="Limpar somente depois de esfriar.").model_copy(update={"page_number": 3})
    answer = "O cesto suporta até 1,2 kg [Fonte: Manual Airfryer SmartChef 4L, p. 3]."
    events = run(Catalog(PRODUCT, [evidence, unrelated]), ChatModel([answer]))
    assert names(events) == ["error", "end"]


def test_foreign_sku_chunks_are_not_sent_to_generation() -> None:
    foreign = chunk(content="Este modelo funciona em 127V.").model_copy(update={"sku": "OTHER-127V"})
    model = ChatModel(["Este modelo funciona em 127V."])
    events = run(Catalog(PRODUCT, [foreign]), model)
    assert names(events) == ["error", "end"] and not model.messages


def test_current_sql_price_can_be_published_without_a_manual_citation() -> None:
    events = run(Catalog(PRODUCT, [chunk()]), ChatModel(["Este modelo custa R$ 499,90."]))
    assert "token" in names(events)
    assert events[-2]["data"]["citations"] == []  # type: ignore[index]


@pytest.mark.parametrize("answer", [
    "Este modelo funciona em 220V.", "A potência é 1500 W.", "Possui capacidade de 4 L.",
    "A potência é 1,5 kW.", "Possui capacidade de 4000 mL.",
])
def test_single_attribute_sql_statements_are_published(answer: str) -> None:
    assert "token" in names(run(Catalog(PRODUCT, [chunk()]), ChatModel([answer])))


def test_literal_material_evidence_gets_only_its_real_page_citation() -> None:
    literal = "Formas de silicone podem ser usadas no cesto."
    events = run(Catalog(PRODUCT, [chunk(content=literal)]), ChatModel([literal]))
    published = "".join(event["data"]["delta"] for event in events if event["event"] == "token")  # type: ignore[index, misc]
    assert "[Fonte: Manual Airfryer SmartChef 4L, p. 7]" in published
    assert events[-2]["data"]["citations"][0]["page_number"] == 7  # type: ignore[index]


def test_citations_contain_only_supporting_chunk_ids_even_on_the_same_page() -> None:
    supporting = chunk()
    unrelated = chunk(content="Limpar depois de esfriar.")
    answer = "O cesto suporta até 1,2 kg [Fonte: Manual Airfryer SmartChef 4L, p. 7]."
    events = run(Catalog(PRODUCT, [supporting, unrelated]), ChatModel([answer]))
    citations = events[-2]["data"]["citations"]  # type: ignore[index]
    assert [citation["chunk_id"] for citation in citations] == [str(supporting.chunk_id)]


def test_consultative_facts_never_borrow_values_or_manuals_from_another_sku() -> None:
    from app.guardrails.publication import ConsultativeVerifier
    from app.models.schemas import ProductRecommendation
    from test_recommendation_service import FAMILY

    card = ProductRecommendation(
        sku=FAMILY.sku, name=FAMILY.name, price=FAMILY.price,
        stock_quantity=5, voltage=FAMILY.voltage,
        capacity_liters=FAMILY.capacity_liters, power_watts=FAMILY.power_watts,
        recommendation_type='UPSELL',
    )
    verifier = ConsultativeVerifier(PRODUCT, [chunk()], [card])
    assert verifier.approve(f'SKU {FAMILY.sku}: Voltagem: 220V.') is not None
    assert verifier.approve(f'SKU {FAMILY.sku}: Preço atual: R$ 499,90.') is None
    assert verifier.approve(f'SKU {FAMILY.sku}: Possui capacidade de 4 L.') is None
    assert verifier.approve(f'SKU {FAMILY.sku}: O cesto suporta até 1,2 kg.') is None
    assert verifier.approve('SKU AF-UNKNOWN-220V: Voltagem: 220V.') is None
    assert verifier.approve(f'SKU {FAMILY.sku}: Possui capacidade de 5,5 L e {PRODUCT.sku} tem 4 L.') is None
    assert verifier.cited_chunk_ids == set()


def test_dash_bullets_keep_facts_and_sku_anchors_publishable() -> None:
    from app.guardrails.publication import ConsultativeVerifier
    from app.models.schemas import ProductRecommendation
    from test_recommendation_service import FAMILY

    card = ProductRecommendation(
        sku=FAMILY.sku, name=FAMILY.name, price=FAMILY.price,
        stock_quantity=5, voltage=FAMILY.voltage,
        capacity_liters=FAMILY.capacity_liters, power_watts=FAMILY.power_watts,
        recommendation_type="UPSELL",
    )
    verifier = ConsultativeVerifier(PRODUCT, [chunk()], [card])
    assert verifier.approve("- A potência é 1500 W.") == "- A potência é 1500 W."
    assert verifier.approve(f"- SKU {FAMILY.sku}: Voltagem: 220V.") == f"- SKU {FAMILY.sku}: Voltagem: 220V."
    assert verifier.approve(f"- SKU {FAMILY.sku}: Possui capacidade de 4 L.") is None


@pytest.mark.parametrize("answer", [
    "A capacidade é de 4 litros.",
    "A potência é de 1500 W.",
    "A potência é de 1.500 W.",
    "Possui 1.500 watts de potência.",
    "A voltagem é de 220V.",
    "A tensão é de 220 volts.",
    "O preço atual é de R$ 499,90.",
    "O preço é de R$ 499,90.",
    "Este produto é 220V.",
    "Ele é 220V.",
])
def test_common_portuguese_phrasings_of_sql_facts_are_published(answer: str) -> None:
    assert SentenceVerifier(PRODUCT, []).approve(answer) == answer


PRODUCT_127V = PRODUCT.model_copy(update={"voltage": "127V"})


@pytest.mark.parametrize("product,answer", [
    (PRODUCT, "A potência é de 1800 W."),
    (PRODUCT, "A potência é de 1.800 W."),
    (PRODUCT, "A capacidade é de 5 litros."),
    (PRODUCT, "O preço atual é de R$ 349,90."),
    (PRODUCT, "A voltagem é de 1500 W."),
    (PRODUCT, "A potência é de 220V."),
    (PRODUCT_127V, "A voltagem é de 220V."),
    (PRODUCT_127V, "Este produto é 220V."),
    (PRODUCT_127V, "Este produto é bivolt."),
])
def test_wrong_values_in_those_phrasings_are_still_blocked(
    product: CatalogProduct, answer: str
) -> None:
    assert SentenceVerifier(product, []).approve(answer) is None


@pytest.mark.parametrize("text,claim", [
    ("1.500 W", ("1500", "W")),
    ("2.000 mL", ("2", "L")),
    ("1,5 L", ("1.5", "L")),
    ("0.5 L", ("0.5", "L")),
])
def test_thousands_separator_is_not_read_as_a_decimal_point(
    text: str, claim: tuple[str, str]
) -> None:
    assert technical_claims(text) == {claim}


@pytest.mark.parametrize("manual,answer", [
    ("Peso de 1,500 kg.", "Peso de 1.500 kg."),
    ("Peso de 1.500 kg.", "Peso de 1,500 kg."),
    ("Pressão de 1,5 bar.", "Pressão de 15 bar."),
    ("Aquece até 200 °C em 3 min.", "Aquece até 200 °C em 30 min."),
    ("Peso de 1,500 kg de batatas.", "Peso de 1.500 kg"),
])
def test_manual_only_figures_must_be_numerically_equal_to_the_evidence(
    manual: str, answer: str
) -> None:
    verifier = SentenceVerifier(PRODUCT, [chunk(content=manual)])
    assert verifier.approve(answer) is None
    assert verifier.approve(f"{answer} [Fonte: Manual Airfryer SmartChef 4L, p. 7].") is None


@pytest.mark.parametrize("manual,answer", [
    ("Peso de 1,500 kg.", "Peso de 1,500 kg."),
    ("Peso de 1.500 kg.", "Peso de 1.500 kg."),
    ("Pressão de 1,5 bar.", "Pressão de 1.5 bar."),
    ("O cesto suporta até 1,2 kg de batatas.", "O cesto suporta até 1,2 kg."),
])
def test_numerically_identical_manual_figures_are_still_published(manual: str, answer: str) -> None:
    approved = SentenceVerifier(PRODUCT, [chunk(content=manual)]).approve(answer)
    assert approved is not None and "[Fonte: Manual Airfryer SmartChef 4L, p. 7]" in approved


@pytest.mark.parametrize("manual,answer", [
    ("Peso de 2 kg a 3 kg, conforme o modelo.", "Peso de 2 kg."),
    ("Peso de 2 kg - 3 kg.", "Peso de 2 kg."),
    ("Peso de 2 kg – 3 kg.", "Peso de 2 kg."),
    ("Tempo de 10 min até 15 min.", "Tempo de 10 min."),
    ("Tempo de 10 min ou mais.", "Tempo de 10 min."),
    ("Aquece a 200 °C quando pré-aquecida.", "Aquece a 200 °C."),
    ("Aquece a 200 °C em modo turbo.", "Aquece a 200 °C."),
    ("Consome 1.500 W no modo turbo e no modo eco é de 800 W.", "Consome 1.500 W."),
])
def test_truncated_ranges_and_mode_qualifiers_are_not_literal_support(
    manual: str, answer: str
) -> None:
    verifier = SentenceVerifier(PRODUCT, [chunk(content=manual)])
    assert verifier.approve(answer) is None
    assert verifier.approve(f"{answer[:-1]} [Fonte: Manual Airfryer SmartChef 4L, p. 7].") is None


FILTER_MANUAL = "Limpe o filtro semanalmente batendo-o levemente; troque-o a cada 3 meses."


@pytest.mark.parametrize("answer", [
    "Troque-o a cada 3 meses [Fonte: Manual Airfryer SmartChef 4L, p. 7].",
    "Troque-o a cada 3 meses.",
])
def test_a_complete_clause_after_a_semicolon_is_literal_support(answer: str) -> None:
    verifier = SentenceVerifier(PRODUCT, [chunk(content=FILTER_MANUAL)])
    assert verifier.approve(answer) == "Troque-o a cada 3 meses [Fonte: Manual Airfryer SmartChef 4L, p. 7]."


@pytest.mark.parametrize("manual,answer", [
    (FILTER_MANUAL, "Troque-o a cada 6 meses."),
    ("Limpe o cesto; aguarde de 10 min a 15 min antes de guardar.", "Aguarde de 10 min."),
    ("Limpe o cesto; aquece a 200 °C em modo turbo.", "Aquece a 200 °C."),
    # A colon label governs its whole list: its items are not independent clauses.
    ("Nunca utilize: álcool; solventes.", "Solventes."),
    ("Proibido: usar formas de alumínio no cesto.", "Usar formas de alumínio no cesto."),
])
def test_clause_support_keeps_values_ranges_and_governing_labels(manual: str, answer: str) -> None:
    verifier = SentenceVerifier(PRODUCT, [chunk(content=manual)])
    assert verifier.approve(answer) is None
    assert verifier.approve(f"{answer[:-1]} [Fonte: Manual Airfryer SmartChef 4L, p. 7].") is None


def _upgrade_card() -> ProductRecommendation:
    return ProductRecommendation(
        sku="AF-800-220V", name="Airfryer SmartChef 8L", price="799.90",  # type: ignore[arg-type]
        stock_quantity=5, voltage="220V", capacity_liters="8.0",  # type: ignore[arg-type]
        power_watts=1800, recommendation_type="UPSELL",
    )


def _verifier() -> ConsultativeVerifier:
    return ConsultativeVerifier(PRODUCT, [chunk()], [_upgrade_card()])


def test_a_sku_header_attributes_the_following_bullets_to_that_sku() -> None:
    verifier = _verifier()
    assert verifier.approve("SKU AF-800-220V:\n") == ""  # held until its first verified fact
    assert verifier.approve("- A potência é 1800 W.\n") == "SKU AF-800-220V:\n- A potência é 1800 W.\n"
    assert verifier.approve("- Possui capacidade de 8 L.\n") == "- Possui capacidade de 8 L.\n"
    assert verifier.approve("- Preço atual: R$ 799,90.\n") == "- Preço atual: R$ 799,90.\n"
    assert verifier.approve("- Possui capacidade de 4 L.\n") is None  # the base value, not this SKU's
    assert verifier.approve("- A potência é 1500 W.\n") is None


def test_the_sku_block_ends_at_a_blank_line_another_header_or_the_end_of_the_list() -> None:
    verifier = _verifier()
    verifier.approve("SKU AF-800-220V:\n")
    verifier.approve("- A potência é 1800 W.\n")
    verifier.end_block()  # blank line
    assert verifier.approve("A potência é 1800 W.\n") is None
    assert verifier.approve("A potência é 1500 W.\n") == "A potência é 1500 W.\n"

    verifier.approve("SKU AF-800-220V:\n")
    verifier.approve("- A potência é 1800 W.\n")
    assert verifier.approve("A potência é 1500 W.\n") == "A potência é 1500 W.\n"  # list ended

    verifier.approve("SKU AF-800-220V:\n")
    assert verifier.approve(f"SKU {PRODUCT.sku}:\n") == ""
    assert verifier.approve("- A potência é 1800 W.\n") is None
    assert verifier.approve("- A potência é 1500 W.\n") == f"SKU {PRODUCT.sku}:\n- A potência é 1500 W.\n"


def test_an_unknown_sku_header_blocks_its_whole_block() -> None:
    verifier = _verifier()
    assert verifier.approve("SKU AF-999-220V:\n") is None
    assert verifier.approve("- A potência é 1500 W.\n") is None
    verifier.end_block()
    assert verifier.approve("A potência é 1500 W.") == "A potência é 1500 W."


def test_streamed_alternative_list_is_published_without_the_missing_evidence_notice() -> None:
    from test_orchestrator_recommendations import Recommender
    from test_orchestrator_recommendations import run as run_with_cards

    model = ChatModel([
        "SKU AF-800-220V:\n- A potência é 1800 W.\n- Possui capacidade de 8.0 L.\n",
        "- Preço atual: R$ 799.9.\n- Voltagem: 220V.\n",
    ])
    events = run_with_cards(Catalog(PRODUCT, [chunk()]), model, Recommender([_upgrade_card().model_dump(mode="json")]))
    text = "".join(str(event["data"]["delta"]) for event in events if event["event"] == "token")  # type: ignore[index]
    assert text == (
        "SKU AF-800-220V:\n- A potência é 1800 W.\n- Possui capacidade de 8.0 L.\n"
        "- Preço atual: R$ 799.9.\n- Voltagem: 220V.\n"
    )
    assert "error" not in names(events)


def test_prompt_renders_sql_values_in_pt_br_and_asks_for_prefixed_sentences() -> None:
    from app.generation.prompt import build_messages

    pricey = PRODUCT.model_copy(update={"price": Decimal("1299.90"), "capacity_liters": Decimal("1.5"),
                                        "specs_json": {"altura_cm": 7.5}})
    card = _upgrade_card().model_dump(mode="json")
    system = build_messages(pricey, [chunk()], [], "Tem maior?", history_limit=0,
                            recommendations=[card])[0]["content"]
    catalog = system[system.index("<CATALOGO_SQL>\n"):system.index("</CATALOGO_SQL>")]
    assert "Preço atual: R$ 1.299,90" in catalog
    assert "Capacidade: 1,5 L" in catalog and "Potência: 1500 W" in catalog
    assert "altura_cm: 7,5" in catalog
    options = system[system.index("<RECOMENDACOES_SQL>\n"):system.index("</RECOMENDACOES_SQL>")]
    assert '"price": "R$ 799,90"' in options
    assert '"capacity_liters": "8 L"' in options and '"power_watts": "1800 W"' in options
    assert "799.90" not in options and "8.0" not in options
    assert '"SKU AF-123-220V: A potência é 1200 W."' in system


@pytest.mark.parametrize("answer", [
    "Preço atual: R$ 1.299,90.", "Possui capacidade de 1,5 L.", "A potência é 1500 W.",
])
def test_g_out_accepts_the_pt_br_forms_the_prompt_renders(answer: str) -> None:
    product = PRODUCT.model_copy(update={"price": Decimal("1299.90"), "capacity_liters": Decimal("1.5")})
    assert SentenceVerifier(product, []).approve(answer) == answer
