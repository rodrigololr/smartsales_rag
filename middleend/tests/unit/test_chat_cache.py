"""M03 in the gateway: cache hit on /chat/stream, revalidated against stock and price."""

import asyncio
import os
import uuid
from collections.abc import Iterator
from decimal import Decimal

import psycopg
import pytest
from app.cache.redis_storage import CATALOG_VERSION_KEY, RedisCacheStorage
from app.cache.service import CacheUnavailableError, ProductSnapshot, SemanticCacheService
from app.config import Settings
from app.main import create_app
from app.repositories.products import PostgresProductSnapshots
from fastapi.testclient import TestClient
from redis.asyncio import Redis
from test_chat_routes import (
    CITATIONS,
    END,
    FALLBACK,
    TOKEN,
    FakeBackend,
    ask,
    new_session,
    sse_events,
)
from test_semantic_cache import UPSELL_CARD, FakeProducts, FakeStorage

REDIS_URL = os.environ.get("TEST_REDIS_URL", "")
DATABASE_URL = os.environ.get("TEST_DATABASE_URL", "")
CARDS = {"event": "recommendations", "data": {"products": [UPSELL_CARD]}}
SETTINGS = Settings(backend_internal_url="http://127.0.0.1:9")


def event_names(text: str) -> list[str]:
    return [name for name, _ in sse_events(text)]


@pytest.fixture
def backend() -> FakeBackend:
    return FakeBackend([TOKEN, CITATIONS, CARDS, END])


@pytest.fixture
def products() -> FakeProducts:
    return FakeProducts()


@pytest.fixture
def storage() -> FakeStorage:
    return FakeStorage()


@pytest.fixture
def client(backend: FakeBackend, storage: FakeStorage, products: FakeProducts) -> Iterator[TestClient]:
    cache = SemanticCacheService(storage, products, ttl_seconds=3600, policy_version="p1")
    with TestClient(create_app(SETTINGS, backend, cache=cache)) as test_client:
        yield test_client


def test_same_question_in_a_new_session_is_a_cache_hit_without_the_backend(
    client: TestClient, backend: FakeBackend
) -> None:
    first = sse_events(ask(client, new_session(client), str(uuid.uuid4())).text)
    second_session = new_session(client)
    second = sse_events(ask(client, second_session, str(uuid.uuid4())).text)

    assert len(backend.calls) == 1
    assert [name for name, _ in second] == ["metadata", "token", "citations", "recommendations", "done"]
    assert first[0][1]["cache_hit"] is False and second[0][1]["cache_hit"] is True
    assert second[0][1]["session_id"] == second_session
    assert second[0][1]["message_id"] != first[0][1]["message_id"]
    assert second[1][1] == first[1][1] and second[2][1] == first[2][1]
    assert second[3][1]["products"][0]["stock_quantity"] == 3  # revalidated: SQL says 3, not 8
    assert second[-1][1]["finish_reason"] == "stop"

    restored = client.post("/api/v1/sessions", json={"session_id": second_session}).json()
    assert [m["role"] for m in restored["history"]] == ["user", "assistant"]


def test_sold_out_card_forces_a_new_generation(
    client: TestClient, backend: FakeBackend, products: FakeProducts
) -> None:
    ask(client, new_session(client), str(uuid.uuid4()))
    products.snapshots["AF-550-220V"] = ProductSnapshot(Decimal("629.90"), 0, True)
    events = sse_events(ask(client, new_session(client), str(uuid.uuid4())).text)
    assert events[0][1]["cache_hit"] is False and len(backend.calls) == 2


def test_new_catalog_version_forces_a_new_generation(
    client: TestClient, backend: FakeBackend, storage: FakeStorage
) -> None:
    ask(client, new_session(client), str(uuid.uuid4()))
    storage.version += 1
    ask(client, new_session(client), str(uuid.uuid4()))
    assert len(backend.calls) == 2


def test_history_and_filters_are_part_of_the_cache_identity(
    client: TestClient, backend: FakeBackend
) -> None:
    session_id = new_session(client)
    ask(client, session_id, str(uuid.uuid4()))
    ask(client, session_id, str(uuid.uuid4()))  # same question, but now after a history
    assert len(backend.calls) == 2

    other_voltage = client.post(
        "/api/v1/chat/stream",
        json={
            "session_id": new_session(client),
            "client_request_id": str(uuid.uuid4()),
            "message": "Qual a voltagem?",
            "context_filters": {"current_product_sku": "AF-400-220V", "preferred_voltage": "127V"},
        },
    )
    assert sse_events(other_voltage.text)[0][1]["cache_hit"] is False
    assert backend.voltages == [None, None, "127V"]


