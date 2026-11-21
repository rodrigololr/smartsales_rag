"""IT-P1: knowledge_chunks ingestion, idempotent skip, replace, delete and multi-file CLI."""

import asyncio
import hashlib
import shutil
from collections.abc import Sequence
from pathlib import Path

import app.ingestion.run as ingestion_run
import psycopg
import pytest
from app.config import Settings, get_settings
from app.ingestion.knowledge import knowledge_docs
from app.ingestion.run import ingest
from ingestion_support import DATA_DIR, DATABASE_URL, HashingEmbedder, reset_backend_tables

pytestmark = pytest.mark.skipif(not DATABASE_URL, reason="TEST_DATABASE_URL not set")

CATALOG_PATHS = [DATA_DIR / "catalog.json", DATA_DIR / "catalog_consultor.json"]
RELATION_PATHS = [
    DATA_DIR / "product_relations.json",
    DATA_DIR / "product_relations_consultor.json",
]
KNOWLEDGE_DIR = DATA_DIR / "knowledge"


async def _reset_all() -> None:
    await reset_backend_tables()
    async with await psycopg.AsyncConnection.connect(DATABASE_URL, autocommit=True) as conn:
        await conn.execute("DROP TABLE IF EXISTS knowledge_chunks CASCADE")


async def _knowledge_rows() -> list[tuple[str, str, int, int, str, str]]:
    async with await psycopg.AsyncConnection.connect(DATABASE_URL) as conn:
        cursor = await conn.execute(
            """
            SELECT doc_id, title, page_number, chunk_index, doc_version, content
            FROM knowledge_chunks
            ORDER BY doc_id, page_number, chunk_index
            """
        )
        return [
            (row[0], row[1], int(row[2]), int(row[3]), row[4], row[5])
            for row in await cursor.fetchall()
        ]


async def _manual_snapshot() -> list[tuple[str, str, int, int, str]]:
    async with await psycopg.AsyncConnection.connect(DATABASE_URL) as conn:
        cursor = await conn.execute(
            """
            SELECT sku, manual_source, page_number, chunk_index, manual_version
            FROM manual_chunks
            ORDER BY sku, manual_source, page_number, chunk_index
            """
        )
        return [
            (row[0], row[1], int(row[2]), int(row[3]), row[4])
            for row in await cursor.fetchall()
        ]


def test_knowledge_ingestion_is_idempotent_and_indexes_combined_seed() -> None:
    asyncio.run(_reset_all())
    embedder = HashingEmbedder()

    first = asyncio.run(
        ingest(
            DATABASE_URL,
            CATALOG_PATHS,
            DATA_DIR / "manuals",
            embedder,
            Settings(),
            relations_path=RELATION_PATHS,
            knowledge_dir=KNOWLEDGE_DIR,
        )
    )
    assert first.products == 47
    assert first.relations == 21
    assert first.needs_intervention == []
    docs = knowledge_docs(KNOWLEDGE_DIR)
    assert len(docs) == 6
    for doc in docs:
        assert f"knowledge:{doc.doc_id}" in first.indexed_sources

    rows = asyncio.run(_knowledge_rows())
    assert {row[0] for row in rows} == {doc.doc_id for doc in docs}
    for doc_id, title, page_number, _chunk_index, doc_version, content in rows:
        expected_doc = next(d for d in docs if d.doc_id == doc_id)
        assert title == expected_doc.title
        assert doc_version == expected_doc.version
        assert content.startswith(f"[BASE DE CONHECIMENTO: {title} | PÁG: {page_number}]\n")

    calls_before = embedder.calls
    second = asyncio.run(
        ingest(
            DATABASE_URL,
            CATALOG_PATHS,
            DATA_DIR / "manuals",
            embedder,
            Settings(),
            relations_path=RELATION_PATHS,
            knowledge_dir=KNOWLEDGE_DIR,
        )
    )
    assert second.indexed_sources == []
    assert embedder.calls == calls_before
    for doc in docs:
        assert f"knowledge:{doc.doc_id}" in second.skipped_sources


