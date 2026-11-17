"""UC08 ingestion CLI.

    python -m app.ingestion.run --catalog ../data/catalog.json --manuals ../data/manuals/
        [--relations ../data/product_relations.json]

Upserts the catalog and its product_relations (RN05), then indexes per product its
catalog spec sheet and its manual (data/manuals/<SKU>.pdf|.txt|.md). Unchanged sources
(same SHA-256) are skipped.
"""

import argparse
import asyncio
import hashlib
import json
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field, replace
from functools import partial
from pathlib import Path
from uuid import UUID

import psycopg
import tiktoken
from pydantic import TypeAdapter

from app.clients.catalog_version import (
    CatalogVersionBumper,
    CatalogVersionUnavailableError,
    RedisCatalogVersion,
)
from app.clients.openai_client import LLMUnavailableError, OpenAIEmbedder, make_client
from app.config import Settings, get_settings
from app.db.repository import (
    ChunkRow,
    IngestionAlreadyRunningError,
    IngestionJobStatus,
    acquire_ingestion_lock,
    apply_schema,
    current_version,
    deactivate_missing,
    ensure_indexed_job,
    finish_ingestion_job,
    replace_manual_chunks,
    replace_product_relations,
    retire_other_manual_sources,
    start_ingestion_job,
    upsert_product,
)
from app.ingestion.chunking import chunk_page, context_header, spec_sheet
from app.ingestion.manuals import find_manual, read_manual_pages
from app.ingestion.relations import load_relations
from app.models.schemas import CatalogProduct
from app.rag.orchestrator import Embedder

logger = logging.getLogger(__name__)
CHUNK_ENCODING = "cl100k_base"
SPEC_SHEET_SOURCE = "catalog:spec_sheet"
# Provider outage or database error: retried with backoff, never swallowed.
RETRYABLE_INGESTION_ERRORS = (LLMUnavailableError, psycopg.Error)


@dataclass(frozen=True)
class ManualSource:
    source: str
    title: str
    version: str
    load_pages: Callable[[], list[str]]  # read inside the job: a broken PDF fails only its job


@dataclass
class IngestionReport:
    products: int = 0
    indexed_sources: list[str] = field(default_factory=list)
    skipped_sources: list[str] = field(default_factory=list)
    products_without_manual: list[str] = field(default_factory=list)
    deactivated: int = 0
    relations: int = 0
    needs_intervention: list[str] = field(default_factory=list)
    catalog_version: int | None = None
    catalog_version_error: str | None = None
    source_read_errors: dict[str, str] = field(default_factory=dict)


def load_catalog(path: Path) -> list[CatalogProduct]:
    products = TypeAdapter(list[CatalogProduct]).validate_json(path.read_bytes())
    skus = [product.sku for product in products]
    if len(set(skus)) != len(skus):
        raise ValueError("SKU duplicado no catálogo")
    return products


def sources_for(
    product: CatalogProduct, manuals_dir: Path, *, read_errors: dict[str, str] | None = None,
) -> list[ManualSource]:
    sheet = spec_sheet(product)
    sources = [
        ManualSource(
            source=SPEC_SHEET_SOURCE,
            title=f"Ficha técnica {product.name}",
            version=hashlib.sha256(sheet.encode()).hexdigest(),
            load_pages=lambda: [sheet],
        )
    ]
    manual = find_manual(manuals_dir, product.sku)
    if manual is not None:
        try:
            snapshot = manual.read_bytes()
        except OSError as error:
            if read_errors is None:
                raise
            read_errors[f"{product.sku}/manual:{manual.name}"] = repr(error)
            return sources
        sources.append(
            ManualSource(
                source=f"manual:{manual.name}",
                title=product.manual_title or f"Manual {product.name}",
                version=hashlib.sha256(snapshot).hexdigest(),
                load_pages=partial(read_manual_pages, manual, content=snapshot),
            )
        )
    return sources