def test_fallback_answers_are_not_cached(
    client: TestClient, backend: FakeBackend, storage: FakeStorage
) -> None:
    backend.events = [FALLBACK, END]
    ask(client, new_session(client), str(uuid.uuid4()))
    ask(client, new_session(client), str(uuid.uuid4()))
    assert len(backend.calls) == 2 and storage.entries == {}


def test_cache_outage_falls_back_to_the_backend(
    client: TestClient, backend: FakeBackend, storage: FakeStorage
) -> None:
    storage.failure = CacheUnavailableError("redis down")
    assert event_names(ask(client, new_session(client), str(uuid.uuid4())).text)[-1] == "done"
    assert len(backend.calls) == 1


def test_cache_is_off_without_redis_and_database(backend: FakeBackend) -> None:
    with TestClient(create_app(SETTINGS, backend)) as plain:
        assert plain.app.state.cache is None  # type: ignore[attr-defined]
        ask(plain, new_session(plain), str(uuid.uuid4()))
        ask(plain, new_session(plain), str(uuid.uuid4()))
    assert len(backend.calls) == 2


@pytest.mark.skipif(not REDIS_URL, reason="TEST_REDIS_URL not set")
def test_it_m03_01_second_request_is_served_from_real_redis(
    backend: FakeBackend, products: FakeProducts
) -> None:
    async def reset() -> None:
        redis = Redis.from_url(REDIS_URL, decode_responses=True)
        try:
            await redis.set(CATALOG_VERSION_KEY, 10)
            stale = [key async for key in redis.scan_iter("cache:sem:v10:*")]
            if stale:
                await redis.delete(*stale)
        finally:
            await redis.aclose()

    asyncio.run(reset())
    settings = Settings(backend_internal_url="http://127.0.0.1:9", redis_url=REDIS_URL)
    with TestClient(create_app(settings, backend)) as gateway:
        redis: Redis = gateway.app.state.store._redis  # type: ignore[attr-defined]
        gateway.app.state.cache = SemanticCacheService(  # type: ignore[attr-defined]
            RedisCacheStorage(redis), products, ttl_seconds=3600, policy_version="p1"
        )
        ask(gateway, new_session(gateway), str(uuid.uuid4()))
        metadata = sse_events(ask(gateway, new_session(gateway), str(uuid.uuid4())).text)[0][1]

    assert metadata["cache_hit"] is True and len(backend.calls) == 1
    assert int(str(metadata["ttft_ms"])) < 200


@pytest.mark.skipif(not REDIS_URL, reason="TEST_REDIS_URL not set")
def test_redis_storage_maps_an_unreachable_server_to_cache_unavailable() -> None:
    async def scenario() -> None:
        redis = Redis.from_url("redis://127.0.0.1:1/0", socket_connect_timeout=1)
        storage = RedisCacheStorage(redis)
        try:
            for operation in (
                storage.catalog_version(),
                storage.get("k"),
                storage.set("k", "v", 1),
                storage.delete("k"),
            ):
                with pytest.raises(CacheUnavailableError):
                    await operation
        finally:
            await redis.aclose()

    asyncio.run(scenario())


@pytest.mark.skipif(not DATABASE_URL, reason="TEST_DATABASE_URL not set")
def test_product_snapshots_read_price_stock_and_status_from_postgres() -> None:
    schema_url = DATABASE_URL + "?options=-csearch_path%3Dm03_test"

    async def scenario() -> dict[str, ProductSnapshot]:
        async with await psycopg.AsyncConnection.connect(DATABASE_URL, autocommit=True) as conn:
            await conn.execute("DROP SCHEMA IF EXISTS m03_test CASCADE")
            await conn.execute("CREATE SCHEMA m03_test")
            await conn.execute(
                "CREATE TABLE m03_test.products (sku VARCHAR(64) PRIMARY KEY, "
                "price NUMERIC(10, 2), stock_quantity INTEGER, is_active BOOLEAN)"
            )
            await conn.execute(
                "INSERT INTO m03_test.products VALUES ('AF-550-220V', 629.90, 8, TRUE), "
                "('KIT-SIL-01', 79.90, 0, FALSE)"
            )
        return await PostgresProductSnapshots(schema_url).current(
            ["AF-550-220V", "KIT-SIL-01", "AUSENTE"]
        )

    assert asyncio.run(scenario()) == {
        "AF-550-220V": ProductSnapshot(Decimal("629.90"), 8, True),
        "KIT-SIL-01": ProductSnapshot(Decimal("79.90"), 0, False),
    }


@pytest.mark.skipif(not DATABASE_URL, reason="TEST_DATABASE_URL not set")
def test_product_snapshots_map_database_errors_to_cache_unavailable() -> None:
    broken = PostgresProductSnapshots(DATABASE_URL + "?options=-csearch_path%3Dschema_ausente")
    with pytest.raises(CacheUnavailableError):
        asyncio.run(broken.current(["AF-550-220V"]))
