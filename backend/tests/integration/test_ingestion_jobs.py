"""IT-B01-01 / B03: ingestion_jobs lifecycle, retries and catalog:version (UC08).

Needs TEST_DATABASE_URL (pgvector); the Redis case also needs TEST_REDIS_URL.
"""

import asyncio
import os
from collections.abc import Sequence
from pathlib import Path

import app.ingestion.run as ingestion_run
import httpx
import openai
import psycopg
import pytest
from app.clients.catalog_version import (
    CATALOG_VERSION_KEY,
    CatalogVersionBumper,
    CatalogVersionUnavailableError,
    RedisCatalogVersion,
)
from app.clients.openai_client import LLMUnavailableError
from app.config import Settings, get_settings
from app.db.repository import acquire_ingestion_lock, apply_schema
from app.ingestion.run import IngestionReport, ingest
from ingestion_support import DATA_DIR, DATABASE_URL, HashingEmbedder, reset_backend_tables
from redis.asyncio import Redis

REDIS_URL = os.environ.get("TEST_REDIS_URL", "")
UNREACHABLE_REDIS_URL = "redis://127.0.0.1:1/0"
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


class UnavailableVersion:
    async def bump(self) -> int:
        raise CatalogVersionUnavailableError("redis offline")


class FlakyEmbedder(HashingEmbedder):
    """Fails the first `failures` calls that embed the AF-400 manual (page 14).

    Without `error` it fails like OpenAIEmbedder: a message-less LLMUnavailableError
    chained to the transport error.
    """

    def __init__(self, failures: int, error: Exception | None = None) -> None:
        super().__init__()
        self.failures = failures
        self.error = error

    async def embed(self, texts: Sequence[str]) -> list[list[float]]:
        if self.failures and any("AF-400-220V" in text and "PÁG: 14" in text for text in texts):
            self.failures -= 1
            if self.error is not None:
                raise self.error
            transport_error = openai.APIConnectionError(request=httpx.Request("POST", "http://llm"))
            raise LLMUnavailableError from transport_error
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
    version: CatalogVersionBumper | None = None,
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
    assert revised[:2] == ("NEEDS_INTERVENTION", 3) and "APIConnectionError" in str(revised[2])
    assert asyncio.run(_chunk_count("AF-400-220V", MANUAL_SOURCE)) == indexed_chunks


@pytest.mark.skipif(not REDIS_URL, reason="TEST_REDIS_URL not set")
def test_redis_catalog_version_increments_the_shared_key() -> None:
    async def scenario() -> tuple[int, int, str | None]:
        client = Redis.from_url(REDIS_URL, decode_responses=True)
        try:
            await client.delete(CATALOG_VERSION_KEY)
            bumper = RedisCatalogVersion(REDIS_URL, connect_timeout_seconds=1.0)
            first, second = await bumper.bump(), await bumper.bump()
            return first, second, await client.get(CATALOG_VERSION_KEY)
        finally:
            await client.aclose()

    assert asyncio.run(scenario()) == (1, 2, "2")


def test_non_retryable_error_marks_the_job_and_the_run_goes_on() -> None:
    asyncio.run(reset_backend_tables())
    version = CountingVersion()
    report = _ingest(FlakyEmbedder(failures=99, error=RuntimeError("bad api key")), version)

    assert report.needs_intervention == [MANUAL_JOB]
    assert asyncio.run(_jobs(MANUAL_JOB)) == [("NEEDS_INTERVENTION", 1, "RuntimeError('bad api key')")]
    assert len(report.indexed_sources) > 1 and report.catalog_version == 1


def test_transient_database_error_is_retried() -> None:
    asyncio.run(reset_backend_tables())
    report = _ingest(FlakyEmbedder(failures=1, error=psycopg.errors.DeadlockDetected("deadlock")))

    assert report.needs_intervention == []
    assert asyncio.run(_jobs(MANUAL_JOB)) == [("INDEXED", 2, None)]


def test_permanent_database_error_goes_to_intervention_without_retries() -> None:
    asyncio.run(reset_backend_tables())
    error = psycopg.errors.IntegrityError("duplicate key")
    report = _ingest(FlakyEmbedder(failures=99, error=error))

    assert report.needs_intervention == [MANUAL_JOB]
    ((status, attempts, last_error),) = asyncio.run(_jobs(MANUAL_JOB))
    assert (status, attempts) == ("NEEDS_INTERVENTION", 1) and "IntegrityError" in str(last_error)


def test_corrupted_pdf_becomes_a_job_needing_intervention(tmp_path: Path) -> None:
    asyncio.run(reset_backend_tables())
    (tmp_path / "AF-400-220V.pdf").write_bytes(b"not a pdf")
    report = _ingest(HashingEmbedder(), manuals_dir=tmp_path)

    pdf_job = "AF-400-220V/manual:AF-400-220V.pdf"
    assert report.needs_intervention == [pdf_job]
    ((status, attempts, last_error),) = asyncio.run(_jobs(pdf_job))
    assert (status, attempts) == ("NEEDS_INTERVENTION", 1) and last_error
    assert "AF-400-220V/catalog:spec_sheet" in report.indexed_sources


