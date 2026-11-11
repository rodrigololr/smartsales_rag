"""IT-B01/B03: ingestion + cosine search on a real PostgreSQL with pgvector.

Runs only when TEST_DATABASE_URL points to a disposable database, e.g.:
docker run -d -p 5544:5432 -e POSTGRES_USER=smartsales -e POSTGRES_PASSWORD=smartsales \
  -e POSTGRES_DB=smartsales pgvector/pgvector:pg16
TEST_DATABASE_URL=postgresql://smartsales:smartsales@localhost:5544/smartsales
"""

import asyncio
import json
from decimal import Decimal
from pathlib import Path

import psycopg
import pytest
from app.config import Settings
from app.db.repository import PostgresCatalog
from app.ingestion.run import ingest
from ingestion_support import DATA_DIR, DATABASE_URL, HashingEmbedder
from ingestion_support import reset_backend_tables as _reset

pytestmark = pytest.mark.skipif(not DATABASE_URL, reason="TEST_DATABASE_URL not set")


async def _relation_rows() -> list[tuple[str, str, str, Decimal]]:
    async with await psycopg.AsyncConnection.connect(DATABASE_URL) as conn:
        cursor = await conn.execute(
            """
            SELECT base.sku, related.sku, relation.relation_type, relation.affinity_weight
            FROM product_relations relation
            JOIN products base ON base.id = relation.base_product_id
            JOIN products related ON related.id = relation.related_product_id
            ORDER BY base.sku, related.sku
            """
        )
        return [(row[0], row[1], row[2], row[3]) for row in await cursor.fetchall()]


async def _table_exists(name: str) -> bool:
    async with await psycopg.AsyncConnection.connect(DATABASE_URL) as conn:
        cursor = await conn.execute("SELECT to_regclass(%s)", (name,))
        row = await cursor.fetchone()
    return row is not None and row[0] is not None


def test_ingestion_creates_backend_tables_and_replaces_relations_from_the_seed(
    tmp_path: Path,
) -> None:
    asyncio.run(_reset())
    embedder = HashingEmbedder()
    catalog_path = DATA_DIR / "catalog.json"
    relations_path = DATA_DIR / "product_relations.json"

    report = asyncio.run(
        ingest(
            DATABASE_URL,
            catalog_path,
            DATA_DIR / "manuals",
            embedder,
            Settings(),
            relations_path=relations_path,
        )
    )
    assert asyncio.run(_table_exists("ingestion_jobs"))
    rows = asyncio.run(_relation_rows())
    assert report.relations == len(rows) == 5
    assert ("AF-400-220V", "KIT-SIL-01", "CROSS_SELL", Decimal("0.950")) in rows

    only_one = tmp_path / "product_relations.json"
    seed = json.loads(relations_path.read_text(encoding="utf-8"))
    only_one.write_text(json.dumps(seed[:1]), encoding="utf-8")
    asyncio.run(
        ingest(
            DATABASE_URL,
            catalog_path,
            DATA_DIR / "manuals",
            embedder,
            Settings(),
            relations_path=only_one,
        )
    )
    assert asyncio.run(_relation_rows()) == [
        ("AF-400-220V", "KIT-SIL-01", "CROSS_SELL", Decimal("0.950"))
    ]


def test_ingestion_indexes_catalog_and_manuals_then_search_stays_on_the_product(
    tmp_path: Path,
) -> None:
    asyncio.run(_reset())
    embedder = HashingEmbedder()
    catalog_path = DATA_DIR / "catalog.json"

    report = asyncio.run(
        ingest(DATABASE_URL, catalog_path, DATA_DIR / "manuals", embedder, Settings())
    )
    assert report.products == 7
    assert "AF-400-220V/manual:AF-400-220V.txt" in report.indexed_sources
    assert "AF-400-220V/catalog:spec_sheet" in report.indexed_sources
    assert "KIT-SIL-01" in report.products_without_manual

    catalog = PostgresCatalog(DATABASE_URL)
    product = asyncio.run(catalog.get_product("AF-400-220V"))
    assert product is not None and product.price == Decimal("499.90")

    question = "Posso usar formas de silicone e papel manteiga no cesto?"
    [query] = asyncio.run(embedder.embed([question]))
    found = asyncio.run(catalog.search("AF-400-220V", query, 5))
    assert found and {chunk.sku for chunk in found} == {"AF-400-220V"}
    assert found[0].page_number == 14
    assert found[0].content.startswith("[PRODUTO: Airfryer SmartChef 4L | SKU: AF-400-220V")
    assert [c.similarity_score for c in found] == sorted(
        (c.similarity_score for c in found), reverse=True
    )

    calls_before = embedder.calls
    rerun = asyncio.run(
        ingest(DATABASE_URL, catalog_path, DATA_DIR / "manuals", embedder, Settings())
    )
    assert rerun.indexed_sources == [] and embedder.calls == calls_before

    smaller = tmp_path / "catalog.json"
    rows = json.loads(catalog_path.read_text(encoding="utf-8"))
    smaller.write_text(json.dumps([r for r in rows if r["sku"] != "CF-15B-127V"]), encoding="utf-8")
    removed = asyncio.run(ingest(DATABASE_URL, smaller, DATA_DIR / "manuals", embedder, Settings()))
    assert removed.deactivated == 1
    gone = asyncio.run(catalog.get_product("CF-15B-127V"))
    assert gone is not None and not gone.is_active
    assert asyncio.run(catalog.search("CF-15B-127V", query, 5)) == []