async def ingest(
    conninfo: str,
    catalog_path: Path,
    manuals_dir: Path,
    embedder: Embedder,
    settings: Settings,
    relations_path: Path | None = None,
    *,
    catalog_version: CatalogVersionBumper | None = None,
    sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
) -> IngestionReport:
    products = load_catalog(catalog_path)
    relations = (
        load_relations(relations_path, {product.sku for product in products})
        if relations_path is not None
        else None
    )
    report = IngestionReport(products=len(products))
    async with await psycopg.AsyncConnection.connect(conninfo, autocommit=True) as conn:
        await acquire_ingestion_lock(conn)
        try:
            await apply_schema(conn)
            indexer = _SourceIndexer(conn, embedder, settings, report, sleep)
            for product in products:
                product_id = await upsert_product(conn, product)
                read_errors: dict[str, str] = {}
                sources = sources_for(product, manuals_dir, read_errors=read_errors)
                report.source_read_errors.update(read_errors)
                report.needs_intervention.extend(read_errors)
                if len(sources) == 1 and not read_errors:
                    report.products_without_manual.append(product.sku)
                for source in sources:
                    await indexer.index(product, product_id, source)
            if relations is not None:  # no seed given: existing relations stay untouched
                report.relations = await replace_product_relations(conn, relations)
            report.deactivated = await deactivate_missing(conn, [p.sku for p in products])
        finally:
            # Autocommit: even a run that dies midway already changed the catalog, so caches
            # built on the old one must die too (spec 01, section 6).
            if catalog_version is not None:
                await _bump_catalog_version(catalog_version, report)
    return report


async def _bump_catalog_version(
    catalog_version: CatalogVersionBumper, report: IngestionReport
) -> None:
    try:
        report.catalog_version = await catalog_version.bump()
    except CatalogVersionUnavailableError as error:
        logger.error("catalog_version_bump_failed", extra={"error": str(error)})
        report.catalog_version_error = str(error)


class _SourceIndexer:
    """Indexes one manual source under its ingestion_jobs record, retrying with backoff."""

    def __init__(
        self,
        conn: psycopg.AsyncConnection[object],
        embedder: Embedder,
        settings: Settings,
        report: IngestionReport,
        sleep: Callable[[float], Awaitable[None]],
    ) -> None:
        self._conn = conn
        self._embedder = embedder
        self._settings = settings
        self._report = report
        self._sleep = sleep
        self._encoding = tiktoken.get_encoding(CHUNK_ENCODING)

    async def index(self, product: CatalogProduct, product_id: UUID, source: ManualSource) -> None:
        label = f"{product.sku}/{source.source}"
        fingerprint = self._fingerprint(product, source)
        if await current_version(
            self._conn, product_id, source.source, fingerprint=fingerprint,
        ) == source.version:
            async with self._conn.transaction():
                await self._conn.execute("SELECT id FROM products WHERE id = %s FOR UPDATE", (product_id,))
                await retire_other_manual_sources(self._conn, product_id, product.sku, source.source)
                await ensure_indexed_job(self._conn, product_id, label, source.version)
            self._report.skipped_sources.append(label)
            return
        for attempt in range(1, self._settings.ingestion_max_attempts + 1):
            await start_ingestion_job(
                self._conn,
                product_id=product_id,
                source_file=label,
                content_hash=source.version,
                attempt=attempt,
            )
            try:
                await self._replace_chunks(product, product_id, source, label)
            except RETRYABLE_INGESTION_ERRORS as error:
                if not await self._retry_after(error, label, source, attempt):
                    return
                continue
            except Exception as error:
                # Last line of defence (broken PDF, rejected API key...): retrying cannot fix
                # it, so the job goes to the operator and the run moves on to the next source.
                logger.exception("ingestion_source_failed", extra={"source": label})
                await self._needs_intervention(error, label, source)
                return
            self._report.indexed_sources.append(label)
            return

    def _fingerprint(self, product: CatalogProduct, source: ManualSource) -> str:
        policy = {
            "version": source.version, "title": source.title,
            "context": context_header(product, page_number=1),
            "embedding_model": self._settings.embedding_model,
            "embedding_base_url": self._settings.llm_base_url,
            "dimensions": self._settings.embedding_dimensions,
            "chunk_size": self._settings.chunk_size_tokens,
            "chunk_overlap": self._settings.chunk_overlap_tokens,
            "policy": "ingestion-v2",
        }
        return hashlib.sha256(json.dumps(policy, sort_keys=True).encode()).hexdigest()

    async def _replace_chunks(
        self, product: CatalogProduct, product_id: UUID, source: ManualSource, label: str
    ) -> None:
        rows = _chunk_rows(product, source, self._encoding, self._settings)
        if not rows:
            raise ValueError("Manual contains no extractable text; previous version preserved")
        embeddings = await self._embedder.embed([row.content for row in rows])
        # One transaction: a crash can never leave new chunks under a job still RUNNING.
        async with self._conn.transaction():
            await replace_manual_chunks(
                self._conn,
                product_id=product_id,
                sku=product.sku,
                manual_source=source.source,
                manual_version=source.version,
                rows=[replace(row, embedding=v, ingestion_fingerprint=self._fingerprint(product, source))
                      for row, v in zip(rows, embeddings, strict=True)],
            )
            await self._finish(label, source, "INDEXED")

    async def _retry_after(
        self, error: Exception, label: str, source: ManualSource, attempt: int
    ) -> bool:
        """Record the failure; False when the attempts are exhausted (NEEDS_INTERVENTION)."""
        logger.warning(
            "ingestion_attempt_failed",
            extra={"source": label, "attempt": attempt, "error": _describe(error)},
        )
        if attempt >= self._settings.ingestion_max_attempts:
            await self._needs_intervention(error, label, source)
            return False
        await self._finish(label, source, "FAILED", last_error=_describe(error))
        await self._sleep(self._settings.ingestion_backoff_seconds * 2 ** (attempt - 1))
        return True

    async def _needs_intervention(
        self, error: Exception, label: str, source: ManualSource
    ) -> None:
        await self._finish(label, source, "NEEDS_INTERVENTION", last_error=_describe(error))
        self._report.needs_intervention.append(label)

    async def _finish(
        self,
        label: str,
        source: ManualSource,
        status: IngestionJobStatus,
        last_error: str | None = None,
    ) -> None:
        await finish_ingestion_job(
            self._conn,
            source_file=label,
            content_hash=source.version,
            status=status,
            last_error=last_error,
        )