def test_run_that_dies_midway_still_bumps_the_version(monkeypatch: pytest.MonkeyPatch) -> None:
    asyncio.run(reset_backend_tables())

    async def database_gone(*_: object) -> int:
        raise psycopg.OperationalError("connection lost")

    monkeypatch.setattr(ingestion_run, "deactivate_missing", database_gone)
    version = CountingVersion()
    with pytest.raises(psycopg.OperationalError):
        _ingest(HashingEmbedder(), version)
    assert version.value == 1  # products and chunks were already committed


def test_chunks_and_indexed_status_are_committed_together(monkeypatch: pytest.MonkeyPatch) -> None:
    asyncio.run(reset_backend_tables())
    finish = ingestion_run.finish_ingestion_job

    async def failing_on_indexed(conn: psycopg.AsyncConnection[object], **job: object) -> None:
        if job["source_file"] == MANUAL_JOB and job["status"] == "INDEXED":
            raise RuntimeError("died before INDEXED")
        await finish(conn, **job)  # type: ignore[arg-type]

    monkeypatch.setattr(ingestion_run, "finish_ingestion_job", failing_on_indexed)
    _ingest(HashingEmbedder())
    assert asyncio.run(_chunk_count("AF-400-220V", MANUAL_SOURCE)) == 0

    monkeypatch.undo()
    assert MANUAL_JOB in _ingest(HashingEmbedder()).indexed_sources
    assert asyncio.run(_jobs(MANUAL_JOB)) == [("INDEXED", 1, None)]


def test_unavailable_version_store_is_reported_without_losing_the_report() -> None:
    asyncio.run(reset_backend_tables())
    report = _ingest(HashingEmbedder(), UnavailableVersion())
    assert report.indexed_sources and report.catalog_version is None
    assert report.catalog_version_error is not None and "redis offline" in report.catalog_version_error


def test_fixed_file_closes_the_job_of_the_broken_version(tmp_path: Path) -> None:
    asyncio.run(reset_backend_tables())
    _ingest(FlakyEmbedder(failures=99))
    assert [job[0] for job in asyncio.run(_jobs(MANUAL_JOB))] == ["NEEDS_INTERVENTION"]

    original = (DATA_DIR / "manuals" / "AF-400-220V.txt").read_text(encoding="utf-8")
    (tmp_path / "AF-400-220V.txt").write_text(original + "\nRevisão 2.", encoding="utf-8")
    _ingest(HashingEmbedder(), manuals_dir=tmp_path)
    assert asyncio.run(_jobs(MANUAL_JOB)) == [("INDEXED", 1, None)]


def test_attempts_restart_on_each_run() -> None:
    asyncio.run(reset_backend_tables())
    _ingest(FlakyEmbedder(failures=99))
    _ingest(HashingEmbedder())
    assert asyncio.run(_jobs(MANUAL_JOB)) == [("INDEXED", 1, None)]


def _run_cli(monkeypatch: pytest.MonkeyPatch, redis_url: str, embedder: HashingEmbedder) -> int:
    monkeypatch.setenv("DATABASE_URL", DATABASE_URL)
    monkeypatch.setenv("LLM_API_KEY", "test-key")
    monkeypatch.setenv("REDIS_URL", redis_url)
    monkeypatch.setenv("INGESTION_BACKOFF_SECONDS", "0")
    monkeypatch.setattr(ingestion_run, "OpenAIEmbedder", lambda *_, **__: embedder)
    get_settings.cache_clear()
    try:
        return ingestion_run.main(
            ["--catalog", str(DATA_DIR / "catalog.json"), "--manuals", str(DATA_DIR / "manuals")]
        )
    finally:
        get_settings.cache_clear()


def test_cli_exit_code_follows_the_report(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    asyncio.run(reset_backend_tables())
    assert _run_cli(monkeypatch, "", HashingEmbedder()) == 0
    assert '"catalog_version": null' in capsys.readouterr().out

    asyncio.run(reset_backend_tables())
    assert _run_cli(monkeypatch, "", FlakyEmbedder(failures=99)) == 1
    assert MANUAL_JOB in capsys.readouterr().out


def test_cli_with_redis_down_prints_the_report_and_fails(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    asyncio.run(reset_backend_tables())
    assert _run_cli(monkeypatch, UNREACHABLE_REDIS_URL, HashingEmbedder()) == 1
    printed = capsys.readouterr().out
    assert '"indexed_sources"' in printed and '"catalog_version_error": "' in printed


def test_cli_rejects_an_overlapping_ingestion_without_writes(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    asyncio.run(reset_backend_tables())

    async def scenario() -> int:
        async with await psycopg.AsyncConnection.connect(DATABASE_URL, autocommit=True) as owner:
            await acquire_ingestion_lock(owner)
            await apply_schema(owner)
            # The CLI owns its own event loop in this worker, as in a second process.
            return await asyncio.to_thread(_run_cli, monkeypatch, "", HashingEmbedder())

    assert asyncio.run(scenario()) == 1
    assert '"ingestion_error"' in capsys.readouterr().out
    assert asyncio.run(_jobs(MANUAL_JOB)) == []
