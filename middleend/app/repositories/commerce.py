"""PostgreSQL access for the gateway's catalog and commerce endpoints."""

from pathlib import Path
from uuid import UUID

from app.commerce import (
    Catalog,
    CatalogQuery,
    Checkout,
    CheckoutConflict,
    CheckoutCreate,
    FeedbackAlreadyRecorded,
    FeedbackCreate,
    FeedbackRecorded,
    MessageNotFound,
    MessageReference,
    Product,
    ProductNotFound,
    checkout_conflict,
)
from app.sse.models import CompletedTurn
from psycopg import AsyncConnection, sql
from psycopg.rows import DictRow, dict_row
from psycopg.types.json import Jsonb

SCHEMA_FILE = Path(__file__).with_suffix(".sql")
STORED_INTENTS = {"TECHNICAL_QA", "PRODUCT_COMPARISON", "PURCHASE_INTENT", "OUT_OF_DOMAIN"}
PRODUCT_COLUMNS = sql.SQL("""
    sku, name, price, stock_quantity, voltage, capacity_liters, power_watts,
    image_url, marketplace, checkout_url, category, subcategory, brand, specs_json, updated_at
""")
CATALOG_WHERE = sql.SQL("""
    WHERE is_active AND stock_quantity > 0
      AND (%(q)s::text IS NULL OR strpos(lower(name), lower(%(q)s::text)) > 0
           OR strpos(lower(sku), lower(%(q)s::text)) > 0)
      AND (%(category)s::text IS NULL OR category = %(category)s::text)
      AND (%(voltage)s::text IS NULL OR voltage IN (%(voltage)s::text, 'BIVOLT', 'N/A'))
""")


