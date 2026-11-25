"""Session store contract (M02): TTL, history window, one turn at a time, idempotency.

Every contract test runs on the in-memory store and, when TEST_REDIS_URL is set, on Redis.
"""

import asyncio
import os
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager

import pytest
from app.sessions.redis_store import RedisSessionStore
from app.sessions.store import InMemorySessionStore, SessionStore, TurnDecision, TurnLost
from app.sse.models import CompletedTurn
from redis.asyncio import Redis

REDIS_URL = os.environ.get("TEST_REDIS_URL", "")
TTL_SECONDS = 1800
HISTORY_WINDOW = 10
LOCK_TTL_SECONDS = 60

STORES = [
    "memory",
    pytest.param(
        "redis", marks=pytest.mark.skipif(not REDIS_URL, reason="TEST_REDIS_URL not set")
    ),
]


def completed(message_id: str, content: str = "Resposta.") -> CompletedTurn:
    return CompletedTurn(
        session_id="s",
        message_id=message_id,
        content=content,
        citations=(
            {
                "chunk_id": "c-14",
                "sku": "AF-400-220V",
                "manual_title": "Manual Airfryer SmartChef 4L",
                "page_number": 14,
                "similarity_score": 0.9,
                "excerpt": "Formas de alumínio.",
            },
        ),
        products=(),
        finish_reason="stop",
        tokens_used=3,
        intent="TECHNICAL_QA",
        cache_hit=False,
        ttft_ms=10,
        total_latency_ms=20,
    )


@asynccontextmanager
async def redis_client() -> AsyncIterator[Redis]:
    client = Redis.from_url(REDIS_URL, decode_responses=True)
    try:
        yield client
    finally:
        await client.aclose()


@asynccontextmanager
async def open_store(kind: str) -> AsyncIterator[SessionStore]:
    if kind == "memory":
        yield InMemorySessionStore(ttl_seconds=TTL_SECONDS, history_max_messages=HISTORY_WINDOW)
        return
    async with redis_client() as client:
        yield RedisSessionStore(
            client,
            ttl_seconds=TTL_SECONDS,
            history_max_messages=HISTORY_WINDOW,
            lock_ttl_seconds=LOCK_TTL_SECONDS,
        )


def run(kind: str, scenario: Callable[[SessionStore], Awaitable[None]]) -> None:
    async def with_store() -> None:
        async with open_store(kind) as store:
            await scenario(store)

    asyncio.run(with_store())


async def finish_turn(store: SessionStore, session_id: str, request_id: str, text: str) -> str:
    turn = await store.begin_turn(session_id, request_id, f"hash-{request_id}")
    assert turn.kind == TurnDecision.NEW
    await store.complete(
        session_id, request_id, turn.lock_token, f"Pergunta {text}?", completed(turn.message_id, text)
    )
    await store.release(session_id, request_id, turn.lock_token)
    return turn.message_id


@pytest.mark.parametrize("kind", STORES)
def test_session_is_created_read_and_deleted(kind: str) -> None:
    async def scenario(store: SessionStore) -> None:
        created = await store.create("AF-400-220V")
        found = await store.get(created.session_id)
        assert found is not None and found.current_product_sku == "AF-400-220V"
        assert found.history == ()

        without_product = await store.create(None)
        assert (await store.get(without_product.session_id)).current_product_sku is None  # type: ignore[union-attr]

        assert await store.delete(created.session_id)
        assert await store.get(created.session_id) is None
        assert not await store.delete(created.session_id)
        assert await store.get("00000000-0000-0000-0000-000000000000") is None

    run(kind, scenario)


@pytest.mark.parametrize("kind", STORES)
def test_new_turn_then_in_progress_then_replay_after_completion(kind: str) -> None:
    async def scenario(store: SessionStore) -> None:
        session_id = (await store.create("AF-400-220V")).session_id

        first = await store.begin_turn(session_id, "req-1", "hash-a")
        assert first.kind == TurnDecision.NEW and first.message_id
        assert (await store.begin_turn(session_id, "req-1", "hash-a")).kind == TurnDecision.IN_PROGRESS
        assert (await store.begin_turn(session_id, "req-2", "hash-b")).kind == TurnDecision.IN_PROGRESS

        await store.complete(
            session_id, "req-1", first.lock_token, "Pergunta?", completed(first.message_id)
        )
        await store.release(session_id, "req-1", first.lock_token)
        replay = await store.begin_turn(session_id, "req-1", "hash-a")
        assert replay.kind == TurnDecision.REPLAY and replay.message_id == first.message_id
        assert replay.completed == completed(first.message_id)
        assert (await store.begin_turn(session_id, "req-1", "hash-other")).kind == TurnDecision.CONFLICT
        assert (await store.begin_turn(session_id, "req-2", "hash-b")).kind == TurnDecision.NEW

    run(kind, scenario)


