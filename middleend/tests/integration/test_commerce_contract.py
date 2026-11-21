"""Validate the four public endpoints against OpenAPI on a real PostgreSQL."""

import asyncio
import json
import os
from collections.abc import AsyncIterator, Iterator, Mapping
from contextlib import asynccontextmanager
from decimal import Decimal
from pathlib import Path
from uuid import uuid4

import httpx
import psycopg
import pytest
from app.config import Settings
from app.main import create_app
from app.sessions.store import HistoryItem
from app.sse.models import BackendStream
from jsonschema import Draft202012Validator, FormatChecker
from psycopg import sql
from psycopg.conninfo import make_conninfo
from redis import Redis

ROOT = Path(__file__).resolve().parents[3]
OPENAPI = json.loads((ROOT / "openapi.yaml").read_text(encoding="utf-8"))
SKU = "AF-400-220V"
PRODUCT_URL = "https://example.com/airfryer"


def assert_contract(response: httpx.Response, path: str, status: int) -> dict:
    assert response.status_code == status, response.text
    operation = OPENAPI["paths"]["/api/v1" + path][response.request.method.lower()]
    schema = operation["responses"][str(status)]["content"]["application/json"]["schema"]
    payload = response.json()
    # Use decimal arithmetic for OpenAPI's multipleOf: 0.01 checks.
    Draft202012Validator(
        json.loads(
            json.dumps({**schema, "components": OPENAPI["components"]}), parse_float=Decimal
        ),
        format_checker=FormatChecker(),
    ).validate(json.loads(response.text, parse_float=Decimal))
    return payload


REDIS_URL = os.environ.get("TEST_REDIS_URL", "")
RATE_LIMIT_OFF = 1_000_000


@pytest.fixture
def database_url() -> Iterator[str]:
    base_url = os.environ.get("TEST_DATABASE_URL")
    if not base_url or not REDIS_URL:
        pytest.skip("TEST_DATABASE_URL and TEST_REDIS_URL required")
    # A whole database per test: the gateway sets connection options, so search_path can't isolate.
    # Cached answers would skip the stub; HTTP counters would leak into the metrics tests.
    with Redis.from_url(REDIS_URL) as redis:
        stale = [*redis.scan_iter("cache:sem:*"), *redis.scan_iter("metrics:http:*")]
        if stale:
            redis.delete(*stale)
    database_name = "commerce_test_" + uuid4().hex
    database = sql.Identifier(database_name)
    with psycopg.connect(base_url, autocommit=True) as admin:
        admin.execute(sql.SQL("CREATE DATABASE {}").format(database))
        try:
            url = make_conninfo(base_url, dbname=database_name)
            products_ddl = (ROOT / "backend/app/db/schema.sql").read_text(encoding="utf-8")
            with psycopg.connect(url) as connection:
                connection.execute(products_ddl)
                connection.execute(
                    """
                    INSERT INTO products
                        (sku, name, category, subcategory, brand, price, stock_quantity,
                         voltage, image_url, checkout_url, is_active)
                    VALUES
                        (%s, 'Airfryer', 'Kitchen', 'Airfryers', 'SmartChef', 499.90, 1,
                         '220V', '/airfryer.svg', %s, true),
                        ('KIT', 'Airfryer Kit', 'Kitchen', 'Accessories', 'SmartChef', 50, 2,
                         'N/A', '/kit.svg', %s, true),
                        ('AF-127V', 'Airfryer 127V', 'Kitchen', 'Airfryers', 'SmartChef', 400, 1,
                         '127V', '/airfryer.svg', %s, true),
                        ('EMPTY', 'Out of stock', 'Kitchen', 'Airfryers', 'SmartChef', 300, 0,
                         '220V', '/airfryer.svg', %s, true),
                        ('INACTIVE', 'Inactive', 'Kitchen', 'Airfryers', 'SmartChef', 300, 4,
                         '220V', '/airfryer.svg', %s, false)
                    """,
                    (SKU, PRODUCT_URL, PRODUCT_URL, PRODUCT_URL, PRODUCT_URL, PRODUCT_URL),
                )
            yield url
        finally:
            admin.execute(sql.SQL("DROP DATABASE {} WITH (FORCE)").format(database))


