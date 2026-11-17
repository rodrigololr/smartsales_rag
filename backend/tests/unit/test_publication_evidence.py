"""B03: verify SQL facts and the actual cited evidence before publishing a sentence."""

import pytest
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
