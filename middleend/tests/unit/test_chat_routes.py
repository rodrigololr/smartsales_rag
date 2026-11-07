"""Gateway MVP: sessions, SSE chat stream, idempotency and the backend NDJSON adapter."""

import asyncio
import json
import uuid
from collections.abc import AsyncIterator, Iterator, Mapping

import httpx
import pytest
from app.clients.backend import BackendClient
from app.config import Settings
from app.main import create_app
from app.sessions.store import HistoryItem
from fastapi.testclient import TestClient

TOKEN = {"event": "token", "data": {"delta": "Opera em 220V. "}}
CITATIONS = {
    "event": "citations",
    "data": {
        "citations": [
            {
                "chunk_id": str(uuid.uuid4()),
                "sku": "AF-400-220V",
                "manual_title": "Manual Airfryer SmartChef 4L",
                "page_number": 6,
                "section_title": None,
                "similarity_score": 0.91,
                "excerpt": "Este modelo opera exclusivamente em 220V / 60 Hz.",
            }
        ]
    },
}
END = {"event": "end", "data": {"tokens_used": 12, "intent": "TECHNICAL_QA"}}
FALLBACK = {
    "event": "error",
    "data": {
        "code": "LOW_SIMILARITY_FALLBACK",
        "recoverable": True,
        "fallback_message": "Não consta no manual.",
    },
}


class FakeStream:
    def __init__(self, events: list[Mapping[str, object]]) -> None:
        self._events = iter(events)
        self.closed = False

    def __aiter__(self) -> AsyncIterator[Mapping[str, object]]:
        return self

    async def __anext__(self) -> Mapping[str, object]:
        try:
            return next(self._events)
        except StopIteration:
            raise StopAsyncIteration from None

    async def aclose(self) -> None:
        self.closed = True


class FakeBackend:
    def __init__(self, events: list[Mapping[str, object]]) -> None:
        self.events = events
        self.calls: list[tuple[str, str, list[HistoryItem]]] = []

    def open_stream(self, sku: str, question: str, history: list[HistoryItem]) -> FakeStream:
        self.calls.append((sku, question, history))
        return FakeStream(self.events)


def sse_events(text: str) -> list[tuple[str, dict[str, object]]]:
    frames = []
    for block in text.strip().split("\n\n"):
        event, data = block.split("\n", 1)
        frames.append((event.removeprefix("event: "), json.loads(data.removeprefix("data: "))))
    return frames


@pytest.fixture
def backend() -> FakeBackend:
    return FakeBackend([TOKEN, CITATIONS, END])


@pytest.fixture
def client(backend: FakeBackend) -> Iterator[TestClient]:
    settings = Settings(backend_internal_url="http://127.0.0.1:9", cors_allowed_origins=["http://localhost:3000"])
    with TestClient(create_app(settings, backend)) as test_client:
        yield test_client


def new_session(client: TestClient) -> str:
    response = client.post("/api/v1/sessions", json={"current_product_sku": "AF-400-220V"})
    assert response.status_code == 201
    body = response.json()
    assert body["restored"] is False and body["history"] == []
    return str(body["session_id"])


def ask(client: TestClient, session_id: str, request_id: str, message: str = "Qual a voltagem?") -> httpx.Response:
    return client.post(
        "/api/v1/chat/stream",
        json={
            "session_id": session_id,
            "client_request_id": request_id,
            "message": message,
            "context_filters": {"current_product_sku": "AF-400-220V"},
        },
    )


def test_chat_stream_emits_the_sse_contract_and_keeps_history(
    client: TestClient, backend: FakeBackend
) -> None:
    session_id = new_session(client)
    response = ask(client, session_id, str(uuid.uuid4()))

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    events = sse_events(response.text)
    assert [name for name, _ in events] == ["metadata", "token", "citations", "done"]
    assert events[0][1]["session_id"] == session_id
    assert events[-1][1]["finish_reason"] == "stop"
    assert backend.calls[0][:2] == ("AF-400-220V", "Qual a voltagem?")

    ask(client, session_id, str(uuid.uuid4()), "E a potência?")
    assert [(item.role, item.content) for item in backend.calls[1][2]] == [
        ("user", "Qual a voltagem?"),
        ("assistant", "Opera em 220V. "),
    ]


def test_same_request_id_replays_the_completed_turn_without_new_generation(
    client: TestClient, backend: FakeBackend
) -> None:
    session_id = new_session(client)
    request_id = str(uuid.uuid4())
    first = sse_events(ask(client, session_id, request_id).text)
    replay = sse_events(ask(client, session_id, request_id).text)

    assert len(backend.calls) == 1
    assert [name for name, _ in replay] == ["metadata", "token", "citations", "done"]
    assert replay[0][1]["message_id"] == first[0][1]["message_id"]
    assert replay[1][1] == first[1][1]


