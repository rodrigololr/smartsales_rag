"""Read-only access to `products` (ADR-06: the backend writes it, the gateway reads it)."""

from collections.abc import Sequence
from decimal import Decimal

import psycopg

from app.cache.service import CacheUnavailableError, ProductSnapshot


class PostgresProductSnapshots:
    """Price, stock and status of this instant (RN01, R09).

    shortcut: one connection per call; switch to psycopg_pool before load testing.
    """

    def __init__(self, conninfo: str) -> None:
        self._conninfo = conninfo

    async def current(self, skus: Sequence[str]) -> dict[str, ProductSnapshot]:
        try:
            async with await psycopg.AsyncConnection.connect(self._conninfo) as conn:
                cursor = await conn.execute(
                    "SELECT sku, price, stock_quantity, is_active FROM products "
                    "WHERE sku = ANY(%s)",
                    (list(skus),),
                )
                rows = await cursor.fetchall()
        except psycopg.Error as error:
            raise CacheUnavailableError("product revalidation failed") from error
        return {
            str(sku): ProductSnapshot(Decimal(price), int(stock_quantity), bool(is_active))
            for sku, price, stock_quantity, is_active in rows
        }
