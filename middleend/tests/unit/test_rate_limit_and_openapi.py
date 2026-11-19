"""UT-M01-01 and CT-M01-01: Gateway rate limiting (30 req/min per IP) and OpenAPI 3.1 contract."""

import asyncio
import json
import os
import uuid
from pathlib import Path

import pytest
from app.config import Settings
from app.main import create_app
from app.ratelimit import InMemoryRateLimiter, RedisRateLimiter
from fastapi.testclient import TestClient
from redis.asyncio import Redis
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
        other_ip = client.post(
            "/api/v1/sessions",
            json={"current_product_sku": "AF-400-220V"},
            headers={"X-Forwarded-For": "203.0.113.9"},
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
        rate_limit_requests_per_minute=2,
        rate_limit_window_seconds=45,
    )
    with TestClient(create_app(settings, FakeBackend([TOKEN, END]))) as client:
        session_id = new_session(client)
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
                decision = await limiter.check(client_ip)
                assert decision.allowed is True
            blocked = await limiter.check(client_ip)
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

    normative_stream_req = normative["components"]["schemas"]["ChatStreamRequest"]
    runtime_stream_req = runtime["components"]["schemas"]["ChatStreamRequest"]
    assert set(normative_stream_req["required"]) == set(runtime_stream_req["required"])
    assert set(normative_stream_req["properties"]) == set(runtime_stream_req["properties"])
