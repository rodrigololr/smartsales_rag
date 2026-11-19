"""Validate stored offer facts against one current SQL snapshot before replay."""

from collections.abc import Mapping
from dataclasses import replace
from decimal import Decimal

from psycopg import AsyncConnection

from app.sse.models import CompletedTurn, ProductCard

STALE_MESSAGE = (
    "Os dados do catálogo mudaram. Envie uma nova pergunta para consultar as ofertas atuais."
)
CARD_FIELDS = (
    "name",
    "stock_quantity",
    "voltage",
    "capacity_liters",
    "power_watts",
    "image_url",
    "marketplace",
    "checkout_url",
)


def _matches(card: ProductCard, product: dict[str, object] | None) -> bool:
    if product is None or not product["is_active"] or product["stock_quantity"] == 0:
        return False
    if Decimal(str(card["price"])) != product["price"]:
        return False
    facts: Mapping[str, object] = card
    for field in CARD_FIELDS:
        if field not in facts:
            continue
        actual = facts[field]
        if field == "capacity_liters" and actual is not None:
            actual = Decimal(str(actual))
        if actual != product[field]:
            return False
    return True


async def validated_replay(
    connection: AsyncConnection[dict[str, object]], turn: CompletedTurn
) -> CompletedTurn:
    if not turn.products:
        return turn
    cursor = await connection.execute(
        "SELECT sku,name,price,stock_quantity,voltage,capacity_liters,power_watts,image_url,"
        "marketplace,checkout_url,is_active FROM products WHERE sku=ANY(%s)",
        ([card["sku"] for card in turn.products],),
    )
    products = {str(row["sku"]): row for row in await cursor.fetchall()}
    if all(_matches(card, products.get(card["sku"])) for card in turn.products):
        return turn
    # Delivery-specific invalidation: never regenerate the logical request or rewrite its metrics.
    return replace(
        turn,
        content=STALE_MESSAGE,
        products=(),
        citations=(),
        finish_reason="error",
        error_code="INTERNAL_ERROR",
        recoverable=True,
        tokens_used=0,
        intent=None,
    )
