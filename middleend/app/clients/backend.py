"""BackendStream adapters for sse_chat_generator: the live RAG worker and cache-free replay."""

import asyncio
import json
from collections.abc import AsyncIterator, Iterator, Mapping, Sequence
from contextlib import AbstractAsyncContextManager
from typing import cast

import httpx

from app.schemas import Filters
from app.sessions.store import HistoryItem
from app.sse.models import CompletedTurn

InternalEvent = Mapping[str, object]


class NdjsonBackendStream:
    """POST /internal/rag/stream, read lazily on first iteration.

    Transport failures become TimeoutError/ConnectionError, as the M02 generator expects.
    """

    def __init__(
        self,
        client: httpx.AsyncClient,
        url: str,
        payload: Mapping[str, object],
        first_event_timeout_seconds: float = 3.0,
    ) -> None:
        self._client = client
        self._url = url
        self._payload = payload
        self._first_timeout = first_event_timeout_seconds
        self._published = False
        self._retries = 0
        self._context: AbstractAsyncContextManager[httpx.Response] | None = None
        self._lines: AsyncIterator[str] | None = None

    def __aiter__(self) -> AsyncIterator[InternalEvent]:
        return self

    async def __anext__(self) -> InternalEvent:
        while True:
            try:
                if self._published:
                    return await self._read_event()
                async with asyncio.timeout(self._first_timeout):
                    event = await self._read_event()
                self._published = True
                return event
            except (httpx.TimeoutException, TimeoutError) as error:
                failure: Exception = TimeoutError("backend first event/read timeout")
                failure.__cause__ = error
            except (httpx.TransportError, ConnectionError) as error:
                failure = ConnectionError("backend unreachable")
                failure.__cause__ = error
            if self._published or self._retries >= 1:
                raise failure
            self._retries += 1
            await self.aclose()
            self._lines = None

    async def _read_event(self) -> InternalEvent:
        if self._lines is None:
            self._lines = await self._open()
        while True:
            line = await anext(self._lines)
            if line.strip():
                return cast(InternalEvent, json.loads(line))

    async def _open(self) -> AsyncIterator[str]:
        self._context = self._client.stream("POST", self._url, json=dict(self._payload))
        response = await self._context.__aenter__()
        if response.is_error:
            raise ConnectionError(f"backend HTTP {response.status_code}")
        return response.aiter_lines()

    async def aclose(self) -> None:
        if self._context is not None:
            context, self._context = self._context, None
            await context.__aexit__(None, None, None)


class BackendClient:
    def __init__(
        self, client: httpx.AsyncClient, base_url: str, *, first_event_timeout_seconds: float = 3.0
    ) -> None:
        self._client = client
        self._first_timeout = first_event_timeout_seconds
        self._url = base_url.rstrip("/") + "/internal/rag/stream"

    def open_stream(
        self,
        sku: str,
        question: str,
        history: Sequence[HistoryItem],
        *,
        filters: Filters | None = None,
    ) -> NdjsonBackendStream:
        payload: dict[str, object] = {
            "sku": sku,
            "question": question,
            "history": [{"role": item.role, "content": item.content} for item in history],
        }
        if filters is not None:
            payload.update(
                filters.model_dump(mode="json", exclude_none=True, exclude={"current_product_sku"})
            )
            if filters.budget_max is not None:
                # JSON number at the transport boundary; money arithmetic stays Decimal.
                payload["budget_max"] = float(filters.budget_max)
        return NdjsonBackendStream(self._client, self._url, payload, self._first_timeout)


class ReplayStream:
    """Re-emits a completed turn (same client_request_id) without a new generation."""

    def __init__(self, turn: CompletedTurn) -> None:
        self._events: Iterator[InternalEvent] = iter(_replay_events(turn))

    def __aiter__(self) -> AsyncIterator[InternalEvent]:
        return self

    async def __anext__(self) -> InternalEvent:
        try:
            return next(self._events)
        except StopIteration:
            raise StopAsyncIteration from None

    async def aclose(self) -> None:
        self._events = iter(())


def _replay_events(turn: CompletedTurn) -> list[InternalEvent]:
    events: list[InternalEvent] = []
    if turn.finish_reason in ("fallback", "error"):
        events.append(
            {
                "event": "error",
                "data": {
                    "code": turn.error_code or "LOW_SIMILARITY_FALLBACK",
                    "recoverable": True if turn.recoverable is None else turn.recoverable,
                    "fallback_message": turn.content,
                },
            }
        )
    else:
        events.append({"event": "token", "data": {"delta": turn.content}})
        if turn.citations:
            events.append({"event": "citations", "data": {"citations": list(turn.citations)}})
    if turn.products:
        events.append({"event": "recommendations", "data": {"products": list(turn.products)}})
    end_data: dict[str, object] = {"tokens_used": turn.tokens_used}
    if turn.finish_reason == "error":
        end_data["finish_reason"] = "error"
    if turn.intent is not None:
        end_data["intent"] = turn.intent
    events.append({"event": "end", "data": end_data})
    return events
