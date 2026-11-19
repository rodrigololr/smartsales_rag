"""Public gateway routes for the MVP: sessions, chat SSE stream and health."""

import hashlib
import json
import logging
import time
import uuid
from typing import Protocol

import anyio
import httpx
from fastapi import APIRouter, Request, Response
from fastapi.responses import JSONResponse

from app.clients.backend import ReplayStream
from app.config import Settings
from app.schemas import ChatStreamRequest, Filters, SessionCreate
from app.sessions.lease import LeaseStream
from app.sessions.response import SessionStreamingResponse
from app.sessions.store import HistoryItem, SessionSnapshot, SessionStore, TurnDecision, TurnState
from app.sse import sse_chat_generator
from app.sse.models import BackendStream, CompletedTurn, ProductCard

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
        sku: str,
        question: str,
        history: list[HistoryItem],
        *,
        filters: Filters | None = None,
    ) -> BackendStream: ...


def error_response(
    status: int, code: str, message: str, headers: dict[str, str] | None = None
) -> JSONResponse:
    body = {
        "error": {"code": code, "message": message, "trace_id": str(uuid.uuid4()), "details": {}}
    }
    return JSONResponse(body, status_code=status, headers=headers)


def _payload_hash(body: ChatStreamRequest) -> str:
    payload = body.model_dump(mode="json", exclude={"client_request_id"})
    if body.context_filters is not None and body.context_filters.budget_max is not None:
        payload["context_filters"]["budget_max"] = f"{body.context_filters.budget_max:.2f}"
    encoded = json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(encoded.encode()).hexdigest()


async def _no_recommendations() -> list[ProductCard]:
    # shortcut: the MVP chat has no upsell/cross-sell cards; plug B04 here later.
    return []


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


@router.post("/sessions", status_code=201)
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


@router.delete("/sessions/{session_id}", status_code=204, response_model=None)
async def end_session(session_id: uuid.UUID, request: Request) -> Response:
    store: SessionStore = request.app.state.store
    request.state.session_id = str(session_id)  # for error logs
    if not await store.delete(str(session_id)):
        return error_response(404, "SESSION_NOT_FOUND", "Sessão não encontrada ou expirada.")
    return Response(status_code=204)


@router.post("/chat/stream", response_model=None)
async def chat_stream(body: ChatStreamRequest, request: Request) -> Response:
    started_at = time.perf_counter()
    store: SessionStore = request.app.state.store
    backend: RagBackend = request.app.state.backend
    settings: Settings = request.app.state.settings

    request.state.session_id = str(body.session_id)  # for error logs
    session = await store.get(str(body.session_id))
    if session is None:
        return error_response(404, "SESSION_NOT_FOUND", "Sessão não encontrada ou expirada.")
    filters = body.context_filters
    sku = (filters.current_product_sku if filters else None) or session.current_product_sku
    if not sku:
        return error_response(422, "PRODUCT_CONTEXT_REQUIRED", "Informe o produto consultado.")

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

    async def complete_turn(completed: CompletedTurn) -> None:
        await store.complete(
            session.session_id, request_id, turn.lock_token, body.message, completed
        )

    async def transition(state: TurnState) -> None:
        if turn.lock_token:
            await store.transition(session.session_id, turn.lock_token, state)

    stream: BackendStream
    try:
        if turn.kind == TurnDecision.REPLAY and turn.completed is not None:
            stream = ReplayStream(turn.completed)
        else:
            # Snapshot belongs to this acquisition; a GET before it may predate another completion.
            snapshot = turn.snapshot or session
            stream = LeaseStream(
                backend.open_stream(sku, body.message, list(snapshot.history), filters=filters),
                store,
                session.session_id,
                request_id,
                turn.lock_token,
                settings.session_heartbeat_seconds,
                settings.session_lock_ttl_seconds,
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

    frames = sse_chat_generator(
        request,
        session.session_id,
        turn.message_id,
        stream,
        False,
        release_turn,
        _no_recommendations,
        complete_turn,
        started_at=started_at,
        fail_turn=complete_turn,
        transition=transition,
        check_delivery=stream.check_delivery if isinstance(stream, LeaseStream) else None,
    )
    return SessionStreamingResponse(frames, headers=SSE_HEADERS)


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
