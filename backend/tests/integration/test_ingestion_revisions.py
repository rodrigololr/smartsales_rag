"""B03: source failures, format changes and indexing configuration migrations."""

import asyncio
import json
from pathlib import Path

import psycopg
import pytest
from app.config import Settings
from app.ingestion.run import IngestionReport, ingest
from ingestion_support import DATA_DIR, DATABASE_URL, HashingEmbedder, reset_backend_tables

pytestmark = pytest.mark.skipif(not DATABASE_URL, reason="TEST_DATABASE_URL not set")
SKU = "AF-400-220V"


def execute(
    catalog: Path, manuals: Path, embedder: HashingEmbedder, **settings: object,
) -> IngestionReport:
    return asyncio.run(ingest(
        DATABASE_URL, catalog, manuals, embedder, Settings.model_validate(settings),
    ))


async def manual_rows() -> list[tuple[str, str]]:
    async with await psycopg.AsyncConnection.connect(DATABASE_URL) as conn:
        cursor = await conn.execute(
            "SELECT manual_source, content FROM manual_chunks WHERE sku = %s "
            "AND manual_source LIKE 'manual:%%' ORDER BY page_number, chunk_index", (SKU,)
        )
        return [(row[0], row[1]) for row in await cursor.fetchall()]


def test_read_error_keeps_processing_other_sources_and_returns_a_report(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    asyncio.run(reset_backend_tables())
    manual = tmp_path / f"{SKU}.txt"
    manual.write_text("Manual revision", encoding="utf-8")
    read_bytes = Path.read_bytes

    def unreadable(path: Path) -> bytes:
        if path == manual:
            raise PermissionError("manual is unreadable")
        return read_bytes(path)

    monkeypatch.setattr(Path, "read_bytes", unreadable)
    report = execute(DATA_DIR / "catalog.json", tmp_path, HashingEmbedder())
    assert report.needs_intervention == [f"{SKU}/manual:{SKU}.txt"]
    assert f"{SKU}/catalog:spec_sheet" in report.indexed_sources
    assert "CF-15B-127V/catalog:spec_sheet" in report.indexed_sources
    assert "PermissionError" in report.source_read_errors[f"{SKU}/manual:{SKU}.txt"]


def test_changing_manual_extension_retires_the_previous_source_only_after_success(tmp_path: Path) -> None:
    asyncio.run(reset_backend_tables())
    execute(DATA_DIR / "catalog.json", DATA_DIR / "manuals", HashingEmbedder())
    (tmp_path / f"{SKU}.md").write_text("New manual text", encoding="utf-8")
    execute(DATA_DIR / "catalog.json", tmp_path, HashingEmbedder())
    assert {source for source, _ in asyncio.run(manual_rows())} == {f"manual:{SKU}.md"}


@pytest.mark.parametrize("change", ["context", "chunking", "embedding", "provider"])
def test_index_rebuilds_when_context_or_indexing_settings_change(tmp_path: Path, change: str) -> None:
    asyncio.run(reset_backend_tables())
    embedder = HashingEmbedder()
    execute(DATA_DIR / "catalog.json", DATA_DIR / "manuals", embedder)
    catalog = DATA_DIR / "catalog.json"
    settings: dict[str, object] = {}
    if change == "context":
        products = json.loads(catalog.read_text(encoding="utf-8"))
        products[0]["name"] = "Renamed product"
        catalog = tmp_path / "catalog.json"
        catalog.write_text(json.dumps(products), encoding="utf-8")
    elif change == "chunking":
        settings["chunk_size_tokens"] = 300
    elif change == "embedding":
        settings["embedding_model"] = "a-different-embedding-model"
    else:
        settings["llm_base_url"] = "https://different-provider.invalid/v1"
    report = execute(catalog, DATA_DIR / "manuals", embedder, **settings)
    assert f"{SKU}/manual:{SKU}.txt" in report.indexed_sources
    if change == "context":
        assert all("Renamed product" in content for _, content in asyncio.run(manual_rows()))


def test_unchanged_existing_chunks_get_missing_job_records_without_embedding() -> None:
    asyncio.run(reset_backend_tables())
    embedder = HashingEmbedder()
    execute(DATA_DIR / "catalog.json", DATA_DIR / "manuals", embedder)

    async def remove_jobs() -> None:
        async with await psycopg.AsyncConnection.connect(DATABASE_URL, autocommit=True) as conn:
            await conn.execute("DELETE FROM ingestion_jobs")

    asyncio.run(remove_jobs())
    calls = embedder.calls
    report = execute(DATA_DIR / "catalog.json", DATA_DIR / "manuals", embedder)

    async def job_count() -> int:
        async with await psycopg.AsyncConnection.connect(DATABASE_URL) as conn:
            cursor = await conn.execute("SELECT COUNT(*) FROM ingestion_jobs WHERE status = 'INDEXED'")
            row = await cursor.fetchone()
            return int(row[0]) if row else 0

    assert embedder.calls == calls and not report.indexed_sources
    assert asyncio.run(job_count()) == len(report.skipped_sources)


def test_broken_new_format_keeps_the_complete_previous_manual(tmp_path: Path) -> None:
    asyncio.run(reset_backend_tables())
    execute(DATA_DIR / "catalog.json", DATA_DIR / "manuals", HashingEmbedder())
    previous = asyncio.run(manual_rows())
    (tmp_path / f"{SKU}.pdf").write_bytes(b"broken replacement PDF")
    report = execute(DATA_DIR / "catalog.json", tmp_path, HashingEmbedder())
    assert report.needs_intervention == [f"{SKU}/manual:{SKU}.pdf"]
    assert asyncio.run(manual_rows()) == previous
