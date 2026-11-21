"""UT-CU-17: pure lexical evidence extractors for manuals and knowledge base chunks."""

import logging
from decimal import Decimal
from uuid import uuid4

import pytest
from app.consultant.evidence import (
    GameRow,
    KbMeasure,
    kb_measure,
    kb_sentence,
    parse_game_rows,
    webcam_capability,
)
from app.consultant.knowledge_facts import (
    KB_GTA6_NO_PC,
    KB_GTA6_PLATFORMS,
    KB_SOFA_CLEARANCE,
    KB_TWITCH_FPS,
    KB_TWITCH_HEIGHT,
)
from app.models.schemas import CatalogProduct, RetrievedChunk


def _chunk(sku: str, title: str, page: int, body: str) -> RetrievedChunk:
    return RetrievedChunk(
        chunk_id=uuid4(),
        sku=sku,
        manual_title=title,
        page_number=page,
        content=body,
        similarity_score=1.0,
    )


def test_ut_cu_17_parse_game_rows_skips_header_and_malformed_lines() -> None:
    manual = _chunk(
        "PC-VX3-BIV",
        "Manual PC Gamer Vortex X3",
        4,
        (
            "[PRODUTO: PC Gamer Vortex X3 | SKU: PC-VX3-BIV | MANUAL PÁG: 4]\n"
            "## Desempenho em jogos\n"
            "| Jogo | Resolução | Predefinição | Desempenho médio |\n"
            "| --- | --- | --- | --- |\n"
            "| Roblox | 1080p | Alto | 160 fps |\n"
            "| GTA V | 1080p | Muito alto | 75 fps |\n"
            "| Linha malformada | FullHD | Alto | rápido |\n"
            "| Fortnite | 1080p | Médio | 90 fps |\n"
            "Valores medidos pelo fabricante em ambiente de teste."
        ),
    )
    rows = parse_game_rows(manual)
    assert rows == [
        GameRow(game="Roblox", resolution="1080p", preset="Alto", fps=160, chunk=manual),
        GameRow(game="GTA V", resolution="1080p", preset="Muito alto", fps=75, chunk=manual),
        GameRow(game="Fortnite", resolution="1080p", preset="Médio", fps=90, chunk=manual),
    ]


def test_ut_cu_17_kb_measure_parses_structured_markdown_rows() -> None:
    twitch = _chunk(
        "KB-TWITCH-TRANSMISSAO",
        "Twitch qualidade de transmissão",
        1,
        (
            "[BASE DE CONHECIMENTO: Twitch qualidade de transmissão | PÁG: 1]\n"
            "| Altura máxima de vídeo recomendada | 1080 px |\n"
            "| Taxa de quadros máxima recomendada | 60 fps |\n"
        ),
    )
    sofa = _chunk(
        "KB-SOFA-ESPACO",
        "Sofá espaço necessário no ambiente",
        1,
        "| Folga lateral mínima por lado | 10 cm |\n",
    )
    assert kb_measure([twitch], KB_TWITCH_HEIGHT) == KbMeasure(
        value=Decimal("1080"), unit="px", chunk=twitch
    )
    assert kb_measure([twitch], KB_TWITCH_FPS.text) == KbMeasure(
        value=Decimal("60"), unit="fps", chunk=twitch
    )
    assert kb_measure([sofa], KB_SOFA_CLEARANCE) == KbMeasure(
        value=Decimal("10"), unit="cm", chunk=sofa
    )
    assert kb_measure([sofa], "Rótulo inexistente") is None


def test_ut_cu_17_kb_sentence_is_fail_closed_and_normalizes_whitespace(
    caplog: pytest.LogCaptureFixture,
) -> None:
    gta6 = _chunk(
        "KB-GTA6-PLATAFORMAS",
        "GTA 6 plataformas e versão para PC",
        1,
        (
            "GTA 6   foi lançado em 19/11/2026 para PlayStation 5 e Xbox Series X|S.\n"
            "Não há versão de GTA 6 para PC anunciada até a data de atualização desta base."
        ),
    )
    assert kb_sentence([gta6], KB_GTA6_PLATFORMS) == gta6
    assert kb_sentence([gta6], KB_GTA6_NO_PC.text) == gta6

    with caplog.at_level(logging.WARNING, logger="app.consultant.evidence"):
        missing = kb_sentence([gta6], "Sentença que não existe na base curada.")
    assert missing is None
    assert any("kb_sentence_missing" in record.getMessage() for record in caplog.records)


def test_ut_cu_17_webcam_capability_supports_tuple_and_product() -> None:
    assert webcam_capability("1920 x 1080", 30) == (1080, 30)
    assert webcam_capability("2560 x 1440", 60) == (1440, 60)
    assert webcam_capability("invalida", 30) is None
    assert webcam_capability("1920 x 1080", None) is None

    webcam = CatalogProduct(
        sku="WC-1080-01",
        name="Webcam Cliqon View Full HD",
        category="Periféricos",
        subcategory="Webcams",
        brand="Cliqon",
        price=Decimal("189.90"),
        stock_quantity=17,
        voltage="N/A",
        image_url="/images/wc.svg",
        checkout_url="https://example.com/wc",
        specs_json={"resolucao": "1920 x 1080", "fps": 30},
    )
    assert webcam_capability(webcam) == (1080, 30)