class StubBackend:
    def __init__(self, fallback: bool) -> None:
        if fallback:
            self.events = [
                {
                    "event": "error",
                    "data": {
                        "code": "LOW_SIMILARITY_FALLBACK",
                        "recoverable": True,
                        "fallback_message": "O manual não informa.",
                    },
                },
                {"event": "end", "data": {"tokens_used": 0, "intent": "LOW_SIMILARITY"}},
            ]
        else:
            self.events = [
                {"event": "token", "data": {"delta": "O modelo é 220V."}},
                {"event": "end", "data": {"tokens_used": 4, "intent": "TECHNICAL_QA"}},
            ]

    def open_stream(
        self, sku: str, question: str, history: list[HistoryItem], **filters: object
    ) -> BackendStream:
        events = iter(self.events)

        class Stream:
            def __aiter__(self) -> "Stream":
                return self

            async def __anext__(self) -> Mapping[str, object]:
                event = next(events, None)
                if event is None:
                    raise StopAsyncIteration
                return event

            async def aclose(self) -> None:
                pass

        return Stream()


@asynccontextmanager
async def client_for(
    database_url: str,
    *,
    fallback: bool = False,
    decrement_stock: bool = True,
    admin_token: str | None = None,
    session_ttl_seconds: int = 1800,
) -> AsyncIterator[httpx.AsyncClient]:
    settings = Settings(
        database_url=database_url,
        redis_url=REDIS_URL,
        checkout_decrement_stock=decrement_stock,
        admin_token=admin_token,
        session_ttl_seconds=session_ttl_seconds,
        # Not a rate-limit test: the shared Redis bucket of 127.0.0.1 must not trip
        # (M01, #36; the field is ignored by Settings until M01 is merged).
        rate_limit_per_minute=RATE_LIMIT_OFF,
    )
    app = create_app(settings, StubBackend(fallback))
    async with (
        app.router.lifespan_context(app),
        httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://gateway/api/v1"
        ) as client,
    ):
        yield client


async def new_turn(client: httpx.AsyncClient, expected_reason: str = "stop") -> dict[str, str]:
    session = await client.post("sessions", json={"current_product_sku": SKU})
    assert session.status_code == 201
    session_id = session.json()["session_id"]
    answer = await client.post(
        "chat/stream",
        json={
            "session_id": session_id,
            "client_request_id": str(uuid4()),
            "message": "Qual a voltagem?",
        },
    )
    events = [
        json.loads(line[6:]) for line in answer.text.splitlines() if line.startswith("data: ")
    ]
    assert events[-1]["finish_reason"] == expected_reason, answer.text
    return {"session_id": session_id, "message_id": events[0]["message_id"]}


def test_catalog_reads_active_in_stock_products_with_stable_paging(database_url: str) -> None:
    async def scenario() -> None:
        async with client_for(database_url) as client:
            params = {"q": "AIRFRYER", "category": "Kitchen", "voltage": "220V", "page_size": 1}
            for page, skus in [(1, [SKU]), (2, ["KIT"]), (3, [])]:
                response = await client.get("products", params={**params, "page": page})
                catalog = assert_contract(response, "/products", 200)
                assert [item["sku"] for item in catalog["items"]] == skus
                assert (catalog["total"], catalog["page"], catalog["page_size"]) == (2, page, 1)
            assert_contract(await client.get("products?page_size=101"), "/products", 422)
            assert_contract(await client.get("products?voltage=BIVOLT"), "/products", 422)

    asyncio.run(scenario())


def test_product_detail_includes_current_price_even_when_out_of_stock(database_url: str) -> None:
    async def scenario() -> None:
        async with client_for(database_url) as client:
            product = assert_contract(await client.get("products/EMPTY"), "/products/{sku}", 200)
            assert product["stock_quantity"] == 0
            assert product["price"] == 300
            assert product["description"] is None  # optional: older seeds have none
            with psycopg.connect(database_url) as connection:
                connection.execute(
                    "UPDATE products SET description = 'Fritadeira sem óleo.' WHERE sku = 'EMPTY'"
                )
            described = assert_contract(await client.get("products/EMPTY"), "/products/{sku}", 200)
            assert described["description"] == "Fritadeira sem óleo."
            for sku in ("INACTIVE", "UNKNOWN"):
                assert_contract(await client.get(f"products/{sku}"), "/products/{sku}", 404)

    asyncio.run(scenario())


