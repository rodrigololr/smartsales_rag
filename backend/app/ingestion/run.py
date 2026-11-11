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
from pathlib import Path
from uuid import UUID

import psycopg
import tiktoken
from pydantic import TypeAdapter

from app.clients.catalog_version import CatalogVersionBumper, RedisCatalogVersion
from app.clients.openai_client import LLMUnavailableError, OpenAIEmbedder, make_client
from app.config import Settings, get_settings
from app.db.repository import (
    ChunkRow,
    IngestionJobStatus,
    apply_schema,
    current_version,
    deactivate_missing,
    finish_ingestion_job,
    replace_manual_chunks,
    replace_product_relations,
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
    pages: list[str]


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


def load_catalog(path: Path) -> list[CatalogProduct]:
    products = TypeAdapter(list[CatalogProduct]).validate_json(path.read_bytes())
    skus = [product.sku for product in products]
    if len(set(skus)) != len(skus):
        raise ValueError("SKU duplicado no catálogo")
    return products


def sources_for(product: CatalogProduct, manuals_dir: Path) -> list[ManualSource]:
    sheet = spec_sheet(product)
    sources = [
        ManualSource(
            source=SPEC_SHEET_SOURCE,
            title=f"Ficha técnica {product.name}",
            version=hashlib.sha256(sheet.encode()).hexdigest(),
            pages=[sheet],
        )
    ]
    manual = find_manual(manuals_dir, product.sku)
    if manual is not None:
        sources.append(
            ManualSource(
                source=f"manual:{manual.name}",
                title=product.manual_title or f"Manual {product.name}",
                version=hashlib.sha256(manual.read_bytes()).hexdigest(),
                pages=read_manual_pages(manual),
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
        else []
    )
    report = IngestionReport(products=len(products))
    async with await psycopg.AsyncConnection.connect(conninfo, autocommit=True) as conn:
        await apply_schema(conn)
        indexer = _SourceIndexer(conn, embedder, settings, report, sleep)
        for product in products:
            product_id = await upsert_product(conn, product)
            sources = sources_for(product, manuals_dir)
            if len(sources) == 1:
                report.products_without_manual.append(product.sku)
            for source in sources:
                await indexer.index(product, product_id, source)
        report.relations = await replace_product_relations(conn, relations)
        report.deactivated = await deactivate_missing(conn, [p.sku for p in products])
    if catalog_version is not None:
        # After the commits above (spec 01, section 6): caches built on the old catalog die.
        report.catalog_version = await catalog_version.bump()
    return report


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
        if await current_version(self._conn, product_id, source.source) == source.version:
            self._report.skipped_sources.append(label)
            return
        for attempt in range(1, self._settings.ingestion_max_attempts + 1):
            await start_ingestion_job(
                self._conn, product_id=product_id, source_file=label, content_hash=source.version
            )
            try:
                await self._replace_chunks(product, product_id, source)
            except RETRYABLE_INGESTION_ERRORS as error:
                if not await self._retry_after(error, label, source, attempt):
                    return
                continue
            await self._finish(label, source, "INDEXED")
            self._report.indexed_sources.append(label)
            return

    async def _replace_chunks(
        self, product: CatalogProduct, product_id: UUID, source: ManualSource
    ) -> None:
        rows = _chunk_rows(product, source, self._encoding, self._settings)
        embeddings = await self._embedder.embed([row.content for row in rows])
        await replace_manual_chunks(
            self._conn,
            product_id=product_id,
            sku=product.sku,
            manual_source=source.source,
            manual_version=source.version,
            rows=[replace(row, embedding=v) for row, v in zip(rows, embeddings, strict=True)],
        )

    async def _retry_after(
        self, error: Exception, label: str, source: ManualSource, attempt: int
    ) -> bool:
        """Record the failure; False when the attempts are exhausted (NEEDS_INTERVENTION)."""
        exhausted = attempt >= self._settings.ingestion_max_attempts
        logger.warning(
            "ingestion_attempt_failed",
            extra={"source": label, "attempt": attempt, "error": str(error)},
        )
        status: IngestionJobStatus = "NEEDS_INTERVENTION" if exhausted else "FAILED"
        await self._finish(label, source, status, last_error=str(error))
        if exhausted:
            self._report.needs_intervention.append(label)
            return False
        await self._sleep(self._settings.ingestion_backoff_seconds * 2 ** (attempt - 1))
        return True

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


def _chunk_rows(
    product: CatalogProduct, source: ManualSource, encoding: tiktoken.Encoding, settings: Settings
) -> list[ChunkRow]:
    rows: list[ChunkRow] = []
    for page_number, page in enumerate(source.pages, start=1):
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
    report = asyncio.run(
        ingest(
            settings.database_url,
            args.catalog,
            args.manuals,
            embedder,
            settings,
            relations_path=args.relations,
            catalog_version=(
                RedisCatalogVersion(settings.redis_url) if settings.redis_url else None
            ),
        )
    )
    print(json.dumps(report.__dict__, ensure_ascii=False, indent=2))
    # Sources that exhausted their retries need the operator: fail the seed job.
    return 1 if report.needs_intervention else 0


if __name__ == "__main__":
    raise SystemExit(main())