@pytest.mark.parametrize("kind", STORES)
def test_completion_is_idempotent_and_feeds_history_in_order(kind: str) -> None:
    async def scenario(store: SessionStore) -> None:
        session_id = (await store.create("AF-400-220V")).session_id
        turn = await store.begin_turn(session_id, "req-1", "hash-a")
        for _ in range(2):
            await store.complete(
                session_id, "req-1", turn.lock_token, "Pergunta?", completed(turn.message_id)
            )

        history = (await store.get(session_id)).history  # type: ignore[union-attr]
        assert [(item.role, item.content) for item in history] == [
            ("user", "Pergunta?"),
            ("assistant", "Resposta."),
        ]
        assert history[1].message_id == turn.message_id and history[0].message_id

    run(kind, scenario)


@pytest.mark.parametrize("kind", STORES)
def test_history_keeps_only_the_last_ten_messages(kind: str) -> None:
    async def scenario(store: SessionStore) -> None:
        session_id = (await store.create("AF-400-220V")).session_id
        for number in range(7):  # 14 messages
            await finish_turn(store, session_id, f"req-{number}", str(number))

        history = (await store.get(session_id)).history  # type: ignore[union-attr]
        assert len(history) == HISTORY_WINDOW
        assert history[0].content == "Pergunta 2?" and history[-1].content == "6"

    run(kind, scenario)


@pytest.mark.parametrize("kind", STORES)
def test_released_unfinished_turn_replays_failure_and_allows_a_new_explicit_id(kind: str) -> None:
    async def scenario(store: SessionStore) -> None:
        session_id = (await store.create("AF-400-220V")).session_id
        turn = await store.begin_turn(session_id, "req-1", "hash-a")
        await store.release(session_id, "req-1", turn.lock_token)
        assert (await store.begin_turn(session_id, "req-1", "hash-a")).kind == TurnDecision.REPLAY
        assert (await store.begin_turn(session_id, "req-2", "hash-b")).kind == TurnDecision.NEW

    run(kind, scenario)


@pytest.mark.parametrize("kind", STORES)
def test_only_the_lock_owner_releases_or_completes_the_turn(kind: str) -> None:
    async def scenario(store: SessionStore) -> None:
        session_id = (await store.create("AF-400-220V")).session_id
        turn = await store.begin_turn(session_id, "req-1", "hash-a")
        assert turn.lock_token

        # Same client_request_id, but not the token of this acquisition (a stale owner).
        await store.release(session_id, "req-1", "stale-token")
        with pytest.raises(TurnLost):
            await store.complete(session_id, "req-1", "stale-token", "Pergunta?", completed("stale"))
        assert (await store.begin_turn(session_id, "req-2", "hash-b")).kind == TurnDecision.IN_PROGRESS
        assert (await store.get(session_id)).history == ()  # type: ignore[union-attr]

        await store.complete(
            session_id, "req-1", turn.lock_token, "Pergunta?", completed(turn.message_id)
        )
        assert len((await store.get(session_id)).history) == 2  # type: ignore[union-attr]
        assert await store.ping()

    run(kind, scenario)


@pytest.mark.parametrize("kind", STORES)
def test_simultaneous_turns_let_exactly_one_in(kind: str) -> None:
    async def scenario(store: SessionStore) -> None:
        session_id = (await store.create("AF-400-220V")).session_id
        starts = await asyncio.gather(
            *(store.begin_turn(session_id, f"req-{number}", "hash") for number in range(20))
        )
        assert sorted(start.kind.value for start in starts) == ["IN_PROGRESS"] * 19 + ["NEW"]

        same_id = (await store.create("AF-400-220V")).session_id
        retries = await asyncio.gather(
            *(store.begin_turn(same_id, "req-1", "hash") for _ in range(20))
        )
        assert sorted(start.kind.value for start in retries) == ["IN_PROGRESS"] * 19 + ["NEW"]

    run(kind, scenario)


def test_in_memory_sessions_expire_after_ttl() -> None:
    now = [1000.0]
    store = InMemorySessionStore(ttl_seconds=60, history_max_messages=10, clock=lambda: now[0])

    async def scenario() -> None:
        session_id = (await store.create("AF-400-220V")).session_id
        now[0] += 59
        assert await store.get(session_id) is not None  # renews the TTL
        now[0] += 59
        assert await store.get(session_id) is not None
        now[0] += 61
        assert await store.get(session_id) is None

    asyncio.run(scenario())