@pytest.mark.parametrize("rating,reason", [("LIKE", None), ("DISLIKE", "WRONG_VOLTAGE")])
def test_feedback_belongs_to_the_chat_message(
    database_url: str, rating: str, reason: str | None
) -> None:
    async def scenario() -> None:
        async with client_for(database_url) as client:
            turn = await new_turn(client)
            request = {**turn, "rating": rating, "reason_category": reason, "comment": "Teste"}
            wrong_session = await client.post("sessions", json={"current_product_sku": SKU})
            assert_contract(
                await client.post(
                    "feedback", json={**request, "session_id": wrong_session.json()["session_id"]}
                ),
                "/feedback",
                404,
            )
            assert_contract(
                await client.post(
                    "feedback", json={**request, "rating": "DISLIKE", "reason_category": None}
                ),
                "/feedback",
                422,
            )
            saved = assert_contract(await client.post("feedback", json=request), "/feedback", 201)
            assert_contract(await client.post("feedback", json=request), "/feedback", 409)
            with psycopg.connect(database_url) as connection:
                rows = connection.execute(
                    "SELECT id::text, message_id::text, rating, reason_category, comment FROM feedback_logs"
                ).fetchall()
            assert rows == [(saved["feedback_id"], turn["message_id"], rating, reason, "Teste")]

    asyncio.run(scenario())


def test_checkout_revalidates_price_and_serializes_purchases_of_last_unit(
    database_url: str,
) -> None:
    async def scenario() -> None:
        async with client_for(database_url) as client:
            turn = await new_turn(client)
            request = {
                **turn,
                "sku": SKU,
                "quantity": 1,
                "recommendation_type": "PRIMARY",
                "displayed_price": 499.90,
            }
            with psycopg.connect(database_url) as connection:
                connection.execute("UPDATE products SET price = 519.90 WHERE sku = %s", (SKU,))
            stale = assert_contract(
                await client.post("checkout/mock", json=request), "/checkout/mock", 409
            )
            assert (stale["status"], stale["current_price"], stale["current_stock"]) == (
                "PRICE_CHANGED",
                519.90,
                1,
            )
            assert stale["redirect_checkout_url"] is None
            invalid = await client.post("checkout/mock", json={**request, "quantity": 0})
            assert_contract(invalid, "/checkout/mock", 422)
            current = {**request, "displayed_price": 519.90}
            responses = await asyncio.gather(
                *(client.post("checkout/mock", json=current) for _ in range(2))
            )
            success, failure = sorted(responses, key=lambda response: response.status_code)
            confirmed = assert_contract(success, "/checkout/mock", 200)
            assert confirmed["confirmed_unit_price"] == 519.90
            assert confirmed["total_amount"] == 519.90
            assert confirmed["remaining_stock"] == 0
            assert confirmed["redirect_checkout_url"] == PRODUCT_URL
            rejected = assert_contract(failure, "/checkout/mock", 409)
            assert (
                rejected["status"],
                rejected["current_stock"],
                rejected["redirect_checkout_url"],
            ) == (
                "OUT_OF_STOCK",
                0,
                None,
            )
            with psycopg.connect(database_url) as connection:
                attempts = connection.execute(
                    "SELECT status FROM checkout_events ORDER BY status"
                ).fetchall()
            assert attempts == [("CONFIRMED",), ("OUT_OF_STOCK",), ("PRICE_CHANGED",)]

    asyncio.run(scenario())


