"""Chat sessions: TTL, sliding history window, one active turn and client_request_id idempotency.

`SessionStore` is the port used by the routes. `InMemorySessionStore` serves a single
replica without Redis (REDIS_URL unset); Redis-only is also a development adapter.
Production uses PostgresSessionStore for durable sessions, turns and messages.
"""

import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import Enum
from typing import Literal, Protocol

from app.sse.models import CompletedTurn

TurnState = Literal[
    "IDLE",
    "VALIDATING_CACHE",
    "STREAMING_TOKENS",
    "EMITTING_CARDS_AND_CITATIONS",
    "ERROR_CONTINGENCY",
]


class TurnLost(RuntimeError):
    """The session/lease was lost; no success may be acknowledged."""


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
    state: TurnState = "IDLE"


class TurnDecision(Enum):
    NEW = "NEW"
    REPLAY = "REPLAY"
    IN_PROGRESS = "IN_PROGRESS"
    CONFLICT = "CONFLICT"
    NOT_FOUND = "NOT_FOUND"
    EXPIRED = "EXPIRED"


@dataclass(frozen=True)
class TurnStart:
    kind: TurnDecision
    message_id: str = ""
    completed: CompletedTurn | None = None
    # Set only for NEW: proves ownership of this acquisition of the session lock, so a
    # stale owner with the same client_request_id cannot complete or release the retry.
    lock_token: str = ""
    snapshot: SessionSnapshot | None = None


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
        self,
        session_id: str,
        client_request_id: str,
        lock_token: str,
        question: str,
        turn: CompletedTurn,
    ) -> None:
        """Persist the approved turn once: idempotency record plus the history window.

        Writes nothing unless `lock_token` still owns the session lock.
        """
        ...

    async def release(self, session_id: str, client_request_id: str, lock_token: str) -> None:
        """Free the lock if `lock_token` still owns it; its unfinished turn becomes a terminal failure."""
        ...

    async def renew(self, session_id: str, client_request_id: str, lock_token: str) -> bool: ...

    async def transition(self, session_id: str, lock_token: str, state: TurnState) -> None: ...

    async def ping(self) -> bool: ...

    async def database_ping(self) -> bool | None: ...


def abandoned_turn(session_id: str, message_id: str) -> CompletedTurn:
    return CompletedTurn(
        session_id,
        message_id,
        "A resposta foi interrompida. Envie uma nova pergunta para continuar.",
        (),
        (),
        "error",
        0,
        None,
        False,
        0,
        0,
        "INTERNAL_ERROR",
        True,
    )


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
    running_lock_token: str | None = None
    running_request_id: str | None = None
    lock_expires_at: float = 0
    state: TurnState = "IDLE"


class InMemorySessionStore:
    """Process memory: lost on restart and private to one middle-end replica."""

    def __init__(
        self,
        *,
        ttl_seconds: int,
        history_max_messages: int,
        clock: Callable[[], float] = time.monotonic,
        lock_ttl_seconds: int = 60,
    ) -> None:
        self._ttl_seconds = ttl_seconds
        self._history_max_messages = history_max_messages
        self._clock = clock
        self._lock_ttl_seconds = lock_ttl_seconds
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
        session = self._active(session_id)
        if session is None:
            return TurnStart(TurnDecision.NOT_FOUND)
        if session.running_lock_token and session.lock_expires_at <= self._clock():
            await self.release(
                session_id, session.running_request_id or "", session.running_lock_token
            )
        record = session.turns.get(client_request_id)
        if record is not None and record.payload_hash != payload_hash:
            return TurnStart(TurnDecision.CONFLICT)
        if record is not None and record.completed is not None:
            return TurnStart(TurnDecision.REPLAY, record.message_id, record.completed)
        if session.running_lock_token is not None:
            return TurnStart(TurnDecision.IN_PROGRESS)
        message_id, lock_token = str(uuid.uuid4()), str(uuid.uuid4())
        session.turns[client_request_id] = _TurnRecord(payload_hash, message_id)
        session.running_lock_token = lock_token
        session.running_request_id = client_request_id
        session.lock_expires_at = self._clock() + self._lock_ttl_seconds
        session.state = "VALIDATING_CACHE"
        return TurnStart(
            TurnDecision.NEW, message_id, lock_token=lock_token, snapshot=self._snapshot(session)
        )

    async def complete(
        self,
        session_id: str,
        client_request_id: str,
        lock_token: str,
        question: str,
        turn: CompletedTurn,
    ) -> None:
        if not lock_token:
            return
        session = self._active(session_id)
        if (
            session is None
            or session.running_lock_token != lock_token
            or session.lock_expires_at <= self._clock()
        ):
            raise TurnLost("Session lease lost")
        record = session.turns.get(client_request_id)
        if record is None or record.completed is not None:
            return
        record.completed = turn
        if turn.finish_reason == "error":
            return
        session.history = [*session.history, *turn_messages(question, turn)][
            -self._history_max_messages :
        ]

    async def release(self, session_id: str, client_request_id: str, lock_token: str) -> None:
        session = self._sessions.get(session_id)
        if session is None or session.running_lock_token != lock_token:
            return
        session.running_lock_token = None
        session.running_request_id = None
        session.state = "IDLE"
        record = session.turns.get(client_request_id)
        if record is not None and record.completed is None:
            record.completed = abandoned_turn(session_id, record.message_id)

    async def renew(self, session_id: str, client_request_id: str, lock_token: str) -> bool:
        session = self._active(session_id)
        if (
            session is None
            or session.running_lock_token != lock_token
            or session.lock_expires_at <= self._clock()
        ):
            return False
        session.lock_expires_at = self._clock() + self._lock_ttl_seconds
        return True

    async def transition(self, session_id: str, lock_token: str, state: TurnState) -> None:
        session = self._active(session_id)
        if (
            session is None
            or session.running_lock_token != lock_token
            or session.lock_expires_at <= self._clock()
        ):
            raise TurnLost("Session lease lost")
        session.state = state

    async def ping(self) -> bool:
        return True

    async def database_ping(self) -> bool | None:
        return None

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
            session.session_id, session.current_product_sku, tuple(session.history), session.state
        )
