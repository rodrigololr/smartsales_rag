"""M02 HTTP integration, using two Gateway lifespans and isolated real stores."""

import asyncio
import json
import os
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor

import httpx
import pytest
from app.clients.backend import BackendClient
from app.config import Settings
from app.main import create_app
from fastapi.testclient import TestClient
from psycopg import AsyncConnection
from redis.asyncio import Redis
from test_chat_routes import END, TOKEN, FakeBackend, FakeStream, ask, new_session, sse_events

DATABASE_URL = os.getenv("TEST_DATABASE_URL", "")
REDIS_URL = os.getenv("TEST_REDIS_URL", "")
requires_stores = pytest.mark.skipif(
    not DATABASE_URL or not REDIS_URL, reason="TEST_DATABASE_URL and TEST_REDIS_URL required"
)


@pytest.fixture(autouse=True)
def clear_semantic_cache() -> None:
    if not REDIS_URL:
        return

    async def flush() -> None:
        async with Redis.from_url(REDIS_URL, decode_responses=True) as redis:
            stale = [key async for key in redis.scan_iter("cache:sem:*")]
            stale.extend([key async for key in redis.scan_iter("ratelimit:ip:*")])
            if stale:
                await redis.delete(*stale)

    asyncio.run(flush())


def settings(**overrides: object) -> Settings:
    return Settings.model_validate(
        {
            "database_url": DATABASE_URL,
            "redis_url": REDIS_URL,
            "backend_internal_url": "http://127.0.0.1:9",
            **overrides,
        }
    )


async def redis_delete(*keys: str) -> None:
    async with Redis.from_url(REDIS_URL, decode_responses=True) as redis:
        await redis.delete(*keys)


async def expire_payload(session: str) -> None:
    async with await AsyncConnection.connect(DATABASE_URL) as connection:
        await connection.execute(
            "UPDATE chat_turn_requests SET expires_at=NOW()-INTERVAL '1 second' "
            "WHERE session_id=%s",
            (session,),
        )


@requires_stores
def test_http_restore_and_replay_survive_lost_redis_and_a_new_gateway() -> None:
    backend = FakeBackend([TOKEN, END])
    request_id = str(uuid.uuid4())
    with TestClient(create_app(settings(), backend)) as first:
        session = new_session(first)
        original = sse_events(ask(first, session, request_id).text)
    asyncio.run(
        redis_delete(*(f"session:{session}:{suffix}" for suffix in ("state", "history", "lock")))
    )
    with TestClient(create_app(settings(), backend)) as second:
        restored = second.post("/api/v1/sessions", json={"session_id": session})
        assert restored.status_code == 200 and len(restored.json()["history"]) == 2
        replay = sse_events(ask(second, session, request_id).text)
        assert replay[0][1]["message_id"] == original[0][1]["message_id"]
        assert len(backend.calls) == 1
        asyncio.run(expire_payload(session))
        expired = ask(second, session, request_id)
        assert expired.status_code == 410 and expired.json()["error"]["code"] == "TURN_EXPIRED"
        second.delete(f"/api/v1/sessions/{session}")


class DelayedBackend(FakeBackend):
    def __init__(self, delay: float) -> None:
        super().__init__([TOKEN, END])
        self.delay = delay
        self.started = threading.Event()
        self.closed = threading.Event()

    def open_stream(self, sku, question, history, **kwargs):
        self.calls.append((sku, question, history))
        owner = self

        class Delayed(FakeStream):
            first = True

            async def __anext__(self):
                if self.first:
                    self.first = False
                    owner.started.set()
                    await asyncio.sleep(owner.delay)
                return await super().__anext__()

            async def aclose(self):
                owner.closed.set()
                await super().aclose()

        return Delayed(self.events)


