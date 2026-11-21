"""UT-M01-01 and CT-M01-01: Gateway rate limiting (30 req/min per IP) and OpenAPI 3.1 contract."""

import asyncio
import json
import os
import uuid
from pathlib import Path

import httpx
import pytest
from app.commerce import CatalogQuery, CheckoutCreate
from app.config import Settings
from app.main import build_redis, create_app
from app.ratelimit import (
    CHAT_SESSIONS_PER_IP,
    InMemoryRateLimiter,
    RedisRateLimiter,
    client_ip_from_request,
)
from fastapi.testclient import TestClient
from pydantic import BaseModel, ValidationError
from redis.asyncio import Redis
from redis.exceptions import ConnectionError as RedisConnectionError
from starlette.requests import Request
from test_chat_routes import END, TOKEN, FakeBackend, ask, new_session

REDIS_URL = os.environ.get("TEST_REDIS_URL", "")
ROOT = Path(__file__).resolve().parents[3]


def test_ut_m01_01_thirty_first_request_within_one_minute_returns_429_with_retry_after() -> None:
    clock = [100.0]
    limiter = InMemoryRateLimiter(limit=30, window_seconds=60, clock=lambda: clock[0])
    settings = Settings(backend_internal_url="http://127.0.0.1:9")
    app = create_app(settings, FakeBackend([TOKEN, END]), rate_limiter=limiter)

    with TestClient(app) as client:
        for _ in range(30):
            response = client.post("/api/v1/sessions", json={"current_product_sku": "AF-400-220V"})
            assert response.status_code == 201

        blocked = client.post("/api/v1/sessions", json={"current_product_sku": "AF-400-220V"})
        assert blocked.status_code == 429
        assert blocked.headers["retry-after"] == "60"
        error = blocked.json()["error"]
        assert error["code"] == "RATE_LIMITED"
        assert uuid.UUID(error["trace_id"])

        # Another IP has its own bucket; health probe is exempt from rate limiting.
        assert client.get("/api/v1/health").status_code == 200
        with TestClient(app, client=("203.0.113.9", 50000)) as other_client:
            other_ip = other_client.post(
                "/api/v1/sessions", json={"current_product_sku": "AF-400-220V"}
            )
        assert other_ip.status_code == 201

        # After the 60s window expires, the original IP is allowed again.
        clock[0] += 60.1
        allowed_again = client.post(
            "/api/v1/sessions", json={"current_product_sku": "AF-400-220V"}
        )
        assert allowed_again.status_code == 201


def test_rate_limit_applies_to_chat_stream_and_uses_configured_threshold() -> None:
    settings = Settings(
        backend_internal_url="http://127.0.0.1:9",
        rate_limit_per_minute=2,
    )
    with TestClient(create_app(settings, FakeBackend([TOKEN, END]))) as client:
        session_id = new_session(client)
        assert ask(client, session_id, str(uuid.uuid4())).status_code == 200
        assert ask(client, session_id, str(uuid.uuid4())).status_code == 200
        third = ask(client, session_id, str(uuid.uuid4()))
        assert third.status_code == 429
        assert int(third.headers["retry-after"]) >= 1
        assert third.json()["error"]["code"] == "RATE_LIMITED"


@pytest.mark.skipif(not REDIS_URL, reason="TEST_REDIS_URL not set")
def test_redis_rate_limiter_uses_ratelimit_ip_key_with_ttl_and_blocks_31st_request() -> None:
    client_ip = f"198.51.100.{uuid.uuid4().int % 250}"
    key = f"ratelimit:ip:{client_ip}"

    async def scenario() -> None:
        redis = Redis.from_url(REDIS_URL, decode_responses=True)
        try:
            await redis.delete(key)
            limiter = RedisRateLimiter(redis, limit=30, window_seconds=60)
            for _ in range(30):
                decision = await limiter.check(f"ip:{client_ip}")
                assert decision.allowed is True
            blocked = await limiter.check(f"ip:{client_ip}")
            assert blocked.allowed is False
            assert 1 <= blocked.retry_after_seconds <= 60
            assert await redis.get(key) == "31"
            assert 1 <= await redis.ttl(key) <= 60
        finally:
            await redis.delete(key)
            await redis.aclose()

    asyncio.run(scenario())


