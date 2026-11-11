"""IT-B01-01 / B03: ingestion_jobs lifecycle, retries and catalog:version (UC08).

Needs TEST_DATABASE_URL (pgvector); the Redis case also needs TEST_REDIS_URL.
"""

import asyncio
import os
from collections.abc import Sequence
from pathlib import Path

import psycopg
import pytest
from app.clients.catalog_version import CATALOG_VERSION_KEY, RedisCatalogVersion
from app.clients.openai_client import LLMUnavailableError
from app.config import Settings
from app.ingestion.run import IngestionReport, ingest
from ingestion_support import DATA_DIR, DATABASE_URL, HashingEmbedder, reset_backend_tables
from redis.asyncio import Redis

REDIS_URL = os.environ.get("TEST_REDIS_URL", "")
MANUAL_SOURCE = "manual:AF-400-220V.txt"
MANUAL_JOB = f"AF-400-220V/{MANUAL_SOURCE}"
SETTINGS = Settings(ingestion_backoff_seconds=0.0)

pytestmark = pytest.mark.skipif(not DATABASE_URL, reason="TEST_DATABASE_URL not set")


class CountingVersion:
    def __init__(self) -> None:
        self.value = 0

    async def bump(self) -> int:
        self.value += 1
        return self.value


class FlakyEmbedder(HashingEmbedder):
    """Fails the first `failures` calls that embed the AF-400 manual (page 14)."""

    def __init__(self, failures: int) -> None:
        super().__init__()
        self.failures = failures

    async def embed(self, texts: Sequence[str]) -> list[list[float]]:
        if self.failures and any("AF-400-220V" in text and "PÁG: 14" in text for text in texts):
            self.failures -= 1
            raise LLMUnavailableError("embedding offline")
        return await super().embed(texts)


async def _jobs(source_file: str) -> list[tuple[str, int, str | None]]:
    async with await psycopg.AsyncConnection.connect(DATABASE_URL) as conn:
        cursor = await conn.execute(
            "SELECT status, attempts, last_error FROM ingestion_jobs WHERE source_file = %s "
            "ORDER BY updated_at",
            (source_file,),
        )
        return [(row[0], row[1], row[2]) for row in await cursor.fetchall()]


async def _chunk_count(sku: str, manual_source: str) -> int:
    async with await psycopg.AsyncConnection.connect(DATABASE_URL) as conn:
        cursor = await conn.execute(
            "SELECT COUNT(*) FROM manual_chunks WHERE sku = %s AND manual_source = %s",
            (sku, manual_source),
        )
        row = await cursor.fetchone()
    return int(row[0]) if row else 0


def _ingest(
    embedder: HashingEmbedder,
    version: CountingVersion | None = None,
    manuals_dir: Path = DATA_DIR / "manuals",
) -> IngestionReport:
    return asyncio.run(
        ingest(
            DATABASE_URL,
            DATA_DIR / "catalog.json",
            manuals_dir,
            embedder,
            SETTINGS,
            catalog_version=version,
        )
    )


def test_it_b01_01_jobs_are_indexed_and_version_is_bumped_once_per_run() -> None:
    asyncio.run(reset_backend_tables())
    embedder, version = HashingEmbedder(), CountingVersion()

    first = _ingest(embedder, version)
    assert asyncio.run(_jobs(MANUAL_JOB)) == [("INDEXED", 1, None)]
    assert first.catalog_version == 1 and first.needs_intervention == []

    calls_before = embedder.calls
    second = _ingest(embedder, version)
    assert embedder.calls == calls_before and second.indexed_sources == []
    assert asyncio.run(_jobs(MANUAL_JOB)) == [("INDEXED", 1, None)]
    assert second.catalog_version == 2  # price and stock of the seed may have changed


def test_ingestion_without_a_version_store_reports_no_version() -> None:
    asyncio.run(reset_backend_tables())
    assert _ingest(HashingEmbedder()).catalog_version is None


def test_failed_source_is_retried_with_the_attempt_count_recorded() -> None:
    asyncio.run(reset_backend_tables())
    report = _ingest(FlakyEmbedder(failures=2))
    assert MANUAL_JOB in report.indexed_sources and report.needs_intervention == []
    assert asyncio.run(_jobs(MANUAL_JOB)) == [("INDEXED", 3, None)]


def test_exhausted_retries_need_intervention_and_keep_the_previous_version(
    tmp_path: Path,
) -> None:
    asyncio.run(reset_backend_tables())
    _ingest(HashingEmbedder())
    indexed_chunks = asyncio.run(_chunk_count("AF-400-220V", MANUAL_SOURCE))

    original = (DATA_DIR / "manuals" / "AF-400-220V.txt").read_text(encoding="utf-8")
    (tmp_path / "AF-400-220V.txt").write_text(original + "\nRevisão 2.", encoding="utf-8")
    report = _ingest(FlakyEmbedder(failures=99), manuals_dir=tmp_path)

    assert report.needs_intervention == [MANUAL_JOB]
    previous, revised = asyncio.run(_jobs(MANUAL_JOB))
    assert previous == ("INDEXED", 1, None)
    assert revised[:2] == ("NEEDS_INTERVENTION", 3) and "embedding offline" in str(revised[2])
    assert asyncio.run(_chunk_count("AF-400-220V", MANUAL_SOURCE)) == indexed_chunks


@pytest.mark.skipif(not REDIS_URL, reason="TEST_REDIS_URL not set")
def test_redis_catalog_version_increments_the_shared_key() -> None:
    async def scenario() -> tuple[int, int, str | None]:
        client = Redis.from_url(REDIS_URL, decode_responses=True)
        try:
            await client.delete(CATALOG_VERSION_KEY)
            bumper = RedisCatalogVersion(REDIS_URL)
            first, second = await bumper.bump(), await bumper.bump()
            return first, second, await client.get(CATALOG_VERSION_KEY)
        finally:
            await client.aclose()

    assert asyncio.run(scenario()) == (1, 2, "2")
