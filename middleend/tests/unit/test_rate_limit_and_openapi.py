"""UT-M01-01 and CT-M01-01: Gateway rate limiting (30 req/min per IP) and OpenAPI 3.1 contract."""

import asyncio
import json
import os
import uuid
from pathlib import Path

import pytest
from app.config import Settings
from app.main import create_app
from app.ratelimit import (
    CHAT_SESSIONS_PER_IP,
    InMemoryRateLimiter,
    RedisRateLimiter,
    client_ip_from_request,
)
from fastapi.testclient import TestClient
from jsonschema import Draft202012Validator
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

    normative_stream_req = normative["components"]["schemas"]["ChatStreamRequest"]
    runtime_stream_req = runtime["components"]["schemas"]["ChatStreamRequest"]
    assert set(normative_stream_req["required"]) == set(runtime_stream_req["required"])
    assert set(normative_stream_req["properties"]) == set(runtime_stream_req["properties"])


def _resolved_schema(document: dict, schema: object) -> object:
    """Compare schema meaning, independently of component names and annotations."""
    if isinstance(schema, list):
        return [_resolved_schema(document, item) for item in schema]
    if not isinstance(schema, dict):
        return schema
    if "$ref" in schema:
        target = document
        for part in schema["$ref"].removeprefix("#/").split("/"):
            target = target[part]
        return _resolved_schema(document, target)
    return {
        key: _resolved_schema(document, value)
        for key, value in schema.items()
        if key not in {"title", "description"}
    }


@pytest.mark.parametrize(
    ("method", "path", "request_path", "payload"),
    [
        ("post", "/api/v1/sessions", "/api/v1/sessions", {"session_id": "invalid"}),
        ("delete", "/api/v1/sessions/{session_id}", "/api/v1/sessions/invalid", None),
        ("post", "/api/v1/chat/stream", "/api/v1/chat/stream", {}),
    ],
)
def test_ct_m01_01_error_responses_match_normative_contract_and_actual_payloads(
    method: str, path: str, request_path: str, payload: dict | None
) -> None:
    normative = json.loads((ROOT / "openapi.yaml").read_text(encoding="utf-8"))
    settings = Settings(backend_internal_url="http://127.0.0.1:9", rate_limit_per_minute=1)
    with TestClient(create_app(settings, FakeBackend([TOKEN, END]))) as client:
        runtime = client.get("/openapi.json").json()
        responses = runtime["paths"][path][method]["responses"]
        expected = normative["paths"][path][method]["responses"]
        for status in ("422", "429"):
            schema = responses[status]["content"]["application/json"]["schema"]
            normative_schema = expected[status]["content"]["application/json"]["schema"]
            assert _resolved_schema(runtime, schema) == _resolved_schema(normative, normative_schema)
        retry_header = responses["429"]["headers"]["Retry-After"]
        assert retry_header == expected["429"]["headers"]["Retry-After"]
        assert retry_header["schema"] == {"type": "integer", "minimum": 1}
        assert "429" not in runtime["paths"]["/api/v1/health"]["get"]["responses"]

        invalid = client.request(method, request_path, json=payload)
        assert invalid.status_code == 422
        # Invalid chat bodies consume the coarse IP bucket before session validation.
        attempts = CHAT_SESSIONS_PER_IP if path.endswith("/chat/stream") else 1
        for _ in range(attempts - 1):
            assert client.request(method, request_path, json=payload).status_code == 422
        blocked = client.request(method, request_path, json=payload)
        assert blocked.status_code == 429
        assert blocked.json()["error"]["code"] == "RATE_LIMITED"
        assert int(blocked.headers["retry-after"]) >= 1
        for response in (invalid, blocked):
            for document in (runtime, normative):
                operation = document["paths"][path][method]
                schema = operation["responses"][str(response.status_code)]["content"][
                    "application/json"
                ]["schema"]
                resolved = _resolved_schema(document, schema)
                Draft202012Validator(resolved).validate(response.json())


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
