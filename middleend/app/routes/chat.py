"""Public gateway routes for the MVP: sessions, chat SSE stream and health."""

import hashlib
import time
import uuid
from dataclasses import dataclass
from typing import Protocol

import httpx
from fastapi import APIRouter, Request, Response
from fastapi.responses import JSONResponse, StreamingResponse

from app.cache.service import CachedAnswer, SemanticCacheService
from app.clients.backend import ReplayStream
from app.config import Settings
from app.schemas import ChatStreamRequest, SessionCreate
from app.sessions.store import HistoryItem, SessionSnapshot, SessionStore, TurnDecision
from app.sse import sse_chat_generator
from app.sse.models import BackendStream, CompletedTurn, ProductCard

router = APIRouter(prefix="/api/v1")

SSE_HEADERS = {"Cache-Control": "no-cache", "X-Accel-Buffering": "no"}
HEALTH_TIMEOUT_SECONDS = 2.0


class RagBackend(Protocol):
    def open_stream(
        self,
        sku: str,
        question: str,
        history: list[HistoryItem],
        *,
        preferred_voltage: str | None = None,
    ) -> BackendStream: ...


def error_response(
    status: int, code: str, message: str, headers: dict[str, str] | None = None
) -> JSONResponse:
    body = {"error": {"code": code, "message": message, "trace_id": str(uuid.uuid4()), "details": {}}}
    return JSONResponse(body, status_code=status, headers=headers)


def _payload_hash(body: ChatStreamRequest) -> str:
    return hashlib.sha256(body.model_dump_json(exclude={"client_request_id"}).encode()).hexdigest()


async def _no_recommendations() -> list[ProductCard]:
    # Cards come from the backend (B04). When the backend itself is unreachable the
    # gateway has no SQL-validated card to offer, so the contingency publishes none.
    return []


@dataclass(frozen=True)
class _Answer:
    """Where this turn's events come from; cache_key is set only for a fresh generation."""

    stream: BackendStream
    cache_key: str | None = None
    cache_hit: bool = False


def _resolved_filters(body: ChatStreamRequest, sku: str) -> dict[str, object]:
    filters = body.context_filters.model_dump() if body.context_filters else {}
    return {**filters, "current_product_sku": sku}


def _cached_turn(cached: CachedAnswer, session_id: str, message_id: str) -> CompletedTurn:
    return CompletedTurn(
        session_id=session_id,
        message_id=message_id,
        content=cached.answer_text,
        citations=cached.citations,
        products=cached.recommendations,
        finish_reason="stop",
        tokens_used=cached.tokens_used,
        intent=cached.intent,
        cache_hit=True,
        ttft_ms=0,
        total_latency_ms=0,
    )


async def _open_answer(
    cache: SemanticCacheService | None,
    backend: RagBackend,
    body: ChatStreamRequest,
    sku: str,
    session: SessionSnapshot,
    message_id: str,
) -> _Answer:
    """Serve a revalidated cache hit, or open the backend stream for a new generation."""
    history = [{"role": item.role, "content": item.content} for item in session.history]
    cache_key = (
        await cache.key_for(body.message, _resolved_filters(body, sku), history)
        if cache is not None
        else None
    )
    cached = await cache.lookup(cache_key) if cache is not None and cache_key else None
    if cached is not None:
        turn = _cached_turn(cached, session.session_id, message_id)
        return _Answer(ReplayStream(turn), cache_hit=True)
    voltage = body.context_filters.preferred_voltage if body.context_filters else None
    stream = backend.open_stream(
        sku, body.message, list(session.history), preferred_voltage=voltage
    )
    return _Answer(stream, cache_key=cache_key)


def _session_body(session: SessionSnapshot, settings: Settings, *, restored: bool) -> dict[str, object]:
    return {
        "session_id": session.session_id,
        "restored": restored,
        "history": [
            {"id": item.message_id, "role": item.role, "content": item.content}
            for item in session.history
        ],
        "expires_in_seconds": settings.session_ttl_seconds,
    }


