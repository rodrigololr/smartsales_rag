"""Public gateway routes for the MVP: sessions, chat SSE stream and health."""

import hashlib
import json
import logging
import time
import uuid
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Protocol

import anyio
import httpx
from fastapi import APIRouter, Request, Response
from fastapi.responses import JSONResponse

from app.cache.service import CachedAnswer, SemanticCacheService
from app.clients.backend import ReplayStream
from app.config import Settings
from app.ratelimit import RateDecision, RateLimiter
from app.schemas import (
    ERROR_RESPONSES,
    JSON_ERROR_RESPONSES,
    ChatStreamRequest,
    Filters,
    SessionCreate,
)
from app.sessions.lease import LeaseStream
from app.sessions.response import SessionStreamingResponse
from app.sessions.store import HistoryItem, SessionSnapshot, SessionStore, TurnDecision, TurnState
from app.sse import sse_chat_generator
from app.sse.models import BackendStream, CompletedTurn, ProductCard
from app.telemetry.tracing import current_trace_id

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1")

SSE_HEADERS = {
    "Cache-Control": "no-cache, no-transform",
    "Connection": "keep-alive",
    "X-Accel-Buffering": "no",
}
HEALTH_TIMEOUT_SECONDS = 2.0


class RagBackend(Protocol):
    def open_stream(
        self,
        sku: str | None,
        question: str,
        history: list[HistoryItem],
        *,
        filters: Filters | None = None,
    ) -> BackendStream: ...


def error_response(
    status: int, code: str, message: str, headers: Mapping[str, str] | None = None
) -> JSONResponse:
    body = {
        "error": {"code": code, "message": message, "trace_id": current_trace_id(), "details": {}}
    }
    return JSONResponse(body, status_code=status, headers=headers)


def rate_limited(decision: RateDecision, limit: int) -> JSONResponse:
    return error_response(
        429,
        "RATE_LIMITED",
        f"Limite de {limit} requisições por minuto excedido.",
        headers={"Retry-After": str(decision.retry_after_seconds)},
    )


def _payload_hash(body: ChatStreamRequest) -> str:
    payload = body.model_dump(mode="json", exclude={"client_request_id"})
    if body.context_filters is not None and body.context_filters.budget_max is not None:
        payload["context_filters"]["budget_max"] = f"{body.context_filters.budget_max:.2f}"
    encoded = json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(encoded.encode()).hexdigest()


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
    sku: str | None,
    session: SessionSnapshot,
    message_id: str,
    *,
    store: SessionStore,
    request_id: str,
    lock_token: str,
    settings: Settings,
) -> _Answer:
    """Serve a revalidated cache hit, or open the backend stream for a new generation."""
    history = [{"role": item.role, "content": item.content} for item in session.history]
    cache_key = (
        await cache.key_for(body.message, _resolved_filters(body, sku), history)
        if cache is not None and sku is not None
        else None
    )
    cached = await cache.lookup(cache_key) if cache is not None and cache_key else None
    if cached is not None:
        turn = _cached_turn(cached, session.session_id, message_id)
        return _Answer(ReplayStream(turn), cache_hit=True)
    stream = LeaseStream(
        backend.open_stream(
            sku, body.message, list(session.history), filters=body.context_filters
        ),
        store,
        session.session_id,
        request_id,
        lock_token,
        settings.session_heartbeat_seconds,
        settings.session_lock_ttl_seconds,
    )
    return _Answer(stream, cache_key=cache_key)


def _session_body(
    session: SessionSnapshot, settings: Settings, *, restored: bool
) -> dict[str, object]:
    return {
        "session_id": session.session_id,
        "restored": restored,
        "history": [
            {"id": item.message_id, "role": item.role, "content": item.content}
            for item in session.history
        ],
        "expires_in_seconds": settings.session_ttl_seconds,
    }


@router.post(
    "/sessions",
    status_code=201,
    operation_id="createSession",
    responses={**ERROR_RESPONSES, 200: {"description": "Sessão ativa restaurada com o histórico"}},
)
async def create_session(body: SessionCreate, request: Request) -> JSONResponse:
    """201 for a new session; 200 with the history window when `session_id` is still active."""
    store: SessionStore = request.app.state.store
    settings: Settings = request.app.state.settings
    if body.session_id is not None:
        request.state.session_id = str(body.session_id)  # for error logs
        active = await store.get(str(body.session_id))
        if active is not None:
            return JSONResponse(_session_body(active, settings, restored=True), status_code=200)
    session = await store.create(body.current_product_sku)
    return JSONResponse(_session_body(session, settings, restored=False), status_code=201)


