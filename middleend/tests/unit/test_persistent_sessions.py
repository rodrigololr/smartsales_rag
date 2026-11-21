"""Production M02 against PostgreSQL and Redis: identity, recovery, fencing and retention."""

import asyncio
import dataclasses
import os
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import pytest
from app.sessions.cache import SessionCache
from app.sessions.postgres_store import PostgresSessionStore
from app.sessions.store import TurnDecision, TurnLost
from app.sse.models import CompletedTurn
from psycopg import AsyncConnection
from redis.asyncio import Redis

DATABASE_URL = os.getenv("TEST_DATABASE_URL", "")
REDIS_URL = os.getenv("TEST_REDIS_URL", "")
pytestmark = pytest.mark.skipif(
    not DATABASE_URL or not REDIS_URL, reason="TEST_DATABASE_URL and TEST_REDIS_URL required"
)


@asynccontextmanager
async def stores() -> AsyncIterator[tuple[PostgresSessionStore, PostgresSessionStore, Redis]]:
    redis = Redis.from_url(REDIS_URL, decode_responses=True)
    cache = SessionCache(redis, 1800, 60)
    first = PostgresSessionStore(
        DATABASE_URL, cache, ttl_seconds=1800, history_max_messages=10, lock_ttl_seconds=60
    )
    second = PostgresSessionStore(
        DATABASE_URL, cache, ttl_seconds=1800, history_max_messages=10, lock_ttl_seconds=60
    )
    try:
        await first.initialize()
        yield first, second, redis
    finally:
        await redis.aclose()


def terminal(session: str, message: str, *, failure: bool = False) -> CompletedTurn:
    return CompletedTurn(
        session,
        message,
        "Falha segura." if failure else "Opera em 220V.",
        (),
        (),
        "error" if failure else "stop",
        3,
        "TECHNICAL_QA",
        False,
        5,
        10,
        "LLM_UNAVAILABLE" if failure else None,
        True if failure else None,
    )


async def execute(sql: str, params: tuple[object, ...] = ()) -> None:
    async with await AsyncConnection.connect(DATABASE_URL) as connection:
        await connection.execute(sql, params)


def test_sql_completion_survives_loss_of_all_redis_keys_and_app_restart() -> None:
    async def scenario() -> None:
        async with stores() as (first, second, redis):
            session = (await first.create("AF-400-220V")).session_id
            rid = str(uuid.uuid4())
            turn = await first.begin_turn(session, rid, "hash")
            result = terminal(session, turn.message_id)
            await first.complete(session, rid, turn.lock_token, "Voltagem?", result)
            await redis.delete(*SessionCache.keys(session))
            restored = await second.get(session)
            assert restored and [row.content for row in restored.history] == [
                "Voltagem?",
                result.content,
            ]
            assert await redis.llen(f"session:{session}:history") == 2
            replay = await second.begin_turn(session, rid, "hash")
            assert replay.kind == TurnDecision.REPLAY and replay.completed == result
            assert (await second.begin_turn(session, rid, "other")).kind == TurnDecision.CONFLICT
            await second.delete(session)

    asyncio.run(scenario())


def test_only_one_of_twenty_replicas_can_reserve_a_session() -> None:
    async def scenario() -> None:
        async with stores() as (first, second, _):
            session = (await first.create("AF-400-220V")).session_id
            turns = await asyncio.gather(
                *(
                    store.begin_turn(session, str(uuid.uuid4()), "hash")
                    for store in [first, second] * 10
                )
            )
            assert sorted(turn.kind.value for turn in turns) == ["IN_PROGRESS"] * 19 + ["NEW"]
            await first.delete(session)

    asyncio.run(scenario())


