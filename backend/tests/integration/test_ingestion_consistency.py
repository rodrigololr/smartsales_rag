"""B03 regressions: complete manual versions under failure and concurrent publication."""

import asyncio
import hashlib
import json
from collections.abc import Sequence
from pathlib import Path

import psycopg
import pytest
from app.config import Settings
from app.db.repository import ChunkRow, apply_schema, replace_manual_chunks, upsert_product
from app.ingestion.run import ingest, load_catalog, sources_for
from ingestion_support import DATA_DIR, DATABASE_URL, HashingEmbedder, reset_backend_tables

pytestmark = pytest.mark.skipif(not DATABASE_URL, reason="TEST_DATABASE_URL not set")
SKU = "AF-400-220V"
SOURCE = f"manual:{SKU}.txt"
JOB = f"{SKU}/{SOURCE}"


async def versions() -> list[str]:
    async with await psycopg.AsyncConnection.connect(DATABASE_URL) as conn:
        cursor = await conn.execute(
            "SELECT DISTINCT manual_version FROM manual_chunks WHERE sku = %s AND manual_source = %s",
            (SKU, SOURCE),
        )
        return [row[0] for row in await cursor.fetchall()]


def test_empty_replacement_keeps_the_previous_manual_and_needs_intervention(tmp_path: Path) -> None:
    asyncio.run(reset_backend_tables())
    arguments = (DATABASE_URL, DATA_DIR / "catalog.json")
    asyncio.run(ingest(*arguments, DATA_DIR / "manuals", HashingEmbedder(), Settings()))
    previous = asyncio.run(versions())
    (tmp_path / f"{SKU}.txt").write_text(" \n\f \n", encoding="utf-8")
    report = asyncio.run(ingest(*arguments, tmp_path, HashingEmbedder(), Settings()))
    assert report.needs_intervention == [JOB]
    assert asyncio.run(versions()) == previous


def test_manual_hash_and_pages_come_from_the_same_bytes(tmp_path: Path) -> None:
    product = next(product for product in load_catalog(DATA_DIR / "catalog.json") if product.sku == SKU)
    manual = tmp_path / f"{SKU}.txt"
    original = b"First revision"
    manual.write_bytes(original)
    source = sources_for(product, tmp_path)[1]
    manual.write_bytes(b"Second revision")
    assert source.version == hashlib.sha256(original).hexdigest()
    assert source.load_pages() == [original.decode()]


async def wait_for_writer_lock(pid: int) -> None:
    async with await psycopg.AsyncConnection.connect(DATABASE_URL, autocommit=True) as observer:
        async with asyncio.timeout(3):
            while True:
                cursor = await observer.execute(
                    "SELECT wait_event_type FROM pg_stat_activity WHERE pid = %s", (pid,)
                )
                row = await cursor.fetchone()
                if row and row[0] == "Lock":
                    return
                await asyncio.sleep(0.01)


def test_concurrent_replacements_never_mix_manual_versions() -> None:
    async def scenario() -> None:
        await reset_backend_tables()
        async with await psycopg.AsyncConnection.connect(DATABASE_URL, autocommit=True) as first:
            await apply_schema(first)
            product = load_catalog(DATA_DIR / "catalog.json")[0]
            product_id = await upsert_product(first, product)

            async def publish(conn: psycopg.AsyncConnection[object], page: int, revision: str) -> None:
                await replace_manual_chunks(
                    conn, product_id=product_id, sku=SKU, manual_source=SOURCE,
                    manual_version=revision * 64,
                    rows=[ChunkRow(page, 0, revision, [1.0] + [0.0] * 1535, "Manual")],
                )

            await publish(first, 3, "0")
            async with await psycopg.AsyncConnection.connect(DATABASE_URL, autocommit=True) as second:
                async with first.transaction():
                    await publish(first, 1, "a")
                    writer = asyncio.create_task(publish(second, 2, "b"))
                    try:
                        await wait_for_writer_lock(second.info.backend_pid)
                    except BaseException:
                        writer.cancel()
                        await asyncio.gather(writer, return_exceptions=True)
                        raise
                await asyncio.wait_for(writer, 3)
        assert await versions() == ["b" * 64]

    asyncio.run(scenario())


def test_second_ingestion_cannot_mutate_catalog_while_the_first_run_is_active(tmp_path: Path) -> None:
    catalog = tmp_path / "catalog.json"
    product = load_catalog(DATA_DIR / "catalog.json")[0]
    catalog.write_text(json.dumps([product.model_dump(mode="json")]), encoding="utf-8")

    async def scenario() -> None:
        await reset_backend_tables()
        started, release = asyncio.Event(), asyncio.Event()

        class PausedEmbedder(HashingEmbedder):
            async def embed(self, texts: Sequence[str]) -> list[list[float]]:
                started.set()
                await release.wait()
                return await super().embed(texts)

        first = asyncio.create_task(
            ingest(DATABASE_URL, catalog, tmp_path, PausedEmbedder(), Settings())
        )
        try:
            await asyncio.wait_for(started.wait(), 3)
            with pytest.raises(RuntimeError, match="ingestion.*running"):
                await ingest(DATABASE_URL, catalog, tmp_path, HashingEmbedder(), Settings())
        finally:
            release.set()
            await asyncio.wait_for(first, 3)
        # Closing the connection releases the lock: the next run is accepted.
        report = await ingest(DATABASE_URL, catalog, tmp_path, HashingEmbedder(), Settings())
        assert not report.needs_intervention

    asyncio.run(scenario())
