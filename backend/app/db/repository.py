"""PostgreSQL + pgvector access (catalog reads, cosine search, ingestion writes)."""

import json
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal, cast
from uuid import UUID

import psycopg
from psycopg.rows import dict_row

from app.models.schemas import CatalogProduct, ProductRelation, RetrievedChunk
from app.recommendation.service import CrossSellRelation, RecommendationLookupError

SCHEMA_SQL = Path(__file__).with_name("schema.sql")
IngestionJobStatus = Literal["INDEXED", "FAILED", "NEEDS_INTERVENTION"]

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

    async def upsell_candidates(self, base: CatalogProduct) -> list[CatalogProduct]:
        """In-stock products of the base's subcategory; RN04 price/tier rules stay in the engine."""
        rows = await self._recommendation_rows(
            f"""
            SELECT {_PRODUCT_COLUMNS} FROM products
            WHERE is_active AND stock_quantity > 0 AND category = %s AND subcategory = %s
              AND sku <> %s
            ORDER BY sku
            """,
            (base.category, base.subcategory, base.sku),
        )
        return [CatalogProduct.model_validate(row) for row in rows]

    async def cross_sell_relations(self, sku: str) -> list[CrossSellRelation]:
        """CROSS_SELL rows of product_relations whose related product is in stock (RN01, RN05)."""
        columns = ", ".join(f"related.{column.strip()}" for column in _PRODUCT_COLUMNS.split(","))
        rows = await self._recommendation_rows(
            f"""
            SELECT {columns}, relation.affinity_weight, relation.justification_template
            FROM product_relations relation
            JOIN products base ON base.id = relation.base_product_id
            JOIN products related ON related.id = relation.related_product_id
            WHERE base.sku = %s AND relation.relation_type = 'CROSS_SELL'
              AND related.is_active AND related.stock_quantity > 0
            ORDER BY related.sku
            """,
            (sku,),
        )
        return [
            CrossSellRelation(
                affinity_weight=row.pop("affinity_weight"),
                justification_template=row.pop("justification_template"),
                product=CatalogProduct.model_validate(row),
            )
            for row in rows
        ]

    async def max_similarities(
        self, skus: Sequence[str], embedding: Sequence[float]
    ) -> dict[str, float]:
        """Best cosine similarity between the query and each product's chunks (sim(q, u))."""
        rows = await self._recommendation_rows(
            """
            SELECT sku, MAX(GREATEST(0, 1 - (embedding <=> %s::vector))) AS similarity
            FROM manual_chunks WHERE sku = ANY(%s) GROUP BY sku
            """,
            (vector_literal(embedding), list(skus)),
        )
        return {row["sku"]: float(row["similarity"]) for row in rows}

    async def _recommendation_rows(
        self, query: str, parameters: Sequence[object]
    ) -> list[dict[str, Any]]:
        try:
            async with await psycopg.AsyncConnection.connect(self._conninfo) as conn:
                cursor = conn.cursor(row_factory=dict_row)
                await cursor.execute(query.encode(), parameters)
                return await cursor.fetchall()
        except psycopg.Error as error:
            raise RecommendationLookupError("recommendation lookup failed") from error


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
    conn: psycopg.AsyncConnection[object], product_id: UUID, manual_source: str
) -> str | None:
    cursor = await conn.execute(
        "SELECT manual_version FROM manual_chunks WHERE product_id = %s AND manual_source = %s "
        "LIMIT 1",
        (product_id, manual_source),
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
        await conn.execute(
            "DELETE FROM manual_chunks WHERE product_id = %s AND manual_source = %s",
            (product_id, manual_source),
        )
        async with conn.cursor() as cursor:
            await cursor.executemany(
                """
                INSERT INTO manual_chunks (product_id, sku, manual_title, page_number,
                    chunk_index, manual_source, manual_version, content, embedding)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s::vector)
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
                    )
                    for row in rows
                ],
            )


async def start_ingestion_job(
    conn: psycopg.AsyncConnection[object],
    *,
    product_id: UUID,
    source_file: str,
    content_hash: str,
) -> None:
    """Open (or reopen) the job of this source version as RUNNING and count the attempt."""
    await conn.execute(
        """
        INSERT INTO ingestion_jobs (product_id, source_file, content_hash, status, attempts)
        VALUES (%s, %s, %s, 'RUNNING', 1)
        ON CONFLICT (source_file, content_hash) DO UPDATE SET
            product_id = EXCLUDED.product_id, status = 'RUNNING',
            attempts = ingestion_jobs.attempts + 1, last_error = NULL, updated_at = NOW()
        """,
        (product_id, source_file, content_hash),
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


async def replace_product_relations(
    conn: psycopg.AsyncConnection[object], relations: Sequence[ProductRelation]
) -> int:
    """The seed is the source of truth: relations absent from it stop being offered."""
    async with conn.transaction():
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