@pytest.mark.skipif(not REDIS_URL, reason="TEST_REDIS_URL not set")
def test_redis_keys_follow_the_spec_ttls_and_delete_leaves_nothing() -> None:
    async def scenario() -> None:
        async with redis_client() as client:
            store = RedisSessionStore(
                client,
                ttl_seconds=TTL_SECONDS,
                history_max_messages=HISTORY_WINDOW,
                lock_ttl_seconds=LOCK_TTL_SECONDS,
            )
            session_id = (await store.create("AF-400-220V")).session_id
            turn = await store.begin_turn(session_id, "req-1", "hash-a")

            assert await client.hget(f"session:{session_id}:state", "active_sku") == "AF-400-220V"
            assert 0 < await client.ttl(f"session:{session_id}:state") <= TTL_SECONDS
            assert 0 < await client.ttl(f"session:{session_id}:turns") <= TTL_SECONDS
            assert await client.get(f"session:{session_id}:lock") == turn.lock_token
            assert 0 < await client.ttl(f"session:{session_id}:lock") <= LOCK_TTL_SECONDS

            await store.complete(session_id, "req-1", turn.lock_token, "Pergunta?", completed("m-1"))
            assert await client.llen(f"session:{session_id}:history") == 2
            assert 0 < await client.ttl(f"session:{session_id}:history") <= TTL_SECONDS

            assert await store.delete(session_id)
            assert await client.keys(f"session:{session_id}:*") == []

    asyncio.run(scenario())


@pytest.mark.skipif(not REDIS_URL, reason="TEST_REDIS_URL not set")
def test_redis_turn_outliving_its_lock_cannot_touch_the_retry() -> None:
    async def scenario() -> None:
        async with redis_client() as client:
            store = RedisSessionStore(
                client, ttl_seconds=TTL_SECONDS, history_max_messages=HISTORY_WINDOW, lock_ttl_seconds=1
            )
            session_id = (await store.create("AF-400-220V")).session_id
            slow = await store.begin_turn(session_id, "req-1", "hash-a")
            await asyncio.sleep(1.2)  # the lock expires while the slow turn still runs
            assert (await store.begin_turn(session_id, "req-1", "hash-a")).kind == TurnDecision.REPLAY
            retry = await store.begin_turn(session_id, "req-fresh", "hash-fresh")
            assert retry.kind == TurnDecision.NEW and retry.lock_token != slow.lock_token

            with pytest.raises(TurnLost):
                await store.complete(session_id, "req-1", slow.lock_token, "Pergunta?", completed("slow"))
            await store.release(session_id, "req-1", slow.lock_token)
            assert (await store.get(session_id)).history == ()  # type: ignore[union-attr]
            assert (await store.begin_turn(session_id, "req-2", "hash-b")).kind == TurnDecision.IN_PROGRESS

            await store.complete(
                session_id, "req-fresh", retry.lock_token, "Pergunta?", completed(retry.message_id)
            )
            history = (await store.get(session_id)).history  # type: ignore[union-attr]
            assert [item.message_id for item in history][1:] == [retry.message_id]

    asyncio.run(scenario())


@pytest.mark.skipif(not REDIS_URL, reason="TEST_REDIS_URL not set")
def test_redis_release_of_a_failed_turn_keeps_the_retry_that_raced_it() -> None:
    """The retry lands right after the failed turn drops the lock (same client_request_id)."""

    async def scenario() -> None:
        async with redis_client() as client:
            store = RedisSessionStore(
                client,
                ttl_seconds=TTL_SECONDS,
                history_max_messages=HISTORY_WINDOW,
                lock_ttl_seconds=LOCK_TTL_SECONDS,
            )
            session_id = (await store.create("AF-400-220V")).session_id
            failed = await store.begin_turn(session_id, "req-1", "hash-a")
            retries = []
            unlock = client.eval

            async def unlock_then_retry(*args: object) -> object:
                unlocked = await unlock(*args)  # type: ignore[arg-type]
                client.eval = unlock  # type: ignore[method-assign]
                retries.append(await store.begin_turn(session_id, "req-1", "hash-a"))
                return unlocked

            client.eval = unlock_then_retry  # type: ignore[method-assign,assignment]
            await store.release(session_id, "req-1", failed.lock_token)

            retry = retries[0]
            assert retry.kind == TurnDecision.REPLAY
            assert retry.message_id == failed.message_id
            assert retry.completed is not None and retry.completed.finish_reason == "error"
            assert (await store.get(session_id)).history == ()

    asyncio.run(scenario())


