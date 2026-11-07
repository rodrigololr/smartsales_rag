"""Public gateway routes for the MVP: sessions, chat SSE stream and health."""

import hashlib
import time
import uuid
from typing import Protocol

import httpx
from fastapi import APIRouter, Request, Response
from fastapi.responses import JSONResponse, StreamingResponse

from app.clients.backend import ReplayStream
from app.config import Settings
from app.schemas import ChatStreamRequest, SessionCreate
from app.sessions.store import HistoryItem, SessionStore, TurnDecision
from app.sse import sse_chat_generator
from app.sse.models import BackendStream, CompletedTurn, ProductCard

router = APIRouter(prefix="/api/v1")

SSE_HEADERS = {"Cache-Control": "no-cache", "X-Accel-Buffering": "no"}
HEALTH_TIMEOUT_SECONDS = 2.0


class RagBackend(Protocol):
    def open_stream(
        self, sku: str, question: str, history: list[HistoryItem]
    ) -> BackendStream: ...


def error_response(
    status: int, code: str, message: str, headers: dict[str, str] | None = None
) -> JSONResponse:
    body = {"error": {"code": code, "message": message, "trace_id": str(uuid.uuid4()), "details": {}}}
    return JSONResponse(body, status_code=status, headers=headers)


def _payload_hash(body: ChatStreamRequest) -> str:
    return hashlib.sha256(body.model_dump_json(exclude={"client_request_id"}).encode()).hexdigest()


async def _no_recommendations() -> list[ProductCard]:
    # shortcut: the MVP chat has no upsell/cross-sell cards; plug B04 here later.
    return []


@router.post("/sessions", status_code=201)
async def create_session(body: SessionCreate, request: Request) -> JSONResponse:
    store: SessionStore = request.app.state.store
    settings: Settings = request.app.state.settings
    # shortcut: no restore of previous sessions yet; every call opens a new one.
    session = store.create(body.current_product_sku)
    return JSONResponse(
        {
            "session_id": session.session_id,
            "restored": False,
            "history": [],
            "expires_in_seconds": settings.session_ttl_seconds,
        },
        status_code=201,
    )


@router.delete("/sessions/{session_id}", status_code=204, response_model=None)
async def end_session(session_id: uuid.UUID, request: Request) -> Response:
    store: SessionStore = request.app.state.store
    if not store.delete(str(session_id)):
        return error_response(404, "SESSION_NOT_FOUND", "Sessão não encontrada ou expirada.")
    return Response(status_code=204)


@router.post("/chat/stream", response_model=None)
async def chat_stream(body: ChatStreamRequest, request: Request) -> Response:
    started_at = time.perf_counter()
    store: SessionStore = request.app.state.store
    backend: RagBackend = request.app.state.backend
    settings: Settings = request.app.state.settings

    session = store.get(str(body.session_id))
    if session is None:
        return error_response(404, "SESSION_NOT_FOUND", "Sessão não encontrada ou expirada.")
    filters = body.context_filters
    sku = (filters.current_product_sku if filters else None) or session.current_product_sku
    if not sku:
        return error_response(422, "PRODUCT_CONTEXT_REQUIRED", "Informe o produto consultado.")

    request_id = str(body.client_request_id)
    turn = store.begin_turn(session, request_id, _payload_hash(body))
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

    stream: BackendStream
    if turn.kind == TurnDecision.REPLAY and turn.completed is not None:
        stream = ReplayStream(turn.completed)
    else:
        stream = backend.open_stream(sku, body.message, list(session.history))

    async def release_turn() -> None:
        store.release(session, request_id)

    async def complete_turn(completed: CompletedTurn) -> None:
        store.complete(session, request_id, body.message, completed)

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
    )
    return StreamingResponse(frames, media_type="text/event-stream", headers=SSE_HEADERS)


@router.get("/health")
async def health(request: Request) -> JSONResponse:
    settings: Settings = request.app.state.settings
    http: httpx.AsyncClient = request.app.state.http
    try:
        response = await http.get(
            settings.backend_internal_url.rstrip("/") + "/health", timeout=HEALTH_TIMEOUT_SECONDS
        )
        backend_status = "ok" if response.is_success else "error"
    except httpx.HTTPError:
        backend_status = "unreachable"
    return JSONResponse(
        {
            "status": "ok" if backend_status == "ok" else "degraded",
            "components": {"redis": "disabled", "postgres": "via-backend", "backend": backend_status},
            "version": settings.app_version,
        }
    )