def _describe(error: Exception) -> str:
    """repr of the root cause: LLMUnavailableError wraps the provider error without a message."""
    return repr(error.__cause__ or error)


def _chunk_rows(
    product: CatalogProduct, source: ManualSource, encoding: tiktoken.Encoding, settings: Settings
) -> list[ChunkRow]:
    rows: list[ChunkRow] = []
    for page_number, page in enumerate(source.load_pages(), start=1):
        pieces = chunk_page(
            page,
            encoding,
            size=settings.chunk_size_tokens,
            overlap=settings.chunk_overlap_tokens,
        )
        header = context_header(product, page_number=page_number)
        rows.extend(
            ChunkRow(
                page_number=page_number,
                chunk_index=index,
                content=f"{header}\n{piece}",
                embedding=[],
                manual_title=source.title,
            )
            for index, piece in enumerate(pieces)
        )
    return rows


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Ingestão do catálogo e manuais (UC08)")
    parser.add_argument("--catalog", type=Path, required=True)
    parser.add_argument("--manuals", type=Path, required=True)
    parser.add_argument("--relations", type=Path, default=None)
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO)
    settings = get_settings()
    if not settings.llm_api_key:
        parser.error("LLM_API_KEY não definido (veja .env.example)")
    embedder = OpenAIEmbedder(
        make_client(settings),
        model=settings.embedding_model,
        dimensions=settings.embedding_dimensions,
        batch_size=settings.embedding_batch_size,
    )
    if settings.redis_url is None:
        logger.warning("REDIS_URL não definido: catalog:version não será incrementada")
    try:
        report = asyncio.run(
            ingest(
                settings.database_url,
                args.catalog,
                args.manuals,
                embedder,
                settings,
                relations_path=args.relations,
                catalog_version=(
                    RedisCatalogVersion(
                        settings.redis_url,
                        connect_timeout_seconds=settings.redis_connect_timeout_seconds,
                    )
                    if settings.redis_url
                    else None
                ),
            ),
        )
    except IngestionAlreadyRunningError as error:
        print(json.dumps({"ingestion_error": str(error)}, ensure_ascii=False, indent=2))
        return 1
    print(json.dumps(report.__dict__, ensure_ascii=False, indent=2))
    # Sources needing the operator or a cache left stale: fail the seed job.
    return 1 if report.needs_intervention or report.catalog_version_error else 0


if __name__ == "__main__":
    raise SystemExit(main())