@pytest.mark.skipif(not REDIS_URL, reason="TEST_REDIS_URL not set")
def test_redis_retry_racing_the_completion_replays_instead_of_regenerating() -> None:
    """The retry reads the unfinished record, then the running turn completes and unlocks."""

    async def scenario() -> None:
        async with redis_client() as client:
            store = RedisSessionStore(
                client,
                ttl_seconds=TTL_SECONDS,
                history_max_messages=HISTORY_WINDOW,
                lock_ttl_seconds=LOCK_TTL_SECONDS,
            )
            session_id = (await store.create("AF-400-220V")).session_id
            running = await store.begin_turn(session_id, "req-1", "hash-a")
            async def finish() -> None:
                await store.complete(session_id, "req-1", running.lock_token,
                                     "Pergunta?", completed(running.message_id))
                await store.release(session_id, "req-1", running.lock_token)

            _, raced = await asyncio.gather(finish(), store.begin_turn(session_id, "req-1", "hash-a"))
            assert raced.kind in (TurnDecision.IN_PROGRESS, TurnDecision.REPLAY)
            retry = await store.begin_turn(session_id, "req-1", "hash-a")

            assert retry.kind == TurnDecision.REPLAY and retry.message_id == running.message_id
            assert len((await store.get(session_id)).history) == 2  # type: ignore[union-attr]
            # the lock taken on the way to the replay was given back
            assert (await store.begin_turn(session_id, "req-2", "hash-b")).kind == TurnDecision.NEW

    asyncio.run(scenario())


@pytest.mark.skipif(not REDIS_URL, reason="TEST_REDIS_URL not set")
def test_redis_ping_reports_an_unreachable_server() -> None:
    async def scenario() -> bool:
        client = Redis.from_url("redis://127.0.0.1:1/0", decode_responses=True, socket_connect_timeout=1)
        try:
            store = RedisSessionStore(
                client, ttl_seconds=1, history_max_messages=1, lock_ttl_seconds=1
            )
            return await store.ping()
        finally:
            await client.aclose()

    assert asyncio.run(scenario()) is False


@pytest.mark.parametrize("kind", STORES)
def test_deleted_session_cannot_acquire_a_new_turn(kind: str) -> None:
    async def scenario(store: SessionStore) -> None:
        session_id = (await store.create("AF-400-220V")).session_id
        await store.delete(session_id)
        assert (await store.begin_turn(session_id, "late", "hash")).kind.value == "NOT_FOUND"
    run(kind, scenario)


@pytest.mark.parametrize("kind", STORES)
def test_abandoned_request_is_terminal_and_never_regenerated(kind: str) -> None:
    async def scenario(store: SessionStore) -> None:
        session_id = (await store.create("AF-400-220V")).session_id
        first = await store.begin_turn(session_id, "req-1", "hash")
        await store.release(session_id, "req-1", first.lock_token)
        retry = await store.begin_turn(session_id, "req-1", "hash")
        assert retry.kind == TurnDecision.REPLAY
        assert retry.completed is not None and retry.completed.finish_reason == "error"
        assert (await store.get(session_id)).history == ()
    run(kind, scenario)


@pytest.mark.parametrize("kind", STORES)
def test_completed_turn_persists_recommended_skus_in_history(kind: str) -> None:
    card = {
        "sku": "PC-VX3-BIV",
        "name": "PC Gamer Vortex X3",
        "price": 3499.0,
        "stock_quantity": 7,
        "voltage": "BIVOLT",
        "image_url": "/images/pc-vx3-biv.svg",
        "marketplace": "LOJA_OFICIAL",
        "checkout_url": "https://example.com/pc-vx3",
        "recommendation_type": "OPTION",
        "badge_label": "Opção",
        "justification": "RTX 3050 6 GB, 16 GB de RAM.",
    }

    async def scenario(store: SessionStore) -> None:
        session_id = (await store.create(None)).session_id
        turn = await store.begin_turn(session_id, "req-1", "hash-1")
        with_cards = CompletedTurn(
            session_id=session_id,
            message_id=turn.message_id,
            content="Encontrei 1 opção.",
            citations=(),
            products=(card,),  # type: ignore[arg-type]
            finish_reason="stop",
            tokens_used=5,
            intent="PURCHASE_INTENT",
            cache_hit=False,
            ttft_ms=10,
            total_latency_ms=20,
        )
        await store.complete(session_id, "req-1", turn.lock_token, "Quero um PC", with_cards)
        await store.release(session_id, "req-1", turn.lock_token)

        snapshot = await store.get(session_id)
        assert snapshot is not None
        assert [item.recommended_skus for item in snapshot.history] == [(), ("PC-VX3-BIV",)]

    run(kind, scenario)


def test_legacy_redis_history_entry_without_skus_still_reads() -> None:
    from app.sessions.redis_store import _snapshot

    legacy_user = '{"id": "m-user", "role": "user", "content": "Oi"}'
    legacy_assistant = '{"id": "m-ast", "role": "assistant", "content": "Olá"}'
    snapshot = _snapshot(
        "s-1",
        {"sku": "", "state": "IDLE", "history": [legacy_assistant, legacy_user]},
    )
    assert [(item.role, item.content, item.recommended_skus) for item in snapshot.history] == [
        ("user", "Oi", ()),
        ("assistant", "Olá", ()),
    ]
