"""Chat sessions with TTL, one active turn per session and client_request_id idempotency.

shortcut: in-process memory (lost on restart, single replica). Upgrade to the
Redis/PostgreSQL design in specs/architecture/02 (chat_sessions, chat_turn_requests)
before running more than one middle-end instance.
"""

import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import Enum

from app.sse.models import CompletedTurn


@dataclass(frozen=True)
class HistoryItem:
    role: str
    content: str


@dataclass
class _TurnRecord:
    payload_hash: str
    message_id: str
    completed: CompletedTurn | None = None


@dataclass
class Session:
    session_id: str
    current_product_sku: str | None
    expires_at: float
    history: list[HistoryItem] = field(default_factory=list)
    turns: dict[str, _TurnRecord] = field(default_factory=dict)
    running_request_id: str | None = None


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


class SessionStore:
    def __init__(self, *, ttl_seconds: int, clock: Callable[[], float] = time.monotonic) -> None:
        self._ttl_seconds = ttl_seconds
        self._clock = clock
        self._sessions: dict[str, Session] = {}

    def create(self, current_product_sku: str | None) -> Session:
        session = Session(
            session_id=str(uuid.uuid4()),
            current_product_sku=current_product_sku,
            expires_at=self._clock() + self._ttl_seconds,
        )
        self._sessions[session.session_id] = session
        return session

    def get(self, session_id: str) -> Session | None:
        session = self._sessions.get(session_id)
        if session is None:
            return None
        if session.expires_at <= self._clock():
            del self._sessions[session_id]
            return None
        session.expires_at = self._clock() + self._ttl_seconds
        return session

    def delete(self, session_id: str) -> bool:
        return self._sessions.pop(session_id, None) is not None

    def begin_turn(self, session: Session, client_request_id: str, payload_hash: str) -> TurnStart:
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

    def complete(
        self, session: Session, client_request_id: str, question: str, turn: CompletedTurn
    ) -> None:
        record = session.turns.get(client_request_id)
        if record is None or record.completed is not None:
            return  # replays complete again; history must not grow twice
        record.completed = turn
        session.history += [HistoryItem("user", question), HistoryItem("assistant", turn.content)]

    def release(self, session: Session, client_request_id: str) -> None:
        if session.running_request_id == client_request_id:
            session.running_request_id = None
        record = session.turns.get(client_request_id)
        if record is not None and record.completed is None:
            # Unfinished turns are forgotten so the browser's reconnect regenerates them.
            del session.turns[client_request_id]
