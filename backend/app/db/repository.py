"""PostgreSQL + pgvector access (catalog reads, cosine search, ingestion writes)."""

import json
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, cast
from uuid import UUID

import psycopg
from psycopg.rows import dict_row

from app.models.schemas import CatalogProduct, ProductRelation, RetrievedChunk

SCHEMA_SQL = Path(__file__).with_name("schema.sql")
IngestionJobStatus = Literal["INDEXED", "FAILED", "NEEDS_INTERVENTION"]
INGESTION_LOCK_KEY = 0x5353494E47455354  # stable database-local "SSINGEST" advisory lock


class IngestionAlreadyRunningError(RuntimeError):
    """A catalog-wide ingestion already owns the database's ingestion lock."""


async def acquire_ingestion_lock(conn: psycopg.AsyncConnection[object]) -> None:
    """Hold a session lock until connection close, including preparation and Redis bump.

    The catalog, relation seed and deactivation step are global. Reject overlapping
    runs before any write; per-source locks alone cannot keep these steps consistent.
    """
    cursor = await conn.execute("SELECT pg_try_advisory_lock(%s)", (INGESTION_LOCK_KEY,))
    row = await cursor.fetchone()
    if not row or not cast(tuple[bool], row)[0]:
        raise IngestionAlreadyRunningError("Another ingestion is already running; retry later")

_PRODUCT_COLUMNS = (
    "sku, name, category, subcategory, brand, price, stock_quantity, voltage, "
    "capacity_liters, power_watts, tier_rank, image_url, marketplace, checkout_url, "
    "specs_json, is_active"
)


def vector_literal(values: Sequence[float]) -> str:
    return "[" + ",".join(repr(float(value)) for value in values) + "]"


@dataclass(frozen=True)
class ChunkRow:
    page_number: int
    chunk_index: int
    content: str
    embedding: list[float]
    manual_title: str
    ingestion_fingerprint: str | None = None


class PostgresCatalog:
    """Read side used by the RAG orchestrator.

    shortcut: one connection per call; switch to psycopg_pool before load testing.
    """

    def __init__(self, conninfo: str) -> None:
        self._conninfo = conninfo

    async def get_product(self, sku: str) -> CatalogProduct | None:
        async with await psycopg.AsyncConnection.connect(self._conninfo) as conn:
            cursor = conn.cursor(row_factory=dict_row)
            await cursor.execute(f"SELECT {_PRODUCT_COLUMNS} FROM products WHERE sku = %s", (sku,))
            row = await cursor.fetchone()
        return CatalogProduct.model_validate(row) if row else None

    async def search(self, sku: str, embedding: Sequence[float], limit: int) -> list[RetrievedChunk]:
        """Cosine similarity restricted to the product's own chunks (stock is not filtered)."""
        query = vector_literal(embedding)
        async with await psycopg.AsyncConnection.connect(self._conninfo) as conn:
            cursor = conn.cursor(row_factory=dict_row)
            await cursor.execute(
                """
                SELECT id AS chunk_id, sku, manual_title, page_number, section_title, content,
                       GREATEST(0, 1 - (embedding <=> %s::vector)) AS similarity_score
                FROM manual_chunks
                WHERE sku = %s
                ORDER BY embedding <=> %s::vector
                LIMIT %s
                """,
                (query, sku, query, limit),
            )
            rows = await cursor.fetchall()
        return [RetrievedChunk.model_validate(row) for row in rows]


async def apply_schema(conn: psycopg.AsyncConnection[object]) -> None:
    await conn.execute(SCHEMA_SQL.read_text(encoding="utf-8").encode())