def test_validation_errors_follow_the_standard_rest_error_envelope() -> None:
    settings = Settings(backend_internal_url="http://127.0.0.1:9")
    with TestClient(create_app(settings, FakeBackend([TOKEN, END]))) as client:
        invalid_uuid = client.delete("/api/v1/sessions/not-a-uuid")
        assert invalid_uuid.status_code == 422
        error = invalid_uuid.json()["error"]
        assert set(error) == {"code", "message", "trace_id", "details"}
        assert error["code"] == "VALIDATION_ERROR"
        assert uuid.UUID(error["trace_id"])
        assert isinstance(error["details"]["errors"], list)


def test_ct_m01_01_runtime_openapi_matches_normative_session_and_chat_contracts() -> None:
    normative = json.loads((ROOT / "openapi.yaml").read_text(encoding="utf-8"))
    settings = Settings(backend_internal_url="http://127.0.0.1:9")
    with TestClient(create_app(settings, FakeBackend([TOKEN, END]))) as client:
        runtime = client.get("/openapi.json").json()

    assert runtime["openapi"].startswith("3.1.")
    for path, methods in {
        "/api/v1/sessions": ("post",),
        "/api/v1/sessions/{session_id}": ("delete",),
        "/api/v1/chat/stream": ("post",),
        "/api/v1/health": ("get",),
    }.items():
        assert path in runtime["paths"]
        for method in methods:
            assert method in runtime["paths"][path]
            if path in normative["paths"]:
                assert method in normative["paths"][path]

    shared = set(runtime["paths"]) & set(normative["paths"])
    assert {"/api/v1/sessions", "/api/v1/chat/stream", "/api/v1/health"} <= shared
    for path in shared:
        for method, operation in normative["paths"][path].items():
            if method == "parameters":  # path-level, not an operation
                continue
            served = runtime["paths"][path][method]
            assert served["operationId"] == operation["operationId"], (path, method)
            assert set(served["responses"]) == set(operation["responses"]), (path, method)
            if "422" in served["responses"]:
                schema = served["responses"]["422"]["content"]["application/json"]["schema"]
                assert schema["$ref"].endswith("/ErrorEnvelope"), (path, method)

    stream_ok = runtime["paths"]["/api/v1/chat/stream"]["post"]["responses"]["200"]
    assert list(stream_ok["content"]) == ["text/event-stream"]

    normative_stream_req = normative["components"]["schemas"]["ChatStreamRequest"]
    runtime_stream_req = runtime["components"]["schemas"]["ChatStreamRequest"]
    assert set(normative_stream_req["required"]) == set(runtime_stream_req["required"])
    assert set(normative_stream_req["properties"]) == set(runtime_stream_req["properties"])


def _limited_app(limit: int) -> TestClient:
    limiter = InMemoryRateLimiter(limit=limit, window_seconds=60)
    settings = Settings(backend_internal_url="http://127.0.0.1:9")
    return TestClient(create_app(settings, FakeBackend([TOKEN, END]), rate_limiter=limiter))


def test_forged_x_forwarded_for_cannot_bypass_the_limit() -> None:
    with _limited_app(limit=3) as client:
        statuses = [
            client.get("/api/v1/sessions/unknown", headers={"X-Forwarded-For": f"10.0.0.{i}"})
            .status_code
            for i in range(5)
        ]
    assert statuses[3:] == [429, 429]


def test_forged_x_forwarded_for_cannot_lock_out_another_client() -> None:
    victim = "203.0.113.7"
    limiter = InMemoryRateLimiter(limit=3, window_seconds=60)
    app = create_app(
        Settings(backend_internal_url="http://127.0.0.1:9"),
        FakeBackend([TOKEN, END]),
        rate_limiter=limiter,
    )
    with TestClient(app) as attacker:
        for _ in range(5):
            attacker.get("/api/v1/health/x", headers={"X-Forwarded-For": victim})
    with TestClient(app, client=(victim, 50000)) as real_victim:
        response = real_victim.post("/api/v1/sessions", json={"current_product_sku": "AF-400-220V"})
    assert response.status_code == 201


def _request(client_host: str, forwarded_for: str | None) -> Request:
    headers = [] if forwarded_for is None else [(b"x-forwarded-for", forwarded_for.encode())]
    return Request({"type": "http", "headers": headers, "client": (client_host, 1234)})