@requires_stores
def test_long_response_renews_lock_and_persists_before_done() -> None:
    backend = DelayedBackend(1.5)
    config = settings(session_lock_ttl_seconds=1, session_heartbeat_seconds=0.1)
    with (
        TestClient(create_app(config, backend)) as first,
        TestClient(create_app(config, backend)) as second,
    ):
        session = new_session(first)
        rid = str(uuid.uuid4())
        with ThreadPoolExecutor() as executor:
            pending = executor.submit(ask, first, session, rid)
            assert backend.started.wait(2)
            time.sleep(1.1)  # past the original lease; heartbeat must still exclude another worker
            busy = ask(second, session, str(uuid.uuid4()))
            assert busy.status_code == 409 and busy.json()["error"]["code"] == "TURN_IN_PROGRESS"
            frames = sse_events(pending.result(timeout=3).text)
        assert frames[-1][1]["finish_reason"] == "stop"
        assert backend.closed.is_set() and len(backend.calls) == 1
        restored = second.post("/api/v1/sessions", json={"session_id": session}).json()
        assert len(restored["history"]) == 2
        assert restored["history"][1]["id"] == frames[0][1]["message_id"]
        second.delete(f"/api/v1/sessions/{session}")


@requires_stores
@pytest.mark.parametrize("delete_session", [False, True])
def test_lost_lease_interrupts_waiting_provider_without_publishing_its_tokens(
    delete_session: bool,
) -> None:
    backend = DelayedBackend(10)
    config = settings(session_lock_ttl_seconds=1, session_heartbeat_seconds=0.1)
    with (
        TestClient(create_app(config, backend)) as first,
        TestClient(create_app(config, backend)) as second,
    ):
        session = new_session(first)
        rid = str(uuid.uuid4())
        with ThreadPoolExecutor() as executor:
            pending = executor.submit(ask, first, session, rid)
            assert backend.started.wait(2)
            if delete_session:
                assert second.delete(f"/api/v1/sessions/{session}").status_code == 204
            else:
                asyncio.run(redis_delete(f"session:{session}:lock"))
            frames = sse_events(pending.result(timeout=3).text)
        assert frames[-1][1]["finish_reason"] == "error"
        assert not any(event == "token" for event, _ in frames)
        assert backend.closed.is_set()
        if delete_session:
            assert ask(second, session, rid).status_code == 404
        else:
            replay = sse_events(ask(second, session, rid).text)
            assert replay[-1][1]["finish_reason"] == "error" and len(backend.calls) == 1
            second.delete(f"/api/v1/sessions/{session}")


@requires_stores
def test_terminal_transport_failure_is_replayed_without_new_generation() -> None:
    backend = DelayedBackend(0)
    backend.events = [TOKEN]  # invalid EOF after content
    with TestClient(create_app(settings(), backend)) as gateway:
        session = new_session(gateway)
        rid = str(uuid.uuid4())
        first = sse_events(ask(gateway, session, rid).text)
        retry = sse_events(ask(gateway, session, rid).text)
        assert first[-1][1]["finish_reason"] == retry[-1][1]["finish_reason"] == "error"
        assert not any(event == "token" for event, _ in retry)
        assert first[0][1]["message_id"] == retry[0][1]["message_id"]
        assert len(backend.calls) == 1
        assert (
            gateway.post("/api/v1/sessions", json={"session_id": session}).json()["history"] == []
        )
        gateway.delete(f"/api/v1/sessions/{session}")


class SilentBody(httpx.AsyncByteStream):
    async def __aiter__(self):
        await asyncio.sleep(60)
        yield b""


def test_first_event_timeout_uses_one_retry_and_sse_contingency() -> None:
    attempts = []

    def handler(request):
        attempts.append(request)
        return httpx.Response(200, stream=SilentBody())

    http = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    backend = BackendClient(http, "http://worker", first_event_timeout_seconds=0.04)
    started = time.monotonic()
    with TestClient(create_app(Settings(), backend)) as gateway:
        session = new_session(gateway)
        frames = sse_events(ask(gateway, session, str(uuid.uuid4())).text)
    assert [event for event, _ in frames] == ["metadata", "error", "recommendations", "done"]
    assert frames[1][1]["code"] == "LLM_UNAVAILABLE"
    assert frames[-1][1]["finish_reason"] == "error"
    assert len(attempts) == 2 and time.monotonic() - started < 2


