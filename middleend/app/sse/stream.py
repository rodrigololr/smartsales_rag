"""M02 SSE library with injected transport, persistence and resource callbacks.

Caller acquires the session lock before consumption. Backend adapters yield only
G-OUT approved content, normalize transport errors to TimeoutError/ConnectionError,
and own the sole permitted retry BEFORE publishing tokens. Cache replay uses this
same protocol, including end. This generator never restarts generation.

complete_turn atomically persists the approved snapshot/idempotency and updates
history/cache before returning, including cache hits. It must be idempotent. It
is never called for failed or incomplete turns. Domain fallbacks are completed
snapshots; orchestration decides cache eligibility and records failed-turn audit.
Cards originate in SQL; adapters serialize Decimal prices to JSON-ready numbers.
No money arithmetic, HTTP, SQL or Redis lives in this module. HTTP adapters set
SSE headers and MUST close the async generator when consumers stop reading.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from collections.abc import AsyncGenerator, AsyncIterator, Awaitable, Callable, Mapping
from dataclasses import dataclass, field
from typing import Literal, cast

from .models import (
    BackendStream,
    Citation,
    CompletedTurn,
    DisconnectRequest,
    ErrorCode,
    FinishReason,
    ProductCard,
    PublicEventName,
)
from .validation import citations, parse, products, require

logger = logging.getLogger(__name__)
SAFE_FAILURE_MESSAGE = "Não foi possível concluir a resposta. Tente novamente."
PUBLIC_EVENTS = {"metadata", "token", "correction", "citations", "recommendations", "error", "done"}


def format_sse(event: PublicEventName, payload: Mapping[str, object]) -> str:
    """Encode one frame, rejecting event-name injection and non-finite numbers."""
    require(event in PUBLIC_EVENTS)
    return f"event: {event}\ndata: {json.dumps(payload, ensure_ascii=False, allow_nan=False)}\n\n"


@dataclass
class _Turn:
    session_id: str
    message_id: str
    cache_hit: bool
    start: float
    clock: Callable[[], float]
    metadata_sent: bool = False
    disconnected: bool = False
    received_end: bool = False
    stage: int = 0
    had_tokens: bool = False
    error_seen: bool = False
    finish_reason: FinishReason = "stop"
    error_code: ErrorCode | None = None
    recoverable: bool | None = None
    tokens_used: int = 0
    intent: str | None = None
    content: list[str] = field(default_factory=list)
    citations: list[Citation] = field(default_factory=list)
    products: list[ProductCard] = field(default_factory=list)
    ttft_ms: int = 0

    def elapsed(self) -> int:
        return max(0, int((self.clock() - self.start) * 1000))

    def accept(self, event: str, payload: Mapping[str, object]) -> None:
        if event == "end":
            require(self.stage > 0)
            self.received_end = True
            self.tokens_used = cast(int, payload["tokens_used"])
            self.intent = cast(str | None, payload.get("intent"))
        elif event == "error":
            self._accept_error(payload)
        else:
            self._accept_content(event, payload)

    def _accept_error(self, payload: Mapping[str, object]) -> None:
        require(not self.error_seen)
        self.error_seen = True
        code = payload["code"]
        self.error_code = cast(ErrorCode, code)
        self.recoverable = cast(bool, payload["recoverable"])
        self.finish_reason = (
            "error"
            if self.had_tokens or code in {"INTERNAL_ERROR", "LLM_UNAVAILABLE"}
            else "fallback"
        )
        self.content = [cast(str, payload["fallback_message"])]
        self.citations.clear()
        self.products.clear()
        self.stage = 5

    def _accept_content(self, event: str, payload: Mapping[str, object]) -> None:
        if event == "token":
            require(self.stage <= 1)
            self.had_tokens = True
            self.content.append(cast(str, payload["delta"]))
            self.stage = 1
        elif event == "correction":
            require(self.stage == 1)
            self.content = [cast(str, payload["content"])]
            self.stage = 2
        elif event == "citations":
            require(self.stage in (1, 2))
            self.citations = citations(payload["citations"])
            self.stage = 3
        elif event == "recommendations":
            require(self.stage in (1, 2, 3, 5))
            self.products = products(payload["products"])
            self.stage = 6 if self.error_seen else 4

    def completed(self) -> CompletedTurn:
        require(self.finish_reason != "error" and self.received_end)
        return CompletedTurn(
            session_id=self.session_id,
            message_id=self.message_id,
            content="".join(self.content),
            citations=tuple(self.citations),
            products=tuple(self.products),
            finish_reason=cast(Literal["stop", "fallback"], self.finish_reason),
            tokens_used=self.tokens_used,
            intent=self.intent,
            cache_hit=self.cache_hit,
            ttft_ms=self.ttft_ms,
            total_latency_ms=self.elapsed(),
            error_code=self.error_code,
            recoverable=self.recoverable,
        )


async def _connected(request: DisconnectRequest, turn: _Turn) -> bool:
    if not turn.disconnected:
        turn.disconnected = await request.is_disconnected()
    return not turn.disconnected


async def _frames(
    request: DisconnectRequest,
    turn: _Turn,
    event: PublicEventName,
    payload: Mapping[str, object],
) -> AsyncIterator[str]:
    if not await _connected(request, turn):
        return
    if not turn.metadata_sent:
        turn.ttft_ms = turn.elapsed()
        turn.metadata_sent = True
        yield format_sse(
            "metadata",
            {
                "session_id": turn.session_id,
                "message_id": turn.message_id,
                "cache_hit": turn.cache_hit,
                "ttft_ms": turn.ttft_ms,
            },
        )
    if await _connected(request, turn):
        yield format_sse(event, payload)


async def _failure_frames(
    request: DisconnectRequest,
    turn: _Turn,
    failure: Exception,
    fallback_products: Callable[[], Awaitable[list[ProductCard]]],
) -> AsyncIterator[str]:
    turn.finish_reason = "error"
    code = (
        "LLM_UNAVAILABLE"
        if isinstance(failure, (TimeoutError, ConnectionError))
        else "INTERNAL_ERROR"
    )
    # Contract allows a single error per turn: keep the backend's if already published.
    if not turn.error_seen:
        async for frame in _frames(
            request,
            turn,
            "error",
            {
                "code": code,
                "recoverable": True,
                "fallback_message": SAFE_FAILURE_MESSAGE,
            },
        ):
            yield frame
    # stage 6 = cards already published after that error; never send a second set.
    if turn.stage == 6 or not await _connected(request, turn):
        return
    try:
        fallback = products(await fallback_products())
    except Exception:
        logger.exception("fallback_products_failed", extra={"session_id": turn.session_id})
        return
    async for frame in _frames(request, turn, "recommendations", {"products": fallback}):
        yield frame


async def _cleanup(
    backend: BackendStream, release_turn: Callable[[], Awaitable[None]], session_id: str
) -> None:
    """Logged, never raised: the turn outcome is already decided (and maybe persisted)."""
    try:
        await backend.aclose()
    except Exception:
        logger.exception("backend_close_failed", extra={"session_id": session_id})
    finally:
        try:
            await release_turn()
        except Exception:
            logger.exception("release_turn_failed", extra={"session_id": session_id})


async def _finish_cleanup(
    backend: BackendStream,
    release_turn: Callable[[], Awaitable[None]],
    session_id: str,
) -> None:
    """Shield resource cleanup when cancellation arrives while cleanup awaits."""
    cleanup = asyncio.create_task(_cleanup(backend, release_turn, session_id))
    try:
        await asyncio.shield(cleanup)
    except asyncio.CancelledError:
        try:
            await asyncio.shield(cleanup)
        finally:
            raise


class SSEStream:
    """Async iterator of SSE frames that releases resources even if closed unread.

    An async generator closed before its first read never runs its finally block,
    which would leak the session lock and the backend stream.
    """

    def __init__(
        self, frames: AsyncGenerator[str, None], cleanup: Callable[[], Awaitable[None]]
    ) -> None:
        self._frames = frames
        self._cleanup = cleanup
        self._started = False

    def __aiter__(self) -> SSEStream:
        return self

    async def __anext__(self) -> str:
        self._started = True
        return await self._frames.__anext__()

    async def aclose(self) -> None:
        if not self._started:
            self._started = True
            await self._cleanup()
        await self._frames.aclose()


def sse_chat_generator(
    request: DisconnectRequest,
    session_id: str,
    message_id: str,
    backend_stream: BackendStream,
    cache_hit: bool,
    release_turn: Callable[[], Awaitable[None]],
    fallback_products: Callable[[], Awaitable[list[ProductCard]]],
    complete_turn: Callable[[CompletedTurn], Awaitable[None]],
    *,
    started_at: float | None = None,
    clock: Callable[[], float] = time.perf_counter,
) -> SSEStream:
    """Emit ordered SSE, persist approved completion, release resources then done.

    Adapter exceptions are caught and logged at this stream boundary; cancellation
    and GeneratorExit propagate. Cleanup failures are logged and never replace the
    decided outcome: a persisted turn still gets its done, so the client won't resend it.
    Every frame and final persistence is preceded by a disconnect check.
    """
    turn = _Turn(
        session_id, message_id, cache_hit, clock() if started_at is None else started_at, clock
    )
    frames = _sse_frames(
        request, turn, backend_stream, release_turn, fallback_products, complete_turn
    )
    return SSEStream(frames, lambda: _finish_cleanup(backend_stream, release_turn, session_id))


async def _sse_frames(
    request: DisconnectRequest,
    turn: _Turn,
    backend_stream: BackendStream,
    release_turn: Callable[[], Awaitable[None]],
    fallback_products: Callable[[], Awaitable[list[ProductCard]]],
    complete_turn: Callable[[CompletedTurn], Awaitable[None]],
) -> AsyncGenerator[str, None]:
    session_id, message_id = turn.session_id, turn.message_id
    try:
        try:
            if not await _connected(request, turn):
                return
            async for item in backend_stream:
                if not await _connected(request, turn):
                    return
                event, payload = parse(item)
                turn.accept(event, payload)
                if event == "end":
                    break
                async for frame in _frames(request, turn, cast(PublicEventName, event), payload):
                    yield frame
                if turn.disconnected:
                    return
            require(turn.received_end and turn.metadata_sent)
            if not await _connected(request, turn):
                return
            if turn.finish_reason != "error":
                await complete_turn(turn.completed())
        except Exception as failure:
            # Includes transport/persistence adapter failures; never cancellation.
            logger.exception(
                "stream_failed", extra={"session_id": session_id, "message_id": message_id}
            )
            async for frame in _failure_frames(request, turn, failure, fallback_products):
                yield frame
    finally:
        await _finish_cleanup(backend_stream, release_turn, session_id)
    if await _connected(request, turn):
        yield format_sse(
            "done",
            {
                "finish_reason": turn.finish_reason,
                "total_latency_ms": turn.elapsed(),
                "tokens_used": turn.tokens_used,
            },
        )
