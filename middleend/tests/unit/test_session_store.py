"""In-memory sessions: TTL, one turn at a time and idempotency by client_request_id."""

from app.sessions.store import SessionStore, TurnDecision
from app.sse.models import CompletedTurn


def completed(message_id: str, content: str = "Resposta.") -> CompletedTurn:
    return CompletedTurn(
        session_id="s",
        message_id=message_id,
        content=content,
        citations=(),
        products=(),
        finish_reason="stop",
        tokens_used=3,
        intent="TECHNICAL_QA",
        cache_hit=False,
        ttft_ms=10,
        total_latency_ms=20,
    )


class Clock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


def test_sessions_expire_after_ttl_and_can_be_deleted() -> None:
    clock = Clock()
    store = SessionStore(ttl_seconds=60, clock=clock)
    session = store.create("AF-400-220V")
    assert store.get(session.session_id) is session
    clock.now += 61
    assert store.get(session.session_id) is None
    other = store.create(None)
    assert store.delete(other.session_id) and store.get(other.session_id) is None
    assert not store.delete(other.session_id)


def test_new_turn_then_in_progress_then_replay_after_completion() -> None:
    store = SessionStore(ttl_seconds=60)
    session = store.create("AF-400-220V")

    first = store.begin_turn(session, "req-1", "hash-a")
    assert first.kind == TurnDecision.NEW and first.message_id
    assert store.begin_turn(session, "req-1", "hash-a").kind == TurnDecision.IN_PROGRESS
    assert store.begin_turn(session, "req-2", "hash-b").kind == TurnDecision.IN_PROGRESS

    store.complete(session, "req-1", "Pergunta?", completed(first.message_id))
    store.release(session, "req-1")
    replay = store.begin_turn(session, "req-1", "hash-a")
    assert replay.kind == TurnDecision.REPLAY and replay.completed is not None
    assert replay.message_id == first.message_id
    assert store.begin_turn(session, "req-1", "hash-other").kind == TurnDecision.CONFLICT


def test_completion_is_idempotent_and_feeds_history() -> None:
    store = SessionStore(ttl_seconds=60)
    session = store.create("AF-400-220V")
    turn = store.begin_turn(session, "req-1", "hash-a")
    store.complete(session, "req-1", "Pergunta?", completed(turn.message_id))
    store.complete(session, "req-1", "Pergunta?", completed(turn.message_id))
    assert [(item.role, item.content) for item in session.history] == [
        ("user", "Pergunta?"),
        ("assistant", "Resposta."),
    ]


def test_released_unfinished_turn_can_be_retried_with_the_same_id() -> None:
    store = SessionStore(ttl_seconds=60)
    session = store.create("AF-400-220V")
    store.begin_turn(session, "req-1", "hash-a")
    store.release(session, "req-1")
    assert store.begin_turn(session, "req-1", "hash-a").kind == TurnDecision.NEW