def test_transport_is_never_retried_after_a_published_token() -> None:
    attempts = []

    class BrokenBody(httpx.AsyncByteStream):
        async def __aiter__(self):
            yield (json.dumps(TOKEN) + "\n").encode()
            raise httpx.ReadTimeout("disconnected")

    def handler(request):
        attempts.append(request)
        return httpx.Response(200, stream=BrokenBody())

    http = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    with TestClient(create_app(Settings(), BackendClient(http, "http://worker"))) as gateway:
        session = new_session(gateway)
        frames = sse_events(ask(gateway, session, str(uuid.uuid4())).text)
    assert [event for event, _ in frames] == [
        "metadata",
        "token",
        "error",
        "recommendations",
        "done",
    ]
    assert frames[-1][1]["finish_reason"] == "error" and len(attempts) == 1


def test_backend_adapter_construction_failure_releases_the_reservation() -> None:
    class Unavailable(FakeBackend):
        def open_stream(self, *args, **kwargs):
            raise ConnectionError("Cannot construct transport")

    with TestClient(create_app(Settings(), Unavailable([]))) as gateway:
        session = new_session(gateway)
        rid = str(uuid.uuid4())
        response = ask(gateway, session, rid)
        assert response.status_code == 503
        replay = sse_events(ask(gateway, session, rid).text)
        assert replay[-1][1]["finish_reason"] == "error"
        # No turn lock is leaked by the exception before constructing StreamingResponse.
        assert ask(gateway, session, str(uuid.uuid4())).status_code == 503


@pytest.mark.parametrize("fail_headers", [True, False])
def test_asgi_send_failure_closes_even_an_unread_stream_and_settles_the_request(
    fail_headers: bool,
) -> None:
    from app.sessions.response import SessionStreamingResponse
    from app.sessions.store import InMemorySessionStore, TurnDecision
    from app.sse.stream import sse_chat_generator
    from starlette.requests import ClientDisconnect

    class Request:
        async def is_disconnected(self):
            return False

    async def scenario():
        store = InMemorySessionStore(ttl_seconds=1800, history_max_messages=10)
        session = (await store.create(None)).session_id
        owner = await store.begin_turn(session, "request", "hash")
        backend = FakeStream([TOKEN, END])

        async def release():
            await store.release(session, "request", owner.lock_token)

        async def complete(turn):
            await store.complete(session, "request", owner.lock_token, "Question", turn)

        frames = sse_chat_generator(
            Request(),
            session,
            owner.message_id,
            backend,
            False,
            release,
            lambda: asyncio.sleep(0, result=[]),
            complete,
        )
        response = SessionStreamingResponse(frames, headers={})

        async def receive():
            await asyncio.Event().wait()

        async def send(message):
            if fail_headers or message["type"] == "http.response.body":
                raise OSError("Client closed the connection")

        with pytest.raises((OSError, ClientDisconnect)):
            await response({"type": "http", "asgi": {"spec_version": "2.4"}}, receive, send)
        assert backend.closed
        retry = await store.begin_turn(session, "request", "hash")
        assert retry.kind == TurnDecision.REPLAY and retry.completed.finish_reason == "error"
        assert (await store.begin_turn(session, "new-request", "new-hash")).kind == TurnDecision.NEW

    asyncio.run(scenario())


@requires_stores
def test_database_outage_is_503_without_downgrading_session_storage() -> None:
    backend = FakeBackend([TOKEN, END])
    with TestClient(create_app(settings(), backend)) as gateway:
        from app.sessions.postgres_store import PostgresSessionStore

        store = gateway.app.state.store
        assert isinstance(store, PostgresSessionStore)
        store._url = "postgresql://smartsales:smartsales@127.0.0.1:1/smartsales"
        response = gateway.post("/api/v1/sessions", json={})
        assert response.status_code == 503
        assert response.json()["error"]["code"] == "SERVICE_UNAVAILABLE"
        assert backend.calls == []
        health = gateway.get("/api/v1/health").json()
        assert health["status"] == "degraded"
        assert health["components"]["postgres"] == "error"


def test_client_request_id_requires_uuid4() -> None:
    with TestClient(create_app(Settings(), FakeBackend([TOKEN, END]))) as gateway:
        session = new_session(gateway)
        assert ask(gateway, session, str(uuid.uuid1())).status_code == 422
