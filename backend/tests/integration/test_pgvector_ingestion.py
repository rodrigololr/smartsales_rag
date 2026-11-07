"""IT-B01/B03: ingestion + cosine search on a real PostgreSQL with pgvector.

Runs only when TEST_DATABASE_URL points to a disposable database, e.g.:
docker run -d -p 5544:5432 -e POSTGRES_USER=smartsales -e POSTGRES_PASSWORD=smartsales \
  -e POSTGRES_DB=smartsales pgvector/pgvector:pg16
TEST_DATABASE_URL=postgresql://smartsales:smartsales@localhost:5544/smartsales
"""

import asyncio
import hashlib
import json
import math
import os
import re
from collections.abc import Sequence
from decimal import Decimal
from pathlib import Path

import psycopg
import pytest
from app.config import Settings
from app.db.repository import PostgresCatalog
from app.ingestion.run import ingest

DATABASE_URL = os.environ.get("TEST_DATABASE_URL", "")
DATA_DIR = Path(__file__).resolve().parents[3] / "data"
DIMENSIONS = 1536

pytestmark = pytest.mark.skipif(not DATABASE_URL, reason="TEST_DATABASE_URL not set")


class HashingEmbedder:
    """Deterministic bag-of-words vectors: shared words => higher cosine similarity."""

    def __init__(self) -> None:
        self.calls = 0

    async def embed(self, texts: Sequence[str]) -> list[list[float]]:
        self.calls += 1
        return [self._vector(text) for text in texts]

    @staticmethod
    def _vector(text: str) -> list[float]:
        vector = [0.0] * DIMENSIONS
        for word in re.findall(r"\w+", text.lower()):
            vector[int(hashlib.md5(word.encode()).hexdigest(), 16) % DIMENSIONS] += 1.0
        norm = math.sqrt(sum(value * value for value in vector)) or 1.0
        return [value / norm for value in vector]


async def _reset() -> None:
    async with await psycopg.AsyncConnection.connect(DATABASE_URL, autocommit=True) as conn:
        await conn.execute("DROP TABLE IF EXISTS manual_chunks, products CASCADE")


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