@pytest.mark.parametrize(
    ("hops", "forwarded_for", "expected"),
    [
        (0, "198.51.100.1", "10.0.0.2"),  # no trusted proxy: the header is ignored
        (1, "198.51.100.1", "198.51.100.1"),  # one proxy appended the real client
        (1, "6.6.6.6, 198.51.100.1", "198.51.100.1"),  # client-forged prefix is skipped
        (2, "6.6.6.6, 198.51.100.1, 10.0.0.9", "198.51.100.1"),
        (2, "198.51.100.1", "10.0.0.2"),  # shorter chain than configured: client wrote it
        (1, None, "10.0.0.2"),
    ],
)
def test_client_ip_only_trusts_hops_appended_by_configured_proxies(
    hops: int, forwarded_for: str | None, expected: str
) -> None:
    request = _request("10.0.0.2", forwarded_for)
    assert client_ip_from_request(request, trusted_proxy_hops=hops) == expected


def test_trusted_proxy_hops_setting_is_used_by_the_middleware() -> None:
    limiter = InMemoryRateLimiter(limit=1, window_seconds=60)
    settings = Settings(backend_internal_url="http://127.0.0.1:9", rate_limit_trusted_proxy_hops=1)
    app = create_app(settings, FakeBackend([TOKEN, END]), rate_limiter=limiter)
    with TestClient(app) as proxy:
        first = proxy.get("/api/v1/sessions/x", headers={"X-Forwarded-For": "198.51.100.1"})
        second = proxy.get("/api/v1/sessions/x", headers={"X-Forwarded-For": "198.51.100.2"})
    assert first.status_code != 429 and second.status_code != 429


def test_validation_error_with_decimal_constraint_stays_422_without_echoing_input() -> None:
    settings = Settings(backend_internal_url="http://127.0.0.1:9")
    with TestClient(create_app(settings, FakeBackend([TOKEN, END]))) as client:
        response = client.post(
            "/api/v1/chat/stream",
            json={
                "session_id": str(uuid.uuid4()),
                "client_request_id": str(uuid.uuid4()),
                "message": "pergunta-secreta-do-cliente",
                "context_filters": {"current_product_sku": "AF-400-220V", "budget_max": -5},
            },
        )
    assert response.status_code == 422
    error = response.json()["error"]
    assert error["code"] == "VALIDATION_ERROR"
    assert error["details"]["errors"][0]["loc"][-1] == "budget_max"
    assert "pergunta-secreta-do-cliente" not in response.text
    assert all("input" not in item for item in error["details"]["errors"])


def test_in_memory_limiter_forgets_expired_windows() -> None:
    clock = [0.0]
    limiter = InMemoryRateLimiter(limit=30, window_seconds=60, clock=lambda: clock[0])
    for index in range(100):
        asyncio.run(limiter.check(f"198.51.100.{index}"))
    clock[0] += 61
    asyncio.run(limiter.check("203.0.113.1"))
    assert limiter.tracked_clients == 1


def test_rate_limit_per_minute_env_var_from_spec_sets_the_limit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("RATE_LIMIT_PER_MINUTE", "60")
    assert Settings(backend_internal_url="http://127.0.0.1:9").rate_limit_per_minute == 60


class _UnavailableRedis:
    async def eval(self, *args: object) -> object:
        raise RedisConnectionError("redis down")


def test_redis_rate_limiter_fails_open_when_redis_is_unavailable() -> None:
    # Security decision: Redis outage must not turn every request into 429/503.
    limiter = RedisRateLimiter(_UnavailableRedis(), limit=1, window_seconds=60)  # type: ignore[arg-type]
    decision = asyncio.run(limiter.check("198.51.100.1"))
    assert decision.allowed is True