def test_same_request_on_concurrent_replicas_is_reserved_once() -> None:
    async def scenario() -> None:
        async with stores() as (first, second, _):
            session = (await first.create(None)).session_id
            rid = str(uuid.uuid4())
            turns = await asyncio.gather(
                *(store.begin_turn(session, rid, "hash") for store in [first, second] * 5)
            )
            assert sorted(turn.kind.value for turn in turns) == ["IN_PROGRESS"] * 9 + ["NEW"]
            await first.delete(session)

    asyncio.run(scenario())


def test_orphan_is_failed_and_replayed_without_reusing_its_generation() -> None:
    async def scenario() -> None:
        async with stores() as (first, second, redis):
            session = (await first.create("AF-400-220V")).session_id
            rid = str(uuid.uuid4())
            owner = await first.begin_turn(session, rid, "hash")
            await execute(
                "UPDATE chat_turn_requests SET lease_expires_at=NOW()-INTERVAL '1 second' "
                "WHERE session_id=%s",
                (session,),
            )
            await redis.delete(f"session:{session}:lock")
            retry = await second.begin_turn(session, rid, "hash")
            assert retry.kind == TurnDecision.REPLAY
            assert retry.completed and retry.completed.finish_reason == "error"
            assert retry.message_id == owner.message_id
            fresh_id = str(uuid.uuid4())
            fresh = await second.begin_turn(session, fresh_id, "new")
            assert fresh.kind == TurnDecision.NEW
            with pytest.raises(TurnLost):
                await first.complete(
                    session, rid, owner.lock_token, "Old", terminal(session, owner.message_id)
                )
            await first.release(session, rid, owner.lock_token)
            assert await second.renew(session, fresh_id, fresh.lock_token)
            await second.delete(session)

    asyncio.run(scenario())


def test_completion_after_deleted_session_is_rejected_and_cannot_resurrect_it() -> None:
    async def scenario() -> None:
        async with stores() as (first, second, redis):
            session = (await first.create(None)).session_id
            rid = str(uuid.uuid4())
            turn = await first.begin_turn(session, rid, "hash")
            assert await second.delete(session)
            with pytest.raises(TurnLost):
                await first.complete(
                    session, rid, turn.lock_token, "Question", terminal(session, turn.message_id)
                )
            assert (
                await first.begin_turn(session, str(uuid.uuid4()), "hash")
            ).kind == TurnDecision.NOT_FOUND
            assert await second.get(session) is None
            assert await redis.keys(f"session:{session}:*") == []

    asyncio.run(scenario())


def test_duplicate_completion_does_not_duplicate_history_or_metrics() -> None:
    async def scenario() -> None:
        async with stores() as (first, second, _):
            session = (await first.create(None)).session_id
            rid = str(uuid.uuid4())
            turn = await first.begin_turn(session, rid, "hash")
            result = terminal(session, turn.message_id)
            for _ in range(2):
                await first.complete(session, rid, turn.lock_token, "Pergunta?", result)
            await first.release(session, rid, turn.lock_token)
            assert len((await second.get(session)).history) == 2
            assert (await second.begin_turn(session, rid, "hash")).completed == result
            await second.delete(session)

    asyncio.run(scenario())


def test_failed_snapshot_is_replayed_but_excluded_from_history() -> None:
    async def scenario() -> None:
        async with stores() as (first, second, _):
            session = (await first.create(None)).session_id
            rid = str(uuid.uuid4())
            turn = await first.begin_turn(session, rid, "hash")
            result = terminal(session, turn.message_id, failure=True)
            await first.complete(session, rid, turn.lock_token, "Pergunta?", result)
            await first.release(session, rid, turn.lock_token)
            assert (await second.begin_turn(session, rid, "hash")).completed == result
            assert (await second.get(session)).history == ()
            await second.delete(session)

    asyncio.run(scenario())