async def upsert_product(conn: psycopg.AsyncConnection[object], product: CatalogProduct) -> UUID:
    values = product.model_dump(include=set(_PRODUCT_COLUMNS.replace(" ", "").split(",")))
    values["specs_json"] = json.dumps(values["specs_json"])
    cursor = await conn.execute(
        f"""
        INSERT INTO products ({_PRODUCT_COLUMNS})
        VALUES (%(sku)s, %(name)s, %(category)s, %(subcategory)s, %(brand)s, %(price)s,
                %(stock_quantity)s, %(voltage)s, %(capacity_liters)s, %(power_watts)s,
                %(tier_rank)s, %(image_url)s, %(marketplace)s, %(checkout_url)s,
                %(specs_json)s::jsonb, %(is_active)s)
        ON CONFLICT (sku) DO UPDATE SET
            name = EXCLUDED.name, category = EXCLUDED.category,
            subcategory = EXCLUDED.subcategory, brand = EXCLUDED.brand,
            price = EXCLUDED.price, stock_quantity = EXCLUDED.stock_quantity,
            voltage = EXCLUDED.voltage, capacity_liters = EXCLUDED.capacity_liters,
            power_watts = EXCLUDED.power_watts, tier_rank = EXCLUDED.tier_rank,
            image_url = EXCLUDED.image_url, marketplace = EXCLUDED.marketplace,
            checkout_url = EXCLUDED.checkout_url, specs_json = EXCLUDED.specs_json,
            is_active = EXCLUDED.is_active, updated_at = NOW()
        RETURNING id
        """,
        values,
    )
    row = await cursor.fetchone()
    return cast(UUID, cast(tuple[object, ...], row)[0])


async def current_version(
    conn: psycopg.AsyncConnection[object], product_id: UUID, manual_source: str,
    *, fingerprint: str | None = None,
) -> str | None:
    cursor = await conn.execute(
        "SELECT MIN(manual_version) FROM manual_chunks "
        "WHERE product_id = %s AND manual_source = %s "
        "HAVING COUNT(DISTINCT manual_version) = 1 AND "
        "(%s::text IS NULL OR BOOL_AND(COALESCE(metadata->>'ingestion_fingerprint' = %s, FALSE)))",
        (product_id, manual_source, fingerprint, fingerprint),
    )
    row = await cursor.fetchone()
    return cast(str, cast(tuple[object, ...], row)[0]) if row else None


async def replace_manual_chunks(
    conn: psycopg.AsyncConnection[object],
    *,
    product_id: UUID,
    sku: str,
    manual_source: str,
    manual_version: str,
    rows: Sequence[ChunkRow],
) -> None:
    """Swap a manual's chunks atomically: the old version survives any failure."""
    async with conn.transaction():
        # A concurrent DELETE can miss the rows inserted by the transaction it waited
        # for. Serialize before DELETE so its statement snapshot sees the full version.
        await lock_product(conn, product_id)
        await retire_other_manual_sources(conn, product_id, sku, manual_source)
        await conn.execute(
            "DELETE FROM manual_chunks WHERE product_id = %s AND manual_source = %s",
            (product_id, manual_source),
        )
        async with conn.cursor() as cursor:
            await cursor.executemany(
                """
                INSERT INTO manual_chunks (product_id, sku, manual_title, page_number,
                    chunk_index, manual_source, manual_version, content, embedding, metadata)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s::vector, %s::jsonb)
                """,
                [
                    (
                        product_id,
                        sku,
                        row.manual_title,
                        row.page_number,
                        row.chunk_index,
                        manual_source,
                        manual_version,
                        row.content,
                        vector_literal(row.embedding),
                        json.dumps({"ingestion_fingerprint": row.ingestion_fingerprint}),
                    )
                    for row in rows
                ],
            )


async def lock_product(conn: psycopg.AsyncConnection[object], product_id: UUID) -> None:
    """Row lock that serializes every change to one product's manual chunks and jobs.

    Call inside a transaction: the lock is released on commit or rollback.
    """
    await conn.execute("SELECT id FROM products WHERE id = %s FOR UPDATE", (product_id,))


async def retire_other_manual_sources(
    conn: psycopg.AsyncConnection[object], product_id: UUID, sku: str, source: str,
) -> None:
    """A SKU has one active manual, even when its filename extension changes."""
    if source.startswith("manual:"):
        await conn.execute(
            "DELETE FROM manual_chunks WHERE product_id = %s "
            "AND manual_source LIKE 'manual:%%' AND manual_source <> %s", (product_id, source),
        )
        await conn.execute(
            "DELETE FROM ingestion_jobs WHERE product_id = %s "
            "AND source_file LIKE %s AND source_file <> %s AND status <> 'INDEXED'",
            (product_id, f"{sku}/manual:%", f"{sku}/{source}"),
        )