class PostgresCommerce:
    def __init__(self, database_url: str, *, decrement_stock: bool) -> None:
        self._database_url = database_url
        self._decrement_stock = decrement_stock

    async def _connect(self) -> AsyncConnection[DictRow]:
        return await AsyncConnection.connect(self._database_url, row_factory=dict_row)

    async def initialize(self) -> None:
        async with await self._connect() as connection:
            await connection.execute(
                "SELECT pg_advisory_xact_lock(hashtext('gateway-commerce-ddl'))"
            )
            await connection.execute(sql.SQL(SCHEMA_FILE.read_text(encoding="utf-8")))

    async def list_products(self, query: CatalogQuery) -> Catalog:
        offset = (query.page - 1) * query.page_size
        async with await self._connect() as connection:
            await connection.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY")
            params = query.model_dump()
            count = await connection.execute(
                sql.SQL("SELECT count(*) AS total FROM products {}").format(CATALOG_WHERE), params
            )
            count_row = await count.fetchone()
            assert count_row is not None
            total: int = count_row["total"]
            items = []
            if offset < total:
                cursor = await connection.execute(
                    sql.SQL(
                        "SELECT {} FROM products {} ORDER BY name, sku LIMIT %(page_size)s OFFSET %(offset)s"
                    ).format(PRODUCT_COLUMNS, CATALOG_WHERE),
                    {**params, "offset": offset},
                )
                items = [Product.model_validate(row) for row in await cursor.fetchall()]
        return Catalog(items=items, page=query.page, page_size=query.page_size, total=total)

    async def get_product(self, sku: str) -> Product:
        async with await self._connect() as connection:
            cursor = await connection.execute(
                sql.SQL("SELECT {} FROM products WHERE sku = %s AND is_active").format(
                    PRODUCT_COLUMNS
                ),
                (sku,),
            )
            product = await cursor.fetchone()
        if product is None:
            raise ProductNotFound
        return Product.model_validate(product)

    async def persist_turn(self, turn: CompletedTurn) -> None:
        # The MVP backend also emits diagnostic labels such as LOW_SIMILARITY.
        intent = turn.intent if turn.intent in STORED_INTENTS else None
        async with await self._connect() as connection:
            await connection.execute(
                """
                INSERT INTO chat_sessions (id) VALUES (%s)
                ON CONFLICT (id) DO UPDATE SET last_active_at = NOW()
                """,
                (turn.session_id,),
            )
            await connection.execute(
                """
                INSERT INTO chat_messages (
                    id, session_id, role, content, citations, recommended_skus,
                    ttft_ms, total_latency_ms, tokens_used, intent, cache_hit
                ) VALUES (%s, %s, 'assistant', %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (id) DO NOTHING
                """,
                (
                    turn.message_id,
                    turn.session_id,
                    turn.content,
                    Jsonb(turn.citations),
                    Jsonb([product["sku"] for product in turn.products]),
                    turn.ttft_ms,
                    turn.total_latency_ms,
                    turn.tokens_used,
                    intent,
                    turn.cache_hit,
                ),
            )

    async def record_feedback(self, request: FeedbackCreate) -> FeedbackRecorded:
        async with await self._connect() as connection:
            await _require_message(connection, request)
            cursor = await connection.execute(
                """
                INSERT INTO feedback_logs (session_id, message_id, rating, reason_category, comment)
                VALUES (%s, %s, %s, %s, %s)
                ON CONFLICT (message_id) DO NOTHING
                RETURNING id AS feedback_id, created_at AS recorded_at
                """,
                (
                    request.session_id,
                    request.message_id,
                    request.rating,
                    request.reason_category,
                    request.comment,
                ),
            )
            recorded = await cursor.fetchone()
        if recorded is None:
            raise FeedbackAlreadyRecorded
        return FeedbackRecorded.model_validate(recorded)

    async def checkout(self, request: CheckoutCreate) -> Checkout | CheckoutConflict:
        async with await self._connect() as connection:
            await _require_message(connection, request)
            cursor = await connection.execute(
                sql.SQL(
                    "SELECT id, {} FROM products WHERE sku = %s AND is_active FOR UPDATE"
                ).format(PRODUCT_COLUMNS),
                (request.sku,),
            )
            row = await cursor.fetchone()
            if row is None:
                raise ProductNotFound
            product = Product.model_validate(row)
            conflict = checkout_conflict(product, request)
            remaining_stock = product.stock_quantity
            if conflict is None and self._decrement_stock:
                remaining_stock -= request.quantity
                await connection.execute(
                    "UPDATE products SET stock_quantity = %s, updated_at = NOW() WHERE id = %s",
                    (remaining_stock, row["id"]),
                )
            event_id = await _record_checkout(
                connection, request, row["id"], product, conflict or "CONFIRMED"
            )

        if conflict is not None:
            return CheckoutConflict(
                checkout_event_id=event_id,
                status=conflict,
                sku=product.sku,
                current_price=product.price,
                current_stock=product.stock_quantity,
                message=(
                    "Estoque insuficiente para a quantidade solicitada."
                    if conflict == "OUT_OF_STOCK"
                    else "O preço mudou. Confirme o valor atualizado."
                ),
            )
        return Checkout(
            checkout_event_id=event_id,
            sku=product.sku,
            product_name=product.name,
            voltage=product.voltage,
            marketplace=product.marketplace,
            redirect_checkout_url=product.checkout_url,
            quantity=request.quantity,
            confirmed_unit_price=product.price,
            total_amount=product.price * request.quantity,
            remaining_stock=remaining_stock,
            message="Conversão registrada com sucesso.",
        )


async def _require_message(
    connection: AsyncConnection[DictRow], reference: MessageReference
) -> None:
    cursor = await connection.execute(
        """
        SELECT id FROM chat_messages
        WHERE id = %s AND session_id = %s AND role = 'assistant' FOR KEY SHARE
        """,
        (reference.message_id, reference.session_id),
    )
    if await cursor.fetchone() is None:
        raise MessageNotFound


async def _record_checkout(
    connection: AsyncConnection[DictRow],
    request: CheckoutCreate,
    product_id: UUID,
    product: Product,
    status: str,
) -> UUID:
    cursor = await connection.execute(
        """
        INSERT INTO checkout_events (session_id, message_id, product_id, sku,
            recommendation_type, quantity, unit_price_at_click, status)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s) RETURNING id
        """,
        (
            request.session_id,
            request.message_id,
            product_id,
            product.sku,
            request.recommendation_type,
            request.quantity,
            product.price,
            status,
        ),
    )
    row = await cursor.fetchone()
    assert row is not None
    return UUID(str(row["id"]))