def test_payload_expires_to_tombstone_without_losing_session_history() -> None:
    async def scenario() -> None:
        async with stores() as (first, second, redis):
            session = (await first.create(None)).session_id
            rid = str(uuid.uuid4())
            turn = await first.begin_turn(session, rid, "hash")
            await first.complete(
                session, rid, turn.lock_token, "Pergunta?", terminal(session, turn.message_id)
            )
            await first.release(session, rid, turn.lock_token)
            await execute(
                "UPDATE chat_turn_requests SET expires_at=NOW()-INTERVAL '1 second' WHERE session_id=%s",
                (session,),
            )
            await first.maintain()
            await redis.delete(*SessionCache.keys(session))
            assert (await second.begin_turn(session, rid, "hash")).kind == TurnDecision.EXPIRED
            assert (await second.begin_turn(session, rid, "other")).kind == TurnDecision.CONFLICT
            assert len((await second.get(session)).history) == 2
            await second.delete(session)

    asyncio.run(scenario())


def test_inactivity_expires_session_even_if_old_redis_state_survives() -> None:
    async def scenario() -> None:
        async with stores() as (first, second, redis):
            session = (await first.create(None)).session_id
            await execute(
                "UPDATE chat_sessions SET last_active_at=NOW()-INTERVAL '31 minutes' WHERE id=%s",
                (session,),
            )
            assert await second.get(session) is None
            assert await redis.keys(f"session:{session}:*") == []

    asyncio.run(scenario())


def test_maximum_retention_cascades_messages_and_tombstones() -> None:
    async def scenario() -> None:
        async with stores() as (first, second, _):
            session = (await first.create(None)).session_id
            rid = str(uuid.uuid4())
            turn = await first.begin_turn(session, rid, "hash")
            await first.complete(
                session, rid, turn.lock_token, "Question", terminal(session, turn.message_id)
            )
            await first.release(session, rid, turn.lock_token)
            await execute(
                "UPDATE chat_sessions SET created_at=NOW()-INTERVAL '91 days' WHERE id=%s",
                (session,),
            )
            await first.maintain()
            assert await second.get(session) is None
            async with await AsyncConnection.connect(DATABASE_URL) as connection:
                for table, key in (
                    ("chat_sessions", "id"),
                    ("chat_messages", "session_id"),
                    ("chat_turn_requests", "session_id"),
                ):
                    cursor = await connection.execute(
                        f"SELECT count(*) FROM {table} WHERE {key}=%s", (session,)
                    )
                    assert (await cursor.fetchone())[0] == 0

    asyncio.run(scenario())


def test_sql_history_window_is_the_latest_five_complete_pairs() -> None:
    async def scenario() -> None:
        async with stores() as (first, second, redis):
            session = (await first.create(None)).session_id
            for index in range(7):
                rid = str(uuid.uuid4())
                turn = await first.begin_turn(session, rid, "hash")
                result = dataclasses.replace(
                    terminal(session, turn.message_id), content=f"Answer {index}"
                )
                await first.complete(session, rid, turn.lock_token, f"Question {index}", result)
                await first.release(session, rid, turn.lock_token)
            restored = await second.get(session)
            assert restored and len(restored.history) == 10
            assert [row.content for row in restored.history][:2] == ["Question 2", "Answer 2"]
            assert [row.content for row in restored.history][-2:] == ["Question 6", "Answer 6"]
            assert await redis.llen(f"session:{session}:history") == 10
            await second.delete(session)

    asyncio.run(scenario())


def test_lease_and_state_are_owner_checked_in_both_stores() -> None:
    async def scenario() -> None:
        async with stores() as (first, second, redis):
            session = (await first.create(None)).session_id
            rid = str(uuid.uuid4())
            owner = await first.begin_turn(session, rid, "hash")
            assert await second.renew(session, rid, owner.lock_token)
            assert not await second.renew(session, rid, str(uuid.uuid4()))
            await first.transition(session, owner.lock_token, "STREAMING_TOKENS")
            assert await redis.hget(f"session:{session}:state", "state") == "STREAMING_TOKENS"
            with pytest.raises(TurnLost):
                await second.transition(session, str(uuid.uuid4()), "IDLE")
            await redis.delete(f"session:{session}:lock")
            with pytest.raises(TurnLost):
                await first.complete(
                    session, rid, owner.lock_token, "Question", terminal(session, owner.message_id)
                )
            await first.release(session, rid, owner.lock_token)
            assert (
                await second.begin_turn(session, rid, "hash")
            ).completed.finish_reason == "error"
            await second.delete(session)

    asyncio.run(scenario())