def test_catalog_checkout_can_record_conversion_without_decrementing_stock(
    database_url: str,
) -> None:
    async def scenario() -> None:
        async with client_for(database_url, decrement_stock=False) as client:
            request = {
                **await new_turn(client),
                "sku": "KIT",
                "quantity": 2,
                "recommendation_type": "CROSS_SELL",
                "displayed_price": 50,
            }
            checkout = assert_contract(
                await client.post("checkout/mock", json=request), "/checkout/mock", 200
            )
            assert checkout["total_amount"] == 100
            assert checkout["remaining_stock"] == 2
            product = assert_contract(await client.get("products/KIT"), "/products/{sku}", 200)
            assert product["stock_quantity"] == 2

    asyncio.run(scenario())


def test_fallback_with_diagnostic_intent_still_completes_with_database(database_url: str) -> None:
    async def scenario() -> None:
        async with client_for(database_url, fallback=True) as client:
            turn = await new_turn(client, expected_reason="fallback")
            with psycopg.connect(database_url) as connection:
                message = connection.execute(
                    "SELECT role, intent FROM chat_messages WHERE id = %s", (turn["message_id"],)
                ).fetchone()
            assert message == ("assistant", None)

    asyncio.run(scenario())


def test_feedback_and_checkout_reject_an_ended_session(database_url: str) -> None:
    async def scenario() -> None:
        async with client_for(database_url) as client:
            turn = await new_turn(client)
            assert (await client.delete(f"sessions/{turn['session_id']}")).status_code == 204
            feedback = await client.post("feedback", json={**turn, "rating": "LIKE"})
            assert_contract(feedback, "/feedback", 410)
            checkout = await client.post(
                "checkout/mock",
                json={
                    **turn,
                    "sku": SKU,
                    "quantity": 1,
                    "recommendation_type": "PRIMARY",
                    "displayed_price": 499.90,
                },
            )
            assert_contract(checkout, "/checkout/mock", 410)

    asyncio.run(scenario())


def test_gateway_starts_before_ingestion_and_creates_commerce_tables_later(
    database_url: str,
) -> None:
    async def scenario() -> None:
        with psycopg.connect(database_url, autocommit=True) as connection:
            connection.execute("DROP TABLE products CASCADE")
        async with client_for(database_url) as client:
            turn = await new_turn(client)
            not_ready = await client.post("feedback", json={**turn, "rating": "LIKE"})
            assert_contract(not_ready, "/feedback", 503)
            products_ddl = (ROOT / "backend/app/db/schema.sql").read_text(encoding="utf-8")
            with psycopg.connect(database_url) as connection:
                connection.execute(products_ddl)
            ready = await client.post("feedback", json={**turn, "rating": "LIKE"})
            assert_contract(ready, "/feedback", 201)

    asyncio.run(scenario())


def test_price_change_and_last_unit_sale_bump_catalog_version(database_url: str) -> None:
    # RN09: cached answers under the old catalog:version must stop being served.
    def version() -> int:
        with Redis.from_url(REDIS_URL) as redis:
            return int(redis.get("catalog:version") or 0)

    async def scenario() -> None:
        async with client_for(database_url) as client:
            turn = await new_turn(client)
            request = {
                **turn,
                "sku": SKU,
                "quantity": 1,
                "recommendation_type": "PRIMARY",
                "displayed_price": 499.90,
            }
            start = version()
            with psycopg.connect(database_url) as connection:
                connection.execute("UPDATE products SET price = 519.90 WHERE sku = %s", (SKU,))
            stale = await client.post("checkout/mock", json=request)
            assert stale.status_code == 409
            assert version() == start + 1
            sold = await client.post("checkout/mock", json={**request, "displayed_price": 519.90})
            assert sold.json()["remaining_stock"] == 0
            assert version() == start + 2
            kit = await client.post(
                "checkout/mock",
                json={**request, "sku": "KIT", "displayed_price": 50},
            )
            assert kit.json()["remaining_stock"] == 1
            assert version() == start + 2  # stock left and same price: no bump

    asyncio.run(scenario())


