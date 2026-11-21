"""Request-id correlation (trace_id) and the REST error envelope for every failure path."""

import json
import logging
import uuid

import httpx
import pytest
from app.clients.backend import BackendClient
from app.config import Settings
from app.main import create_app
from app.ratelimit import InMemoryRateLimiter
from app.sessions.store import InMemorySessionStore, SessionSnapshot
from app.telemetry.tracing import build_log_handler, trace_id_var
from fastapi.testclient import TestClient
from test_chat_routes import END, TOKEN, FakeBackend, ask, new_session

SETTINGS = Settings(backend_internal_url="http://127.0.0.1:9")


def _client(**kwargs: object) -> TestClient:
    return TestClient(create_app(SETTINGS, FakeBackend([TOKEN, END]), **kwargs))  # type: ignore[arg-type]


def _envelope(response: httpx.Response) -> dict[str, object]:
    error = response.json()["error"]
    assert set(error) == {"code", "message", "trace_id", "details"}
    assert error["trace_id"] == response.headers["x-request-id"]
    return dict(error)


def test_incoming_uuid_request_id_is_echoed_and_used_as_trace_id() -> None:
    request_id = str(uuid.uuid4())
    with _client() as client:
        response = client.delete(
            f"/api/v1/sessions/{uuid.uuid4()}", headers={"X-Request-ID": request_id}
        )
    assert response.status_code == 404
    assert response.headers["x-request-id"] == request_id
    assert _envelope(response)["code"] == "SESSION_NOT_FOUND"


@pytest.mark.parametrize("incoming", [None, "not-a-uuid", "x" * 500])
def test_missing_or_invalid_request_id_is_replaced_by_a_generated_uuid(
    incoming: str | None,
) -> None:
    headers = {} if incoming is None else {"X-Request-ID": incoming}
    with _client() as client:
        response = client.post("/api/v1/sessions", json={"session_id": "bad"}, headers=headers)
    assert response.status_code == 422
    generated = response.headers["x-request-id"]
    assert generated != incoming and uuid.UUID(generated)
    assert _envelope(response)["code"] == "VALIDATION_ERROR"


def test_success_responses_also_carry_the_request_id() -> None:
    with _client() as client:
        response = client.post("/api/v1/sessions", json={"current_product_sku": "AF-400-220V"})
    assert response.status_code == 201 and uuid.UUID(response.headers["x-request-id"])


def test_rate_limited_and_commerce_errors_share_the_request_trace_id() -> None:
    with _client(rate_limiter=InMemoryRateLimiter(limit=1, window_seconds=60)) as client:
        client.post("/api/v1/feedback", json={})
        assert _envelope(client.post("/api/v1/feedback", json={}))["code"] == "RATE_LIMITED"
        assert _envelope(client.get("/api/v1/products"))["code"] == "DATABASE_UNAVAILABLE"


def test_cors_lets_the_browser_send_and_read_the_request_id() -> None:
    with _client() as client:
        preflight = client.options(
            "/api/v1/chat/stream",
            headers={
                "Origin": "http://localhost:3000",
                "Access-Control-Request-Method": "POST",
                "Access-Control-Request-Headers": "X-Request-ID",
            },
        )
        actual = client.post(
            "/api/v1/sessions",
            json={"current_product_sku": "AF-400-220V"},
            headers={"Origin": "http://localhost:3000"},
        )
    assert preflight.status_code == 200
    assert "x-request-id" in preflight.headers["access-control-allow-headers"].lower()
    assert "x-request-id" in actual.headers["access-control-expose-headers"].lower()


def test_request_id_is_forwarded_to_the_backend() -> None:
    forwarded: list[str | None] = []

    def handler(request: httpx.Request) -> httpx.Response:
        forwarded.append(request.headers.get("x-request-id"))
        return httpx.Response(200, text="\n".join(json.dumps(event) for event in (TOKEN, END)))

    http = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    request_id = str(uuid.uuid4())
    with TestClient(create_app(SETTINGS, BackendClient(http, "http://worker"))) as client:
        session = new_session(client)
        client.headers["X-Request-ID"] = request_id
        response = ask(client, session, str(uuid.uuid4()))
    assert response.status_code == 200 and response.headers["x-request-id"] == request_id
    assert forwarded == [request_id]


def test_log_lines_carry_trace_id_and_session_id_as_key_values() -> None:
    handler = build_log_handler()
    token = trace_id_var.set("trace-123")
    try:
        record = logging.makeLogRecord(
            {"msg": "stream_failed", "levelname": "ERROR", "session_id": "session-9"}
        )
        assert handler.filter(record)
        line = handler.format(record)
    finally:
        trace_id_var.reset(token)
    assert "event=stream_failed" in line
    assert "trace_id=trace-123" in line and "session_id=session-9" in line

    bare = logging.makeLogRecord({"msg": "startup"})
    assert handler.filter(bare)
    assert "trace_id=- session_id=-" in handler.format(bare)


def test_unknown_route_returns_not_found_envelope() -> None:
    with _client() as client:
        response = client.get("/api/v1/nope")
    assert response.status_code == 404
    assert _envelope(response)["code"] == "NOT_FOUND"


def test_wrong_method_returns_method_not_allowed_envelope_with_allow_header() -> None:
    with _client() as client:
        response = client.put("/api/v1/sessions", json={})
    assert response.status_code == 405
    assert "POST" in response.headers["allow"]
    assert _envelope(response)["code"] == "METHOD_NOT_ALLOWED"


class _BrokenStore(InMemorySessionStore):
    async def create(self, current_product_sku: str | None) -> SessionSnapshot:
        raise RuntimeError("secret internal detail")


def test_unhandled_exception_returns_internal_error_without_leaking_details(
    caplog: pytest.LogCaptureFixture,
) -> None:
    app = create_app(SETTINGS, FakeBackend([TOKEN, END]), store=_BrokenStore(ttl_seconds=60, history_max_messages=10))
    with caplog.at_level(logging.ERROR), TestClient(app, raise_server_exceptions=False) as client:
        response = client.post("/api/v1/sessions", json={"current_product_sku": "AF-400-220V"})
    assert response.status_code == 500
    error = _envelope(response)
    assert error["code"] == "INTERNAL_ERROR"
    assert "secret internal detail" not in response.text and "Traceback" not in response.text
    logged = [record for record in caplog.records if record.getMessage() == "unhandled_error"]
    assert logged and logged[0].exc_info is not None
    assert getattr(logged[0], "trace_id", None) == error["trace_id"]


def test_unhandled_error_is_readable_by_the_browser() -> None:
    # The trace id exists for exactly these failures: CORS must not hide the envelope.
    app = create_app(SETTINGS, FakeBackend([TOKEN, END]), store=_BrokenStore(ttl_seconds=60, history_max_messages=10))
    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.post(
            "/api/v1/sessions",
            json={"current_product_sku": "AF-400-220V"},
            headers={"Origin": "http://localhost:3000"},
        )
    assert response.status_code == 500
    assert response.headers["access-control-allow-origin"] == "http://localhost:3000"
    assert response.headers["x-request-id"] == _envelope(response)["trace_id"]
