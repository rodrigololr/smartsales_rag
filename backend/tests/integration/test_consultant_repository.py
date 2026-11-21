"""IT-P2: PostgresConsultantCatalog against real pgvector (search, stock, voltage, games, KB)."""

import asyncio
from decimal import Decimal

import psycopg
import pytest
from app.config import Settings
from app.consultant.evidence import kb_measure, kb_sentence, parse_game_rows
from app.consultant.knowledge_facts import (
    KB_GTA6_NO_PC,
    KB_GTA6_PLATFORMS,
    KB_GTA_RP,
    KB_SOFA_CLEARANCE,
    KB_TWITCH_FPS,
    KB_TWITCH_HEIGHT,
)
from app.db.consultant_repository import (
    CatalogQuery,
    ConsultantLookupError,
    PostgresConsultantCatalog,
)
from app.ingestion.run import ingest
from ingestion_support import DATA_DIR, DATABASE_URL, HashingEmbedder, reset_backend_tables

pytestmark = pytest.mark.skipif(not DATABASE_URL, reason="TEST_DATABASE_URL not set")

CATALOG_PATHS = [DATA_DIR / "catalog.json", DATA_DIR / "catalog_consultor.json"]
RELATION_PATHS = [
    DATA_DIR / "product_relations.json",
    DATA_DIR / "product_relations_consultor.json",
]
KNOWLEDGE_DIR = DATA_DIR / "knowledge"


async def _seed_all(embedder: HashingEmbedder) -> None:
    await reset_backend_tables()
    async with await psycopg.AsyncConnection.connect(DATABASE_URL, autocommit=True) as conn:
        await conn.execute("DROP TABLE IF EXISTS knowledge_chunks CASCADE")
    report = await ingest(
        DATABASE_URL,
        CATALOG_PATHS,
        DATA_DIR / "manuals",
        embedder,
        Settings(),
        relations_path=RELATION_PATHS,
        knowledge_dir=KNOWLEDGE_DIR,
    )
    assert not report.needs_intervention


def test_consultant_repository_search_filters_stock_voltage_and_ordering() -> None:
    embedder = HashingEmbedder()
    asyncio.run(_seed_all(embedder))
    repo = PostgresConsultantCatalog(DATABASE_URL)

    # 1. products() preserves input order and includes sold-out active items (NB-NX17-BIV)
    fetched = asyncio.run(repo.products(["NB-NX17-BIV", "PC-VX5-BIV", "PC-VX3-BIV", "UNKNOWN"]))
    assert [p.sku for p in fetched] == ["NB-NX17-BIV", "PC-VX5-BIV", "PC-VX3-BIV"]
    assert fetched[0].stock_quantity == 0

    # 2. search() filters out sold-out items (R03: NB-NX17-BIV excluded) and orders by price, sku
    notebooks = asyncio.run(
        repo.search(
            CatalogQuery(
                categories=("Computadores",),
                subcategories=("Notebooks Gamer",),
            )
        )
    )
    assert [p.sku for p in notebooks] == ["NB-NX15-BIV", "NB-NX16-BIV"]

    # 3. search() budget_max and voltage filter (127V includes BIVOLT and excludes 220V-only PCs)
    pcs_127v = asyncio.run(
        repo.search(
            CatalogQuery(
                categories=("Computadores",),
                subcategories=("PCs Gamer",),
                voltage="127V",
            )
        )
    )
    assert [p.sku for p in pcs_127v] == ["PC-VX3-BIV", "PC-VX5-BIV"]

    pcs_budget = asyncio.run(
        repo.search(
            CatalogQuery(
                categories=("Computadores",),
                subcategories=("PCs Gamer",),
                budget_max=Decimal("5000.00"),
                voltage="220V",
            )
        )
    )
    assert [p.sku for p in pcs_budget] == ["PC-VX3-BIV", "PC-VX5-BIV"]

    # 4. N/A voltage products (Webcams, Sofás) pass voltage filter
    webcams = asyncio.run(
        repo.search(
            CatalogQuery(
                categories=("Periféricos",),
                subcategories=("Webcams",),
                voltage="127V",
            )
        )
    )
    assert [p.sku for p in webcams] == ["WC-1080-01", "WC-1080-60", "WC-2K-60"]

    # 5. categories_in_stock() returns sorted (category, subcategory) pairs with stock > 0
    categories = asyncio.run(repo.categories_in_stock())
    assert ("Computadores", "PCs Gamer") in categories
    assert ("Computadores", "Notebooks Gamer") in categories
    assert ("Monitores", "Monitores Gamer") in categories
    assert ("Móveis", "Sofás") in categories


def test_consultant_repository_game_tables_and_knowledge_queries() -> None:
    embedder = HashingEmbedder()
    asyncio.run(_seed_all(embedder))
    repo = PostgresConsultantCatalog(DATABASE_URL)

    # 1. game_tables() lexical lookup
    game_chunks = asyncio.run(repo.game_tables(["PC-VX3-BIV", "PC-VX7-220V"]))
    assert {c.sku for c in game_chunks} == {"PC-VX3-BIV", "PC-VX7-220V"}
    for chunk in game_chunks:
        assert chunk.similarity_score == 1.0
        rows = parse_game_rows(chunk)
        assert {r.game for r in rows} >= {"Roblox", "GTA V", "Fortnite", "Counter-Strike 2"}

    # 2. knowledge_doc() and knowledge_page()
    gta6_chunks = asyncio.run(repo.knowledge_doc("KB-GTA6-PLATAFORMAS"))
    assert gta6_chunks and all(c.sku == "KB-GTA6-PLATAFORMAS" for c in gta6_chunks)
    assert kb_sentence(gta6_chunks, KB_GTA6_PLATFORMS) is not None
    assert kb_sentence(gta6_chunks, KB_GTA6_NO_PC) is not None

    gta6_p1 = asyncio.run(repo.knowledge_page("KB-GTA6-PLATAFORMAS", 1))
    assert gta6_p1 and all(c.page_number == 1 for c in gta6_p1)

    rp_chunks = asyncio.run(repo.knowledge_doc("KB-GTA-RP"))
    assert kb_sentence(rp_chunks, KB_GTA_RP) is not None

    twitch_chunks = asyncio.run(repo.knowledge_doc("KB-TWITCH-TRANSMISSAO"))
    height = kb_measure(twitch_chunks, KB_TWITCH_HEIGHT)
    fps = kb_measure(twitch_chunks, KB_TWITCH_FPS)
    assert height is not None and height.value == Decimal("1080")
    assert fps is not None and fps.value == Decimal("60")

    sofa_chunks = asyncio.run(repo.knowledge_doc("KB-SOFA-ESPACO"))
    clearance = kb_measure(sofa_chunks, KB_SOFA_CLEARANCE)
    assert clearance is not None and clearance.value == Decimal("10")

    # 3. search_knowledge() cosine similarity vector search
    [query_vec] = asyncio.run(embedder.embed(["Requisitos do Roblox para PC Windows 10 RAM"]))
    kb_hits = asyncio.run(repo.search_knowledge(query_vec, limit=3))
    assert len(kb_hits) == 3
    assert kb_hits[0].sku == "KB-ROBLOX-REQUISITOS"
    assert kb_hits[0].similarity_score >= kb_hits[1].similarity_score

    # 4. Connection failure raises ConsultantLookupError
    broken = PostgresConsultantCatalog("postgresql://invalid:invalid@127.0.0.1:1/invalid")
    with pytest.raises(ConsultantLookupError):
        asyncio.run(broken.categories_in_stock())