def test_chat_stream_is_limited_per_session_not_per_shared_ip() -> None:
    # Classroom demo: everyone behind one Wi-Fi IP must not share a single chat bucket.
    settings = Settings(backend_internal_url="http://127.0.0.1:9", rate_limit_per_minute=3)
    with TestClient(create_app(settings, FakeBackend([TOKEN, END]))) as client:
        first, second = new_session(client), new_session(client)
        assert [ask(client, first, str(uuid.uuid4())).status_code for _ in range(3)] == [200] * 3
        blocked = ask(client, first, str(uuid.uuid4()))
        assert blocked.status_code == 429
        assert blocked.json()["error"]["code"] == "RATE_LIMITED"
        assert ask(client, second, str(uuid.uuid4())).status_code == 200
        # Chat turns do not consume the IP bucket used by the other routes.
        assert client.post(
            "/api/v1/sessions", json={"current_product_sku": "AF-400-220V"}
        ).status_code == 201


def test_chat_stream_has_a_coarse_ip_bucket_before_the_session_lookup() -> None:
    # Unknown session ids or bad bodies must not hit the store without any limit.
    settings = Settings(backend_internal_url="http://127.0.0.1:9", rate_limit_per_minute=1)
    with TestClient(create_app(settings, FakeBackend([TOKEN, END]))) as client:
        statuses = [
            ask(client, str(uuid.uuid4()), str(uuid.uuid4())).status_code
            for _ in range(CHAT_SESSIONS_PER_IP + 1)
        ]
    assert statuses[:-1] == [404] * CHAT_SESSIONS_PER_IP
    assert statuses[-1] == 429


def test_catalog_reads_skip_the_ip_bucket_but_writes_stay_limited() -> None:
    # The Next.js server renders the storefront from a single container IP (SSR).
    with _limited_app(limit=1) as client:
        reads = [
            client.get(path).status_code
            for path in ("/api/v1/products", "/api/v1/products/AF-400-220V") * 3
        ]
        assert 429 not in reads
        writes = [client.post("/api/v1/feedback", json={}).status_code for _ in range(2)]
        assert writes[-1] == 429
        # Only the list and the single-product route are exempt, not deeper paths.
        assert client.get("/api/v1/products/AF-400-220V/extra").status_code == 429


def _stream_with_filters(client: TestClient, filters: str) -> httpx.Response:
    body = (
        f'{{"session_id": "{uuid.uuid4()}", "client_request_id": "{uuid.uuid4()}", '
        f'"message": "Qual a voltagem?", "context_filters": {filters}}}'
    )
    return client.post(
        "/api/v1/chat/stream", content=body, headers={"Content-Type": "application/json"}
    )


@pytest.mark.parametrize(
    ("filters", "field"),
    [
        ('{"capacity_min": NaN}', "capacity_min"),
        ('{"capacity_min": Infinity}', "capacity_min"),
        ('{"capacity_min": -1}', "capacity_min"),
        (json.dumps({"category": "x" * 65}), "category"),
    ],
)
def test_chat_filters_reject_non_finite_negative_or_oversized_values(
    filters: str, field: str
) -> None:
    settings = Settings(backend_internal_url="http://127.0.0.1:9")
    with TestClient(create_app(settings, FakeBackend([TOKEN, END]))) as client:
        response = _stream_with_filters(client, filters)
    assert response.status_code == 422
    assert response.json()["error"]["details"]["errors"][0]["loc"][-1] == field


@pytest.mark.parametrize(
    ("model", "payload", "field"),
    [
        (CatalogQuery, {"category": "x" * 65}, "category"),
        (
            CheckoutCreate,
            {
                "session_id": str(uuid.uuid4()),
                "message_id": str(uuid.uuid4()),
                "sku": "S" * 65,
                "recommendation_type": "PRIMARY",
                "quantity": 1,
                "displayed_price": 10.0,
            },
            "sku",
        ),
    ],
)
def test_commerce_request_strings_are_bounded(
    model: type[BaseModel], payload: dict[str, object], field: str
) -> None:
    with pytest.raises(ValidationError) as invalid:
        model.model_validate(payload)
    assert invalid.value.errors()[0]["loc"][-1] == field


def test_redis_client_pings_idle_connections_before_reuse() -> None:
    # Upstash and NAT gateways drop idle TCP connections; a stale one would fail a request.
    settings = Settings(redis_url="redis://127.0.0.1:9/0")
    assert settings.redis_health_check_interval_seconds == 30
    redis = build_redis(settings, "redis://127.0.0.1:9/0")
    try:
        assert redis.connection_pool.connection_kwargs["health_check_interval"] == 30
    finally:
        asyncio.run(redis.aclose())
