"""Chat sessions: TTL, sliding history window, one active turn and client_request_id idempotency.

`SessionStore` is the port used by the routes. `InMemorySessionStore` serves a single
replica without Redis (REDIS_URL unset); `RedisSessionStore` (redis_store.py) is the M02
design of specs/architecture/02, section 4.
"""

import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import Enum
from typing import Protocol

from app.sse.models import CompletedTurn


@dataclass(frozen=True)
class HistoryItem:
    role: str
    content: str
    message_id: str = ""


@dataclass(frozen=True)
class SessionSnapshot:
    """What a route needs from a session; history is chronological and already windowed."""

    session_id: str
    current_product_sku: str | None
    history: tuple[HistoryItem, ...] = ()


class TurnDecision(Enum):
    NEW = "NEW"
    REPLAY = "REPLAY"
    IN_PROGRESS = "IN_PROGRESS"
    CONFLICT = "CONFLICT"


@dataclass(frozen=True)
class TurnStart:
    kind: TurnDecision
    message_id: str = ""
    completed: CompletedTurn | None = None


class SessionStore(Protocol):
    async def create(self, current_product_sku: str | None) -> SessionSnapshot: ...

    async def get(self, session_id: str) -> SessionSnapshot | None:
        """Active session with its TTL renewed, or None when unknown or expired."""
        ...

    async def delete(self, session_id: str) -> bool: ...

    async def begin_turn(
        self, session_id: str, client_request_id: str, payload_hash: str
    ) -> TurnStart:
        """Take the session lock for a new turn, or report replay/conflict/in-progress."""
        ...

    async def complete(
        self, session_id: str, client_request_id: str, question: str, turn: CompletedTurn
    ) -> None:
        """Persist the approved turn once: idempotency record plus the history window."""
        ...

    async def release(self, session_id: str, client_request_id: str) -> None:
        """Free the lock held by this request; an unfinished turn may be retried."""
        ...

    async def ping(self) -> bool: ...


def turn_messages(question: str, turn: CompletedTurn) -> tuple[HistoryItem, HistoryItem]:
    """The user/assistant pair a completed turn adds to the history."""
    return (
        HistoryItem("user", question, str(uuid.uuid4())),
        HistoryItem("assistant", turn.content, turn.message_id),
    )


@dataclass
class _TurnRecord:
    payload_hash: str
    message_id: str
    completed: CompletedTurn | None = None


@dataclass
class _Session:
    session_id: str
    current_product_sku: str | None
    expires_at: float
    history: list[HistoryItem] = field(default_factory=list)
    turns: dict[str, _TurnRecord] = field(default_factory=dict)
    running_request_id: str | None = None


class InMemorySessionStore:
    """Process memory: lost on restart and private to one middle-end replica."""

    def __init__(
        self,
        *,
        ttl_seconds: int,
        history_max_messages: int,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._ttl_seconds = ttl_seconds
        self._history_max_messages = history_max_messages
        self._clock = clock
        self._sessions: dict[str, _Session] = {}

    async def create(self, current_product_sku: str | None) -> SessionSnapshot:
        session = _Session(
            session_id=str(uuid.uuid4()),
            current_product_sku=current_product_sku,
            expires_at=self._clock() + self._ttl_seconds,
        )
        self._sessions[session.session_id] = session
        return self._snapshot(session)

    async def get(self, session_id: str) -> SessionSnapshot | None:
        session = self._active(session_id)
        return self._snapshot(session) if session else None

    async def delete(self, session_id: str) -> bool:
        return self._sessions.pop(session_id, None) is not None

    async def begin_turn(
        self, session_id: str, client_request_id: str, payload_hash: str
    ) -> TurnStart:
        session = self._sessions[session_id]
        record = session.turns.get(client_request_id)
        if record is not None and record.payload_hash != payload_hash:
            return TurnStart(TurnDecision.CONFLICT)
        if record is not None and record.completed is not None:
            return TurnStart(TurnDecision.REPLAY, record.message_id, record.completed)
        if session.running_request_id is not None:
            return TurnStart(TurnDecision.IN_PROGRESS)
        message_id = str(uuid.uuid4())
        session.turns[client_request_id] = _TurnRecord(payload_hash, message_id)
        session.running_request_id = client_request_id
        return TurnStart(TurnDecision.NEW, message_id)

    async def complete(
        self, session_id: str, client_request_id: str, question: str, turn: CompletedTurn
    ) -> None:
        session = self._sessions.get(session_id)
        record = session.turns.get(client_request_id) if session else None
        if session is None or record is None or record.completed is not None:
            return  # replays complete again; history must not grow twice
        record.completed = turn
        session.history = [*session.history, *turn_messages(question, turn)][
            -self._history_max_messages :
        ]

    async def release(self, session_id: str, client_request_id: str) -> None:
        session = self._sessions.get(session_id)
        if session is None:
            return
        if session.running_request_id == client_request_id:
            session.running_request_id = None
        record = session.turns.get(client_request_id)
        if record is not None and record.completed is None:
            # Unfinished turns are forgotten so the browser's reconnect regenerates them.
            del session.turns[client_request_id]

    async def ping(self) -> bool:
        return True

    def _active(self, session_id: str) -> _Session | None:
        session = self._sessions.get(session_id)
        if session is None:
            return None
        if session.expires_at <= self._clock():
            del self._sessions[session_id]
            return None
        session.expires_at = self._clock() + self._ttl_seconds
        return session

    @staticmethod
    def _snapshot(session: _Session) -> SessionSnapshot:
        return SessionSnapshot(
            session.session_id, session.current_product_sku, tuple(session.history)
        )
