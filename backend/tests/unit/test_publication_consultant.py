"""UT-CU-18: opt-in G-OUT extensions (Informação geral, user-echoed lengths, KB SentenceVerifier)."""

from decimal import Decimal
from uuid import uuid4

import pytest
from app.consultant.builders import FIXED_GENERAL_INFORMATION
from app.guardrails.publication import (
    CATALOG_MISSING_NOTICE,
    GENERAL_INFORMATION_MAX,
    GENERAL_INFORMATION_PREFIX,
    ConsultativeVerifier,
    SentenceVerifier,
    _PublicationGate,
    general_information,
)
from app.models.schemas import CatalogProduct, RetrievedChunk

PC_X3 = CatalogProduct(
    sku="PC-VX3-BIV",
    name="PC Gamer Vortex X3",
    category="Computadores",
    subcategory="PCs Gamer",
    brand="Vortex",
    price=Decimal("3499.00"),
    stock_quantity=7,
    voltage="BIVOLT",
    power_watts=500,
    tier_rank=1,
    image_url="/images/pc-vx3-biv.svg",
    checkout_url="https://example.com/pc-vx3",
)


def _kb_chunk(doc_id: str, title: str, page: int, body: str) -> RetrievedChunk:
    return RetrievedChunk(
        chunk_id=uuid4(),
        sku=doc_id,
        manual_title=title,
        page_number=page,
        content=f"[BASE DE CONHECIMENTO: {title} | PÁG: {page}]\n{body}",
        similarity_score=0.91,
    )


@pytest.mark.parametrize("constant", FIXED_GENERAL_INFORMATION)
def test_ut_cu_18_every_fixed_general_information_constant_passes(constant: str) -> None:
    assert general_information(constant)
    assert general_information(f"- {constant}")


@pytest.mark.parametrize(
    "sentence",
    [
        "Informação geral: o desempenho real varia com drivers e configurações gráficas.",
        "- Informação geral: confira também o caminho até a sala, como portas e corredores.",
    ],
)
def test_ut_cu_18_general_information_approves_qualitative_guidance(sentence: str) -> None:
    assert general_information(sentence)


@pytest.mark.parametrize(
    "sentence",
    [
        "O desempenho real varia com drivers.",  # missing prefix
        f"{GENERAL_INFORMATION_PREFIX}   ",  # empty body
        "Informação geral: precisa de 16 GB de memória.",  # digit
        "Informação geral: funciona em 127V.",  # digit + voltage
        "Informação geral: verifique a voltagem da tomada.",  # voltage word
        "Informação geral: a potência influencia o consumo.",  # power word
        "Informação geral: o preço varia bastante.",  # price word
        "Informação geral: custa pouco.",  # custa
        "Informação geral: confira os litros do reservatório.",  # unit word
        "Informação geral: a garantia cobre defeitos.",  # garantia
        "Informação geral: mais fps melhora a fluidez.",  # fps
        "Informação geral: a resolução define a nitidez.",  # resolucao
        "Informação geral: veja os requisitos do sistema.",  # requisitos
        "Informação geral: o modelo é compatível.",  # compativel
        "Informação geral: a marca mais confiável do mercado.",  # confiavel
        "Informação geral: a melhor marca para jogos.",  # melhor marca
        "Informação geral: o SKU PC-VX3-BIV atende bem.",  # SKU
        "Informação geral: segundo o guia [Fonte: Guia, p. 1].",  # citation
    ],
)
def test_ut_cu_18_general_information_rejects_numbers_units_skus_and_rankings(
    sentence: str,
) -> None:
    assert not general_information(sentence)


def test_ut_cu_18_general_information_is_opt_in_and_capped_at_two_per_answer() -> None:
    s1 = f"{FIXED_GENERAL_INFORMATION[0]}\n"
    s2 = f"{FIXED_GENERAL_INFORMATION[1]}\n"
    s3 = f"{FIXED_GENERAL_INFORMATION[2]}\n"

    # Opt-in disabled by default (RAGAS / TECHNICAL path)
    default_verifier = ConsultativeVerifier(PC_X3, [], [])
    assert default_verifier.approve(s1) is None

    # Opt-in enabled (KB_QA path): capped at GENERAL_INFORMATION_MAX == 2
    assert GENERAL_INFORMATION_MAX == 2
    kb_verifier = ConsultativeVerifier(None, [], [PC_X3], allow_general_information=True)
    gate = _PublicationGate(kb_verifier, "KB_QA", notice=CATALOG_MISSING_NOTICE)
    assert gate.review(s1) == [s1]
    assert gate.review(s2) == [s2]
    assert gate.review(s3) == []


def test_ut_cu_18_user_echoed_lengths_approved_only_when_matching_and_never_for_voltage() -> None:
    verifier = ConsultativeVerifier(
        None,
        [],
        [PC_X3],
        allow_general_information=True,
        user_message="Minha sala tem 2 metros e tomada 127V.",
    )
    assert verifier.approve("Você informou 200 cm.") == "Você informou 200 cm."
    assert verifier.approve("Sua sala tem 2 metros.") == "Sua sala tem 2 metros."
    # Different measure not stated by the user
    assert verifier.approve("Você informou 250 cm.") is None
    # Extra numeral outside length measure
    assert verifier.approve("Você informou 200 cm para 3 lugares.") is None
    # No reference to user ("você", "sua", "seu", "informado")
    assert verifier.approve("O sofá tem 200 cm.") is None
    # Voltage is never echoable even if the user said 127V
    assert verifier.approve("Você informou 127V.") is None
    assert verifier.approve("Sua tomada é de 127 V.") is None


def test_ut_cu_18_sentence_verifier_none_product_supports_kb_citations_and_shown_options() -> None:
    kb = _kb_chunk(
        "KB-ROBLOX-REQUISITOS",
        "Requisitos do Roblox para PC",
        1,
        "A Roblox recomenda pelo menos 1 GB de RAM no Windows 10 ou 11.",
    )
    verifier = ConsultativeVerifier(
        None,
        [kb],
        [PC_X3],
        allow_general_information=True,
    )
    cited = (
        "A Roblox recomenda pelo menos 1 GB de RAM no Windows 10 ou 11 "
        "[Fonte: Requisitos do Roblox para PC, p. 1]."
    )
    assert verifier.approve(cited) == cited
    assert verifier.cited_chunk_ids == {kb.chunk_id}

    # Uncited literal KB extract gets its KB citation automatically
    uncited = "A Roblox recomenda pelo menos 1 GB de RAM no Windows 10 ou 11."
    assert SentenceVerifier(None, [kb]).approve(uncited) == cited

    # Shown CatalogProduct facts can be anchored via "SKU <code>:"
    assert (
        verifier.approve("SKU PC-VX3-BIV: Preço atual: R$ 3.499,00.")
        == "SKU PC-VX3-BIV: Preço atual: R$ 3.499,00."
    )
    assert verifier.approve("SKU PC-VX3-BIV: Preço atual: R$ 1.999,00.") is None