async def ensure_indexed_job(
    conn: psycopg.AsyncConnection[object], product_id: UUID, label: str, version: str,
) -> None:
    """Backfill bookkeeping for already committed chunks, preserving attempt history."""
    await conn.execute(
        "INSERT INTO ingestion_jobs (product_id, source_file, content_hash, status, attempts) "
        "VALUES (%s, %s, %s, 'INDEXED', 0) ON CONFLICT (source_file, content_hash) DO NOTHING",
        (product_id, label, version),
    )
    await finish_ingestion_job(conn, source_file=label, content_hash=version, status="INDEXED")


async def start_ingestion_job(
    conn: psycopg.AsyncConnection[object],
    *,
    product_id: UUID,
    source_file: str,
    content_hash: str,
    attempt: int,
) -> None:
    """Open (or reopen) the job of this source version as RUNNING on the run's nth attempt."""
    await conn.execute(
        """
        INSERT INTO ingestion_jobs (product_id, source_file, content_hash, status, attempts)
        VALUES (%s, %s, %s, 'RUNNING', %s)
        ON CONFLICT (source_file, content_hash) DO UPDATE SET
            product_id = EXCLUDED.product_id, status = 'RUNNING',
            attempts = EXCLUDED.attempts, last_error = NULL, updated_at = NOW()
        """,
        (product_id, source_file, content_hash, attempt),
    )


async def finish_ingestion_job(
    conn: psycopg.AsyncConnection[object],
    *,
    source_file: str,
    content_hash: str,
    status: IngestionJobStatus,
    last_error: str | None = None,
) -> None:
    await conn.execute(
        "UPDATE ingestion_jobs SET status = %s, last_error = %s, updated_at = NOW() "
        "WHERE source_file = %s AND content_hash = %s",
        (status, last_error, source_file, content_hash),
    )
    if status == "INDEXED":
        # Unfinished jobs of older versions of this source are settled by this one.
        await conn.execute(
            "DELETE FROM ingestion_jobs "
            "WHERE source_file = %s AND content_hash <> %s AND status <> 'INDEXED'",
            (source_file, content_hash),
        )


async def replace_product_relations(
    conn: psycopg.AsyncConnection[object], relations: Sequence[ProductRelation]
) -> int:
    """The seed is the source of truth: relations absent from it stop being offered."""
    async with conn.transaction():
        # Serialize whole-table replacements before DELETE takes its READ COMMITTED
        # snapshot. Readers keep seeing the committed seed; commit/rollback releases
        # this writer lock, including for an explicit empty replacement seed.
        await conn.execute("LOCK TABLE product_relations IN SHARE ROW EXCLUSIVE MODE")
        await conn.execute("DELETE FROM product_relations")
        async with conn.cursor() as cursor:
            await cursor.executemany(
                """
                INSERT INTO product_relations (base_product_id, related_product_id,
                    relation_type, affinity_weight, justification_template)
                SELECT base.id, related.id, %s, %s, %s
                FROM products base, products related
                WHERE base.sku = %s AND related.sku = %s
                """,
                [
                    (
                        relation.relation_type,
                        relation.affinity_weight,
                        relation.justification_template,
                        relation.base_sku,
                        relation.related_sku,
                    )
                    for relation in relations
                ],
            )
    return len(relations)


async def deactivate_missing(conn: psycopg.AsyncConnection[object], skus: Sequence[str]) -> int:
    """Products removed from the seed stop being answered and lose their chunks."""
    async with conn.transaction():
        await conn.execute(
            "DELETE FROM manual_chunks WHERE sku <> ALL(%s)", (list(skus),)
        )
        cursor = await conn.execute(
            "UPDATE products SET is_active = FALSE, updated_at = NOW() "
            "WHERE sku <> ALL(%s) AND is_active",
            (list(skus),),
        )
    return cursor.rowcount