@pytest.mark.parametrize(
    "mutation",
    ["stock_quantity=0", "price=101", "voltage='127V'", "is_active=false", "name='Renamed'"],
)
def test_replay_never_reuses_cards_whose_sql_facts_changed(mutation: str) -> None:
    from pathlib import Path

    async def scenario() -> None:
        async with stores() as (first, second, _):
            # Real backend-owned schema; use a unique row and never truncate other tests' data.
            await execute(Path("../backend/app/db/schema.sql").read_text())
            sku = "M02-" + str(uuid.uuid4())
            await execute(
                "INSERT INTO products(sku,name,category,subcategory,brand,price,stock_quantity,voltage,image_url,checkout_url) "
                "VALUES(%s,'Example','test','test','test',100,2,'220V','/test.webp','https://example.com/product')",
                (sku,),
            )
            session = (await first.create(sku)).session_id
            rid = str(uuid.uuid4())
            owner = await first.begin_turn(session, rid, "hash")
            result = dataclasses.replace(
                terminal(session, owner.message_id),
                products=(
                    {
                        "sku": sku,
                        "name": "Example",
                        "price": 100,
                        "stock_quantity": 2,
                        "voltage": "220V",
                        "image_url": "/test.webp",
                        "marketplace": "AMAZON",
                        "checkout_url": "https://example.com/product",
                        "recommendation_type": "PRIMARY",
                        "badge_label": "Produto consultado",
                        "justification": "Catálogo verificado.",
                    },
                ),
            )
            await first.complete(session, rid, owner.lock_token, "Quero comprar", result)
            await first.release(session, rid, owner.lock_token)
            assert (await second.begin_turn(session, rid, "hash")).completed == result
            await execute(f"UPDATE products SET {mutation} WHERE sku=%s", (sku,))
            replay = await second.begin_turn(session, rid, "hash")
            assert replay.kind == TurnDecision.REPLAY and replay.message_id == owner.message_id
            assert replay.completed.finish_reason == "error" and replay.completed.products == ()
            assert "nova pergunta" in replay.completed.content
            # Original result and message pair are not rewritten by a delivery revalidation.
            assert len((await second.get(session)).history) == 2
            await second.delete(session)
            await execute("DELETE FROM products WHERE sku=%s", (sku,))

    asyncio.run(scenario())


def test_create_session_does_not_run_retention_maintenance(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Retention sweeps every table; the periodic task in main.py already runs it.
    async def scenario() -> None:
        async with stores() as (first, _, _redis):
            sweeps: list[None] = []

            async def counting_maintain() -> None:
                sweeps.append(None)

            monkeypatch.setattr(first, "maintain", counting_maintain)
            await first.create("AF-400-220V")
            assert sweeps == []

    asyncio.run(scenario())


def test_postgres_snapshot_restores_recommended_skus_into_history() -> None:
    async def scenario() -> None:
        async with stores() as (first, second, redis):
            session = (await first.create(None)).session_id
            rid = str(uuid.uuid4())
            turn = await first.begin_turn(session, rid, "hash")
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
            result = dataclasses.replace(terminal(session, turn.message_id), products=(card,))  # type: ignore[arg-type]
            await first.complete(session, rid, turn.lock_token, "Quero um PC", result)
            await first.release(session, rid, turn.lock_token)
            await redis.delete(*SessionCache.keys(session))
            restored = await second.get(session)
            assert restored is not None
            assert [item.recommended_skus for item in restored.history] == [(), ("PC-VX3-BIV",)]
            await second.delete(session)

    asyncio.run(scenario())