def test_checkout_accepts_option_role_and_migrates_legacy_constraint_idempotently(
    database_url: str,
) -> None:
    async def scenario() -> None:
        async with client_for(database_url) as client:
            turn = await new_turn(client)
            with psycopg.connect(database_url) as connection:
                connection.execute(
                    "ALTER TABLE checkout_events "
                    "DROP CONSTRAINT IF EXISTS checkout_events_recommendation_type_check"
                )
                connection.execute(
                    "ALTER TABLE checkout_events "
                    "ADD CONSTRAINT checkout_events_recommendation_type_check "
                    "CHECK (recommendation_type IN ('PRIMARY', 'UPSELL', 'CROSS_SELL'))"
                )
            commerce = client._transport.app.state.commerce  # type: ignore[attr-defined]
            assert await commerce.initialize() is True
            assert await commerce.initialize() is True

            response = await client.post(
                "checkout/mock",
                json={
                    **turn,
                    "sku": "KIT",
                    "quantity": 1,
                    "recommendation_type": "OPTION",
                    "displayed_price": 50,
                },
            )
            confirmed = assert_contract(response, "/checkout/mock", 200)
            assert confirmed["status"] == "CONFIRMED"
            with psycopg.connect(database_url) as connection:
                row = connection.execute(
                    "SELECT recommendation_type FROM checkout_events WHERE id = %s",
                    (confirmed["checkout_event_id"],),
                ).fetchone()
            assert row == ("OPTION",)

    asyncio.run(scenario())


@pytest.mark.parametrize(
    ("ttl_seconds", "inactive_seconds", "age_days"),
    [(1800, 1860, 0), (120, 121, 0), (1800, 0, 91)],
)
def test_expired_active_session_cannot_record_feedback_or_checkout(
    database_url: str, ttl_seconds: int, inactive_seconds: int, age_days: int
) -> None:
    async def scenario() -> None:
        async with client_for(database_url, session_ttl_seconds=ttl_seconds) as client:
            turn = await new_turn(client)
            with psycopg.connect(database_url) as connection:
                connection.execute(
                    "UPDATE chat_sessions SET "
                    "last_active_at=clock_timestamp()-make_interval(secs => %s), "
                    "created_at=clock_timestamp()-make_interval(days => %s) WHERE id=%s",
                    (inactive_seconds, age_days, turn["session_id"]),
                )
                assert connection.execute(
                    "SELECT state FROM chat_sessions WHERE id=%s", (turn["session_id"],)
                ).fetchone() == ("ACTIVE",)
            feedback = await client.post("feedback", json={**turn, "rating": "LIKE"})
            checkout = await client.post(
                "checkout/mock",
                json={
                    **turn,
                    "sku": SKU,
                    "quantity": 1,
                    "recommendation_type": "PRIMARY",
                    "displayed_price": 499.90,
                },
            )
            for response, path in [(feedback, "/feedback"), (checkout, "/checkout/mock")]:
                result = assert_contract(response, path, 410)
                assert result["error"]["code"] == "SESSION_ENDED"
            with psycopg.connect(database_url) as connection:
                assert connection.execute("SELECT count(*) FROM feedback_logs").fetchone() == (0,)
                assert connection.execute("SELECT count(*) FROM checkout_events").fetchone() == (0,)
                assert connection.execute(
                    "SELECT stock_quantity FROM products WHERE sku=%s", (SKU,)
                ).fetchone() == (1,)

    asyncio.run(scenario())


def test_commerce_respects_a_session_ttl_longer_than_thirty_minutes(database_url: str) -> None:
    async def scenario() -> None:
        async with client_for(database_url, session_ttl_seconds=3600) as client:
            turn = await new_turn(client)
            with psycopg.connect(database_url) as connection:
                connection.execute(
                    "UPDATE chat_sessions SET last_active_at=clock_timestamp()-INTERVAL '31 minutes' "
                    "WHERE id=%s",
                    (turn["session_id"],),
                )
            assert_contract(
                await client.post("feedback", json={**turn, "rating": "LIKE"}), "/feedback", 201
            )
            assert_contract(
                await client.post(
                    "checkout/mock",
                    json={
                        **turn,
                        "sku": SKU,
                        "quantity": 1,
                        "recommendation_type": "PRIMARY",
                        "displayed_price": 499.90,
                    },
                ),
                "/checkout/mock",
                200,
            )

    asyncio.run(scenario())