@router.post("/sessions", status_code=201)
async def create_session(body: SessionCreate, request: Request) -> JSONResponse:
    """201 for a new session; 200 with the history window when `session_id` is still active."""
    store: SessionStore = request.app.state.store
    settings: Settings = request.app.state.settings
    if body.session_id is not None:
        active = await store.get(str(body.session_id))
        if active is not None:
            return JSONResponse(_session_body(active, settings, restored=True), status_code=200)
    session = await store.create(body.current_product_sku)
    return JSONResponse(_session_body(session, settings, restored=False), status_code=201)


@router.delete("/sessions/{session_id}", status_code=204, response_model=None)
async def end_session(session_id: uuid.UUID, request: Request) -> Response:
    store: SessionStore = request.app.state.store
    if not await store.delete(str(session_id)):
        return error_response(404, "SESSION_NOT_FOUND", "Sessão não encontrada ou expirada.")
    return Response(status_code=204)


@router.post("/chat/stream", response_model=None)
async def chat_stream(body: ChatStreamRequest, request: Request) -> Response:
    started_at = time.perf_counter()
    store: SessionStore = request.app.state.store
    backend: RagBackend = request.app.state.backend
    settings: Settings = request.app.state.settings

    session = await store.get(str(body.session_id))
    if session is None:
        return error_response(404, "SESSION_NOT_FOUND", "Sessão não encontrada ou expirada.")
    filters = body.context_filters
    sku = (filters.current_product_sku if filters else None) or session.current_product_sku
    if not sku:
        return error_response(422, "PRODUCT_CONTEXT_REQUIRED", "Informe o produto consultado.")

    request_id = str(body.client_request_id)
    turn = await store.begin_turn(session.session_id, request_id, _payload_hash(body))
    if turn.kind == TurnDecision.CONFLICT:
        return error_response(
            409, "IDEMPOTENCY_CONFLICT", "client_request_id reutilizado com outro conteúdo."
        )
    if turn.kind == TurnDecision.IN_PROGRESS:
        return error_response(
            409,
            "TURN_IN_PROGRESS",
            "Já existe uma resposta em andamento nesta sessão.",
            headers={"Retry-After": str(settings.turn_retry_after_seconds)},
        )

    cache: SemanticCacheService | None = request.app.state.cache
    if turn.kind == TurnDecision.REPLAY and turn.completed is not None:
        answer = _Answer(ReplayStream(turn.completed))
    else:
        answer = await _open_answer(cache, backend, body, sku, session, turn.message_id)

    async def release_turn() -> None:
        await store.release(session.session_id, request_id)

    async def complete_turn(completed: CompletedTurn) -> None:
        await store.complete(session.session_id, request_id, body.message, completed)
        if cache is not None and answer.cache_key is not None:
            await cache.store(answer.cache_key, completed)

    frames = sse_chat_generator(
        request,
        session.session_id,
        turn.message_id,
        answer.stream,
        answer.cache_hit,
        release_turn,
        _no_recommendations,
        complete_turn,
        started_at=started_at,
    )
    return StreamingResponse(frames, media_type="text/event-stream", headers=SSE_HEADERS)


@router.get("/health")
async def health(request: Request) -> JSONResponse:
    settings: Settings = request.app.state.settings
    http: httpx.AsyncClient = request.app.state.http
    store: SessionStore = request.app.state.store
    try:
        response = await http.get(
            settings.backend_internal_url.rstrip("/") + "/health", timeout=HEALTH_TIMEOUT_SECONDS
        )
        backend_status = "ok" if response.is_success else "error"
    except httpx.HTTPError:
        backend_status = "unreachable"
    if not request.app.state.redis_enabled:
        redis_status = "disabled"  # sessions in process memory
    else:
        redis_status = "ok" if await store.ping() else "error"
    healthy = backend_status == "ok" and redis_status != "error"
    return JSONResponse(
        {
            "status": "ok" if healthy else "degraded",
            "components": {
                "redis": redis_status,
                "postgres": "via-backend",
                "backend": backend_status,
            },
            "version": settings.app_version,
        }
    )