def test_reused_request_id_with_other_payload_is_a_conflict(client: TestClient) -> None:
    session_id = new_session(client)
    request_id = str(uuid.uuid4())
    ask(client, session_id, request_id)
    response = ask(client, session_id, request_id, "Outra pergunta")
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "IDEMPOTENCY_CONFLICT"


def test_turn_in_progress_returns_409_with_retry_after(client: TestClient) -> None:
    session_id = new_session(client)
    store = client.app.state.store  # type: ignore[attr-defined]
    store.begin_turn(store.get(session_id), "other-request", "hash")
    response = ask(client, session_id, str(uuid.uuid4()))
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "TURN_IN_PROGRESS"
    assert response.headers["retry-after"] == "1"


def test_low_similarity_fallback_ends_with_done_fallback(backend: FakeBackend, client: TestClient) -> None:
    backend.events = [FALLBACK, END]
    session_id = new_session(client)
    events = sse_events(ask(client, session_id, str(uuid.uuid4())).text)
    assert [name for name, _ in events] == ["metadata", "error", "done"]
    assert events[1][1]["code"] == "LOW_SIMILARITY_FALLBACK"
    assert events[-1][1]["finish_reason"] == "fallback"


def test_unknown_session_and_missing_product_are_contract_errors(client: TestClient) -> None:
    response = ask(client, str(uuid.uuid4()), str(uuid.uuid4()))
    assert response.status_code == 404
    assert set(response.json()["error"]) == {"code", "message", "trace_id", "details"}

    bare = client.post("/api/v1/sessions", json={}).json()["session_id"]
    response = client.post(
        "/api/v1/chat/stream",
        json={"session_id": bare, "client_request_id": str(uuid.uuid4()), "message": "Oi"},
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "PRODUCT_CONTEXT_REQUIRED"


def test_request_body_follows_chat_stream_request(client: TestClient) -> None:
    session_id = new_session(client)
    response = client.post(
        "/api/v1/chat/stream",
        json={"session_id": session_id, "client_request_id": str(uuid.uuid4()), "message": "x", "sku_context": "AF"},
    )
    assert response.status_code == 422


def test_delete_session(client: TestClient) -> None:
    session_id = new_session(client)
    assert client.delete(f"/api/v1/sessions/{session_id}").status_code == 204
    assert client.delete(f"/api/v1/sessions/{session_id}").status_code == 404


def test_cors_allows_the_frontend_origin(client: TestClient) -> None:
    response = client.options(
        "/api/v1/chat/stream",
        headers={"Origin": "http://localhost:3000", "Access-Control-Request-Method": "POST"},
    )
    assert response.headers["access-control-allow-origin"] == "http://localhost:3000"


def test_health_reports_degraded_when_backend_is_down(client: TestClient) -> None:
    body = client.get("/api/v1/health").json()
    assert body["status"] == "degraded" and body["components"]["backend"] == "unreachable"


def test_cors_origins_accept_a_comma_separated_env_value(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CORS_ALLOWED_ORIGINS", "http://a.test, http://b.test")
    assert Settings().cors_allowed_origins == ["http://a.test", "http://b.test"]


def _collect(client: BackendClient) -> list[Mapping[str, object]]:
    async def run() -> list[Mapping[str, object]]:
        stream = client.open_stream("AF-400-220V", "Voltagem?", [HistoryItem("user", "Oi")])
        try:
            return [event async for event in stream]
        finally:
            await stream.aclose()

    return asyncio.run(run())


def test_backend_client_posts_the_rag_request_and_parses_ndjson() -> None:
    seen: list[dict[str, object]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(json.loads(request.content))
        body = "\n".join(json.dumps(event) for event in (TOKEN, END)) + "\n\n"
        return httpx.Response(200, text=body)

    http = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    assert _collect(BackendClient(http, "http://backend:8001/")) == [TOKEN, END]
    assert seen == [
        {"sku": "AF-400-220V", "question": "Voltagem?", "history": [{"role": "user", "content": "Oi"}]}
    ]


@pytest.mark.parametrize(
    ("handler_failure", "expected"),
    [(httpx.ConnectError("down"), ConnectionError), (httpx.ReadTimeout("slow"), TimeoutError)],
)
def test_backend_transport_failures_map_to_builtin_errors(
    handler_failure: Exception, expected: type[Exception]
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise handler_failure

    http = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    with pytest.raises(expected):
        _collect(BackendClient(http, "http://backend:8001"))


def test_backend_http_error_is_a_connection_error() -> None:
    http = httpx.AsyncClient(transport=httpx.MockTransport(lambda request: httpx.Response(500)))
    with pytest.raises(ConnectionError):
        _collect(BackendClient(http, "http://backend:8001"))
