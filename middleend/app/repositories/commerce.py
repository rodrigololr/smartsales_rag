"""PostgreSQL access for the gateway's catalog and commerce endpoints."""

from pathlib import Path
from uuid import UUID

from psycopg import AsyncConnection, sql
from psycopg.rows import DictRow, dict_row

from app.commerce import (
    Catalog,
    CatalogNotReady,
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
    SessionEnded,
    checkout_conflict,
)

SCHEMA_FILE = Path(__file__).with_suffix(".sql")
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
    """shortcut: one connection per call (like the session store); pool before load tests."""

    def __init__(
        self,
        database_url: str,
        *,
        decrement_stock: bool,
        connect_timeout_seconds: int,
        query_timeout_ms: int,
    ) -> None:
        self._database_url = database_url
        self._decrement_stock = decrement_stock
        self._connect_timeout_seconds = connect_timeout_seconds
        self._query_timeout_ms = query_timeout_ms
        self._schema_ready = False

    async def _connect(self) -> AsyncConnection[DictRow]:
        # Bounded: an unreachable or locked database must fail the request, not hang it.
        timeout = self._query_timeout_ms
        return await AsyncConnection.connect(
            self._database_url,
            row_factory=dict_row,
            connect_timeout=self._connect_timeout_seconds,
            options=f"-c statement_timeout={timeout} -c lock_timeout={timeout}",
        )

    async def initialize(self) -> bool:
        """Create the M05 tables; False while the backend has not created `products` yet."""
        async with await self._connect() as connection:
            await connection.execute(
                "SELECT pg_advisory_xact_lock(hashtext('gateway-commerce-ddl'))"
            )
            cursor = await connection.execute("SELECT to_regclass('products') IS NOT NULL AS ok")
            products_exist = await cursor.fetchone()
            if products_exist is None or not products_exist["ok"]:
                return False
            await connection.execute(sql.SQL(SCHEMA_FILE.read_text(encoding="utf-8")))
        self._schema_ready = True
        return True

    async def _require_schema(self) -> None:
        if not self._schema_ready and not await self.initialize():
            raise CatalogNotReady

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

    async def record_feedback(self, request: FeedbackCreate) -> FeedbackRecorded:
        await self._require_schema()
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
        await self._require_schema()
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
        SELECT s.state FROM chat_messages m JOIN chat_sessions s ON s.id = m.session_id
        WHERE m.id = %s AND m.session_id = %s AND m.role = 'assistant' FOR KEY SHARE OF m
        """,
        (reference.message_id, reference.session_id),
    )
    message = await cursor.fetchone()
    if message is None:
        raise MessageNotFound
    if message["state"] != "ACTIVE":
        raise SessionEnded


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
