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
from app.metrics import MEDIAN, P95, TOP_QUESTIONS_LIMIT, Metrics, MetricsWindow, TopQuestion
from app.sessions.postgres_store import MAX_RETENTION_DAYS

SCHEMA_FILE = Path(__file__).with_suffix(".sql")
# M04 definitions over [from, to): turns = assistant answers (failed turns included);
# card_ctr = answers with cards that got >= 1 mock checkout click (any status) / answers
# with cards; like_ratio = likes / (likes + dislikes); feedback and checkouts by their own
# created_at. Every ratio and percentile is 0 when its denominator is empty.
METRICS_SQL = """
WITH answers AS (
    SELECT id, ttft_ms, total_latency_ms, cache_hit,
           jsonb_array_length(recommended_skus) > 0 AS has_cards
    FROM chat_messages
    WHERE role = 'assistant' AND created_at >= %(from)s AND created_at < %(to)s
), ratings AS (
    SELECT count(*) FILTER (WHERE rating = 'LIKE') AS likes, count(*) AS rated
    FROM feedback_logs WHERE created_at >= %(from)s AND created_at < %(to)s
)
SELECT
    (SELECT count(*) FROM answers) AS turns,
    (SELECT coalesce(percentile_cont(%(median)s) WITHIN GROUP (ORDER BY ttft_ms), 0)
     FROM answers) AS ttft_p50_ms,
    (SELECT coalesce(percentile_cont(%(p95)s) WITHIN GROUP (ORDER BY ttft_ms), 0)
     FROM answers) AS ttft_p95_ms,
    (SELECT coalesce(percentile_cont(%(p95)s) WITHIN GROUP (ORDER BY total_latency_ms), 0)
     FROM answers) AS total_latency_p95_ms,
    (SELECT coalesce(avg(cache_hit::int), 0)::float8 FROM answers) AS cache_hit_ratio,
    (SELECT coalesce(likes::float8 / nullif(rated, 0), 0) FROM ratings) AS like_ratio,
    (SELECT coalesce(avg((EXISTS (
         SELECT 1 FROM checkout_events c WHERE c.message_id = a.id))::int), 0)::float8
     FROM answers a WHERE has_cards) AS card_ctr,
    (SELECT count(*) FROM checkout_events
     WHERE status = 'CONFIRMED' AND created_at >= %(from)s AND created_at < %(to)s
    ) AS confirmed_checkouts
"""
TOP_QUESTIONS_SQL = """
SELECT lower(btrim(content)) AS question, count(*) AS count
FROM chat_messages
WHERE role = 'user' AND created_at >= %(from)s AND created_at < %(to)s
GROUP BY 1 ORDER BY count DESC, question LIMIT %(limit)s
"""
PRODUCT_COLUMNS = sql.SQL("""
    sku, name, price, stock_quantity, voltage, capacity_liters, power_watts,
    image_url, marketplace, checkout_url, category, subcategory, brand, specs_json, description,
    updated_at
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
        session_ttl_seconds: int,
        connect_timeout_seconds: int,
        query_timeout_ms: int,
    ) -> None:
        self._database_url = database_url
        self._decrement_stock = decrement_stock
        self._session_ttl_seconds = session_ttl_seconds
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
            await _require_message(connection, request, ttl_seconds=self._session_ttl_seconds)
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
            await _require_message(connection, request, ttl_seconds=self._session_ttl_seconds)
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

    async def metrics_summary(self, window: MetricsWindow, error_5xx_rate: float) -> Metrics:
        await self._require_schema()
        params = {
            "from": window.window_from,
            "to": window.window_to,
            "median": MEDIAN,
            "p95": P95,
            "limit": TOP_QUESTIONS_LIMIT,
        }
        async with await self._connect() as connection:
            await connection.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY")
            cursor = await connection.execute(METRICS_SQL, params)
            totals = await cursor.fetchone()
            assert totals is not None
            cursor = await connection.execute(TOP_QUESTIONS_SQL, params)
            questions = [TopQuestion.model_validate(row) for row in await cursor.fetchall()]
        return Metrics(
            window=window, error_5xx_rate=error_5xx_rate, top_questions=questions, **totals
        )


async def _require_message(
    connection: AsyncConnection[DictRow], reference: MessageReference, *, ttl_seconds: int
) -> None:
    # Same lifetime rules as PostgresSessionStore._active, without renewing the TTL.
    # Hold the session row against DELETE/state updates until feedback/checkout commits.
    cursor = await connection.execute(
        """
        SELECT s.state='ACTIVE'
            AND s.last_active_at > clock_timestamp()-make_interval(secs => %s)
            AND s.created_at > clock_timestamp()-make_interval(days => %s) AS active
        FROM chat_messages m JOIN chat_sessions s ON s.id = m.session_id
        WHERE m.id = %s AND m.session_id = %s AND m.role = 'assistant'
        FOR SHARE OF s FOR KEY SHARE OF m
        """,
        (ttl_seconds, MAX_RETENTION_DAYS, reference.message_id, reference.session_id),
    )
    message = await cursor.fetchone()
    if message is None:
        raise MessageNotFound
    if not message["active"]:
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