@router.delete(
    "/sessions/{session_id}",
    status_code=204,
    response_model=None,
    operation_id="endSession",
    responses={status: ERROR_RESPONSES[status] for status in (404, 422, 429, 503)},
)
async def end_session(session_id: uuid.UUID, request: Request) -> Response:
    store: SessionStore = request.app.state.store
    request.state.session_id = str(session_id)  # for error logs
    if not await store.delete(str(session_id)):
        return error_response(404, "SESSION_NOT_FOUND", "Sessão não encontrada ou expirada.")
    return Response(status_code=204)


@router.post(
    "/chat/stream",
    status_code=200,
    response_model=None,
    response_class=SessionStreamingResponse,  # documents text/event-stream as the 200 body
    operation_id="streamChat",
    responses={**JSON_ERROR_RESPONSES, 200: {"description": "Eventos SSE (CLAUDE.md §5)"}},
)
async def chat_stream(body: ChatStreamRequest, request: Request) -> Response:
    started_at = time.perf_counter()
    store: SessionStore = request.app.state.store
    backend: RagBackend = request.app.state.backend
    settings: Settings = request.app.state.settings

    request.state.session_id = str(body.session_id)  # for error logs
    session = await store.get(str(body.session_id))
    if session is None:
        return error_response(404, "SESSION_NOT_FOUND", "Sessão não encontrada ou expirada.")
    # Chat is limited per session (not per IP): a class behind one NAT shares one IP.
    limiter: RateLimiter = request.app.state.rate_limiter
    decision = await limiter.check(f"session:{session.session_id}")
    if not decision.allowed:
        return rate_limited(decision, settings.rate_limit_per_minute)
    filters = body.context_filters
    sku = (filters.current_product_sku if filters else None) or session.current_product_sku or None

    request_id = str(body.client_request_id)
    turn = await store.begin_turn(session.session_id, request_id, _payload_hash(body))
    if turn.kind == TurnDecision.NOT_FOUND:
        return error_response(404, "SESSION_NOT_FOUND", "Sessão não encontrada ou expirada.")
    if turn.kind == TurnDecision.EXPIRED:
        return error_response(410, "TURN_EXPIRED", "Pedido expirado. Envie uma nova pergunta.")
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

    async def release_turn() -> None:
        await store.release(session.session_id, request_id, turn.lock_token)

    cache: SemanticCacheService | None = request.app.state.cache
    try:
        if turn.kind == TurnDecision.REPLAY and turn.completed is not None:
            answer = _Answer(ReplayStream(turn.completed))
        else:
            # Snapshot belongs to this acquisition; a GET before it may predate another completion.
            snapshot = turn.snapshot or session
            answer = await _open_answer(
                cache,
                backend,
                body,
                sku,
                snapshot,
                turn.message_id,
                store=store,
                request_id=request_id,
                lock_token=turn.lock_token,
                settings=settings,
            )
    except BaseException as failure:
        with anyio.CancelScope(shield=True):
            await release_turn()
        if isinstance(failure, Exception):
            logger.error(
                "backend_stream_initialization_failed", extra={"session_id": session.session_id}
            )
            return error_response(
                503,
                "SERVICE_UNAVAILABLE",
                "Não foi possível iniciar a resposta. Envie uma nova pergunta.",
            )
        raise

    async def complete_turn(completed: CompletedTurn) -> None:
        await store.complete(
            session.session_id, request_id, turn.lock_token, body.message, completed
        )
        if cache is not None and answer.cache_key is not None and sku is not None:
            await cache.store(answer.cache_key, completed, sku)

    async def fail_turn(completed: CompletedTurn) -> None:
        await store.complete(
            session.session_id, request_id, turn.lock_token, body.message, completed
        )

    async def transition(state: TurnState) -> None:
        if turn.lock_token:
            await store.transition(session.session_id, turn.lock_token, state)

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
        fail_turn=fail_turn,
        transition=transition,
        check_delivery=answer.stream.check_delivery
        if isinstance(answer.stream, LeaseStream)
        else None,
    )
    return SessionStreamingResponse(frames, headers=SSE_HEADERS)


# Exempt from rate limiting, so no 429 (openapi.yaml).
@router.get(
    "/health",
    operation_id="health",
    responses={status: body for status, body in ERROR_RESPONSES.items() if status != 429},
)
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
    database_ok = await store.database_ping()
    postgres_status = "via-backend" if database_ok is None else "ok" if database_ok else "error"
    healthy = backend_status == "ok" and redis_status != "error" and postgres_status != "error"
    return JSONResponse(
        {
            "status": "ok" if healthy else "degraded",
            "components": {
                "redis": redis_status,
                "postgres": postgres_status,
                "backend": backend_status,
            },
            "version": settings.app_version,
        }
    )
