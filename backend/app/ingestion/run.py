"""UC08 ingestion CLI.

    python -m app.ingestion.run --catalog ../data/catalog.json --manuals ../data/manuals/

Upserts the catalog, then indexes per product its catalog spec sheet and its manual
(data/manuals/<SKU>.pdf|.txt|.md). Unchanged sources (same SHA-256) are skipped.
"""

import argparse
import asyncio
import hashlib
import json
import logging
from dataclasses import dataclass, field, replace
from pathlib import Path

import psycopg
import tiktoken
from openai import AsyncOpenAI
from pydantic import TypeAdapter

from app.clients.openai_client import OpenAIEmbedder
from app.config import Settings, get_settings
from app.db.repository import (
    ChunkRow,
    apply_schema,
    current_version,
    deactivate_missing,
    replace_manual_chunks,
    upsert_product,
)
from app.ingestion.chunking import chunk_page, context_header, spec_sheet
from app.ingestion.manuals import find_manual, read_manual_pages
from app.models.schemas import CatalogProduct
from app.rag.orchestrator import Embedder

logger = logging.getLogger(__name__)
CHUNK_ENCODING = "cl100k_base"
SPEC_SHEET_SOURCE = "catalog:spec_sheet"


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
) -> IngestionReport:
    encoding = tiktoken.get_encoding(CHUNK_ENCODING)
    products = load_catalog(catalog_path)
    report = IngestionReport(products=len(products))
    async with await psycopg.AsyncConnection.connect(conninfo, autocommit=True) as conn:
        await apply_schema(conn)
        for product in products:
            product_id = await upsert_product(conn, product)
            sources = sources_for(product, manuals_dir)
            if len(sources) == 1:
                report.products_without_manual.append(product.sku)
            for source in sources:
                label = f"{product.sku}/{source.source}"
                if await current_version(conn, product_id, source.source) == source.version:
                    report.skipped_sources.append(label)
                    continue
                rows = _chunk_rows(product, source, encoding, settings)
                embeddings = await embedder.embed([row.content for row in rows])
                rows = [replace(row, embedding=vector) for row, vector in zip(rows, embeddings, strict=True)]
                await replace_manual_chunks(
                    conn,
                    product_id=product_id,
                    sku=product.sku,
                    manual_source=source.source,
                    manual_version=source.version,
                    rows=rows,
                )
                report.indexed_sources.append(label)
        report.deactivated = await deactivate_missing(conn, [p.sku for p in products])
    return report


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
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO)
    settings = get_settings()
    if not settings.openai_api_key:
        parser.error("OPENAI_API_KEY não definido (veja backend/.env.example)")
    embedder = OpenAIEmbedder(
        AsyncOpenAI(api_key=settings.openai_api_key),
        model=settings.embedding_model,
        dimensions=settings.embedding_dimensions,
        batch_size=settings.embedding_batch_size,
    )
    report = asyncio.run(
        ingest(settings.database_url, args.catalog, args.manuals, embedder, settings)
    )
    print(json.dumps(report.__dict__, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
