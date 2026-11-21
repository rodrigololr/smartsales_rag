"""Read-only PostgreSQL + pgvector adapter for the unified consultant (spec §3 and §11 A3)."""

from collections.abc import Sequence
from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Literal, Protocol

import psycopg
from psycopg.rows import dict_row

from app.db.repository import _PRODUCT_COLUMNS, vector_literal
from app.models.schemas import CatalogProduct, RetrievedChunk


class ConsultantLookupError(RuntimeError):
    """Database read failure inside the consultant repository."""


@dataclass(frozen=True)
class CatalogQuery:
    categories: tuple[str, ...]
    subcategories: tuple[str, ...] | None = None
    budget_max: Decimal | None = None
    voltage: Literal["127V", "220V"] | None = None


class ConsultantCatalog(Protocol):
    async def products(self, skus: Sequence[str]) -> list[CatalogProduct]: ...
    async def search(self, query: CatalogQuery) -> list[CatalogProduct]: ...
    async def categories_in_stock(self) -> list[tuple[str, str]]: ...
    async def game_tables(self, skus: Sequence[str]) -> list[RetrievedChunk]: ...
    async def knowledge_doc(self, doc_id: str) -> list[RetrievedChunk]: ...
    async def knowledge_page(self, doc_id: str, page: int) -> list[RetrievedChunk]: ...
    async def search_knowledge(
        self, embedding: Sequence[float], limit: int
    ) -> list[RetrievedChunk]: ...


class PostgresConsultantCatalog:
    """PostgreSQL implementation of ConsultantCatalog."""

    def __init__(self, conninfo: str) -> None:
        self._conninfo = conninfo

    async def products(self, skus: Sequence[str]) -> list[CatalogProduct]:
        """Active products of any stock quantity, returned in the caller's input order."""
        if not skus:
            return []
        rows = await self._fetch_rows(
            f"SELECT {_PRODUCT_COLUMNS} FROM products WHERE is_active AND sku = ANY(%s)",
            (list(skus),),
        )
        by_sku = {row["sku"]: CatalogProduct.model_validate(row) for row in rows}
        return [by_sku[sku] for sku in skus if sku in by_sku]

    async def search(self, query: CatalogQuery) -> list[CatalogProduct]:
        """In-stock active products matching structured filters, ordered by price then sku."""
        if not query.categories:
            return []
        rows = await self._fetch_rows(
            f"""
            SELECT {_PRODUCT_COLUMNS} FROM products
            WHERE is_active AND stock_quantity > 0 AND category = ANY(%(categories)s)
              AND (%(subcats)s::text[] IS NULL OR subcategory = ANY(%(subcats)s))
              AND (%(budget)s::numeric IS NULL OR price <= %(budget)s)
              AND (%(voltage)s::text IS NULL OR voltage IN (%(voltage)s, 'BIVOLT', 'N/A'))
            ORDER BY price, sku
            """,
            {
                "categories": list(query.categories),
                "subcats": list(query.subcategories) if query.subcategories else None,
                "budget": query.budget_max,
                "voltage": query.voltage,
            },
        )
        return [CatalogProduct.model_validate(row) for row in rows]

    async def categories_in_stock(self) -> list[tuple[str, str]]:
        rows = await self._fetch_rows(
            """
            SELECT DISTINCT category, subcategory
            FROM products
            WHERE is_active AND stock_quantity > 0
            ORDER BY category, subcategory
            """,
            (),
        )
        return [(str(row["category"]), str(row["subcategory"])) for row in rows]

    async def game_tables(self, skus: Sequence[str]) -> list[RetrievedChunk]:
        if not skus:
            return []
        rows = await self._fetch_rows(
            """
            SELECT id AS chunk_id, sku, manual_title, page_number, section_title, content,
                   1.0 AS similarity_score
            FROM manual_chunks
            WHERE sku = ANY(%s)
              AND manual_source LIKE 'manual:%%'
              AND content ILIKE '%%Desempenho em jogos%%'
            ORDER BY sku, page_number, chunk_index
            """,
            (list(skus),),
        )
        return [RetrievedChunk.model_validate(row) for row in rows]

    async def knowledge_doc(self, doc_id: str) -> list[RetrievedChunk]:
        rows = await self._fetch_rows(
            """
            SELECT id AS chunk_id, doc_id AS sku, title AS manual_title, page_number,
                   NULL AS section_title, content, 1.0 AS similarity_score
            FROM knowledge_chunks
            WHERE doc_id = %s
            ORDER BY page_number, chunk_index
            """,
            (doc_id,),
        )
        return [RetrievedChunk.model_validate(row) for row in rows]

    async def knowledge_page(self, doc_id: str, page: int) -> list[RetrievedChunk]:
        rows = await self._fetch_rows(
            """
            SELECT id AS chunk_id, doc_id AS sku, title AS manual_title, page_number,
                   NULL AS section_title, content, 1.0 AS similarity_score
            FROM knowledge_chunks
            WHERE doc_id = %s AND page_number = %s
            ORDER BY chunk_index
            """,
            (doc_id, page),
        )
        return [RetrievedChunk.model_validate(row) for row in rows]

    async def search_knowledge(
        self, embedding: Sequence[float], limit: int
    ) -> list[RetrievedChunk]:
        query_vec = vector_literal(embedding)
        rows = await self._fetch_rows(
            """
            SELECT id AS chunk_id, doc_id AS sku, title AS manual_title, page_number,
                   NULL AS section_title, content,
                   GREATEST(0, 1 - (embedding <=> %s::vector)) AS similarity_score
            FROM knowledge_chunks
            ORDER BY embedding <=> %s::vector
            LIMIT %s
            """,
            (query_vec, query_vec, limit),
        )
        return [RetrievedChunk.model_validate(row) for row in rows]

    async def _fetch_rows(
        self, query: str, parameters: Sequence[object] | dict[str, object]
    ) -> list[dict[str, Any]]:
        try:
            async with await psycopg.AsyncConnection.connect(self._conninfo) as conn:
                cursor = conn.cursor(row_factory=dict_row)
                await cursor.execute(query.encode("utf-8"), parameters)
                return await cursor.fetchall()
        except psycopg.Error as error:
            raise ConsultantLookupError("consultant database lookup failed") from error