def test_knowledge_ingestion_replaces_changed_doc_deletes_removed_and_keeps_manual_chunks(
    tmp_path: Path,
) -> None:
    asyncio.run(_reset_all())
    embedder = HashingEmbedder()
    kb_copy = tmp_path / "knowledge"
    shutil.copytree(KNOWLEDGE_DIR, kb_copy)

    asyncio.run(
        ingest(
            DATABASE_URL,
            CATALOG_PATHS,
            DATA_DIR / "manuals",
            embedder,
            Settings(),
            relations_path=RELATION_PATHS,
            knowledge_dir=kb_copy,
        )
    )
    manuals_before = asyncio.run(_manual_snapshot())
    assert manuals_before

    # Modify KB-GTA-RP and remove KB-SOFA-ESPACO
    gta_rp_path = kb_copy / "KB-GTA-RP.txt"
    updated_text = gta_rp_path.read_text(encoding="utf-8") + "\nLinha adicional verificada."
    gta_rp_path.write_text(updated_text, encoding="utf-8")
    new_sha = hashlib.sha256(gta_rp_path.read_bytes()).hexdigest()
    (kb_copy / "KB-SOFA-ESPACO.txt").unlink()

    report = asyncio.run(
        ingest(
            DATABASE_URL,
            CATALOG_PATHS,
            DATA_DIR / "manuals",
            embedder,
            Settings(),
            relations_path=RELATION_PATHS,
            knowledge_dir=kb_copy,
        )
    )
    assert report.indexed_sources == ["knowledge:KB-GTA-RP"]
    assert "knowledge:KB-GTA6-PLATAFORMAS" in report.skipped_sources

    rows = asyncio.run(_knowledge_rows())
    doc_ids = {row[0] for row in rows}
    assert "KB-SOFA-ESPACO" not in doc_ids
    assert "KB-GTA-RP" in doc_ids
    gta_rp_rows = [row for row in rows if row[0] == "KB-GTA-RP"]
    assert all(row[4] == new_sha for row in gta_rp_rows)
    assert any("Linha adicional verificada." in row[5] for row in gta_rp_rows)

    # Running without --knowledge must not delete knowledge_chunks
    asyncio.run(
        ingest(
            DATABASE_URL,
            CATALOG_PATHS,
            DATA_DIR / "manuals",
            embedder,
            Settings(),
            relations_path=RELATION_PATHS,
        )
    )
    assert {row[0] for row in asyncio.run(_knowledge_rows())} == doc_ids

    # manual_chunks is untouched by KB updates and deletions
    assert asyncio.run(_manual_snapshot()) == manuals_before


def test_cli_supports_multiple_catalogs_relations_and_knowledge_and_reports_kb_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    asyncio.run(_reset_all())
    embedder = HashingEmbedder()
    monkeypatch.setenv("DATABASE_URL", DATABASE_URL)
    monkeypatch.setenv("LLM_API_KEY", "test-key")
    monkeypatch.setenv("REDIS_URL", "")
    monkeypatch.setenv("INGESTION_BACKOFF_SECONDS", "0")
    monkeypatch.setattr(ingestion_run, "OpenAIEmbedder", lambda *_, **__: embedder)
    get_settings.cache_clear()
    argv = [
        "--catalog",
        str(DATA_DIR / "catalog.json"),
        "--catalog",
        str(DATA_DIR / "catalog_consultor.json"),
        "--manuals",
        str(DATA_DIR / "manuals"),
        "--relations",
        str(DATA_DIR / "product_relations.json"),
        "--relations",
        str(DATA_DIR / "product_relations_consultor.json"),
        "--knowledge",
        str(KNOWLEDGE_DIR),
    ]
    try:
        assert ingestion_run.main(argv) == 0
        assert len({row[0] for row in asyncio.run(_knowledge_rows())}) == 6

        class FailingKbEmbedder(HashingEmbedder):
            async def embed(self, texts: Sequence[str]) -> list[list[float]]:
                if any("BASE DE CONHECIMENTO:" in t for t in texts):
                    raise RuntimeError("kb embedder failure")
                return await super().embed(texts)

        asyncio.run(_reset_all())
        monkeypatch.setattr(
            ingestion_run, "OpenAIEmbedder", lambda *_, **__: FailingKbEmbedder()
        )
        assert ingestion_run.main(argv) == 1
    finally:
        get_settings.cache_clear()
