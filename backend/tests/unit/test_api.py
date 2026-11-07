"""Internal worker HTTP surface: NDJSON stream of the orchestrator events."""

import json
from collections.abc import AsyncIterator, Iterator

import pytest
from app.main import app, get_orchestrator
from app.models.schemas import RagRequest
from fastapi.testclient import TestClient


class FakeOrchestrator:
    def __init__(self) -> None:
        self.requests: list[RagRequest] = []

    async def stream(self, request: RagRequest) -> AsyncIterator[dict[str, object]]:
        self.requests.append(request)
        yield {"event": "token", "data": {"delta": "Olá"}}
        yield {"event": "end", "data": {"tokens_used": 1, "intent": "TECHNICAL_QA"}}


@pytest.fixture
def fake() -> Iterator[FakeOrchestrator]:
    orchestrator = FakeOrchestrator()
    app.dependency_overrides[get_orchestrator] = lambda: orchestrator
    yield orchestrator
    app.dependency_overrides.clear()


def test_rag_stream_returns_one_json_event_per_line(fake: FakeOrchestrator) -> None:
    response = TestClient(app).post(
        "/internal/rag/stream",
        json={"sku": "AF-400-220V", "question": "Voltagem?", "history": []},
    )
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/x-ndjson")
    events = [json.loads(line) for line in response.text.splitlines()]
    assert [event["event"] for event in events] == ["token", "end"]
    assert fake.requests[0].sku == "AF-400-220V"


def test_rag_stream_validates_the_request(fake: FakeOrchestrator) -> None:
    response = TestClient(app).post("/internal/rag/stream", json={"sku": "", "question": ""})
    assert response.status_code == 422


def test_health() -> None:
    assert TestClient(app).get("/health").json() == {"status": "ok"}
