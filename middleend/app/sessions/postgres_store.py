"""M02 durable sessions/turns. SQL transactions serialize each session, not workers.

Redis is a projection plus a renewable lease. A SQL reservation is never regenerated:
RUNNING -> COMPLETED/FAILED -> EXPIRED. Only a new explicit request id can generate again.
"""

import dataclasses
import logging
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import cast

from psycopg import AsyncConnection
from psycopg import Error as DatabaseError
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb
from redis.exceptions import RedisError

from app.sessions.cache import SessionCache
from app.sessions.redis_store import decode_turn
from app.sessions.replay import validated_replay
from app.sessions.store import (
    HistoryItem,
    SessionSnapshot,
    TurnDecision,
    TurnLost,
    TurnStart,
    TurnState,
    abandoned_turn,
    turn_messages,
)
from app.sse.models import CompletedTurn

logger = logging.getLogger(__name__)
Row = dict[str, object]
Connection = AsyncConnection[Row]
MIGRATION_LOCK = 260802
PAYLOAD_TTL_SECONDS = 86400
MAX_RETENTION_DAYS = 90


class PostgresSessionStore:
    def __init__(
        self,
        database_url: str,
        cache: SessionCache,
        *,
        ttl_seconds: int,
        history_max_messages: int,
        lock_ttl_seconds: int,
        connect_timeout_seconds: int = 2,
        query_timeout_ms: int = 2000,
    ) -> None:
        self._url, self._cache = database_url, cache
        self._ttl, self._window, self._lease = ttl_seconds, history_max_messages, lock_ttl_seconds
        self._connect_timeout, self._query_timeout = connect_timeout_seconds, query_timeout_ms

    @asynccontextmanager
    async def _connection(self) -> AsyncIterator[Connection]:
        connection = cast(
            Connection,
            await AsyncConnection.connect(
                self._url,
                row_factory=dict_row,
                connect_timeout=self._connect_timeout,
                options=f"-c statement_timeout={self._query_timeout} -c lock_timeout={self._query_timeout}",
            ),
        )
        async with connection:
            yield connection

    async def initialize(self) -> None:
        async with self._connection() as connection:
            await connection.execute("SELECT pg_advisory_xact_lock(%s)", (MIGRATION_LOCK,))
            await connection.execute(
                Path(__file__).parents[1].joinpath("db/schema.sql").read_text()
            )
        await self.maintain()

    async def maintain(self) -> None:
        """Bounded retention, also run periodically by the app (not just on session reads)."""
        async with self._connection() as connection:
            await connection.execute(
                "DELETE FROM chat_sessions WHERE created_at <= clock_timestamp() - make_interval(days => %s)",
                (MAX_RETENTION_DAYS,),
            )
            await connection.execute(
                "UPDATE chat_sessions SET state='ENDED' WHERE state='ACTIVE' AND "
                "last_active_at <= clock_timestamp() - make_interval(secs => %s)",
                (self._ttl,),
            )
            await connection.execute(
                "UPDATE chat_turn_requests SET terminal_payload=NULL,status='EXPIRED' "
                "WHERE expires_at <= clock_timestamp() AND status <> 'EXPIRED'",
            )
            # Session closure is final; no tombstone needs to outlive it.
            await connection.execute(
                "UPDATE chat_turn_requests SET terminal_payload=NULL,status='EXPIRED' "
                "WHERE status <> 'EXPIRED' AND session_id IN (SELECT id FROM chat_sessions WHERE state='ENDED')",
            )

    async def _active(self, connection: Connection, session_id: str) -> Row | None:
        cursor = await connection.execute(
            "SELECT *, state='ACTIVE' AND last_active_at > clock_timestamp()-make_interval(secs => %s) "
            "AND created_at > clock_timestamp()-make_interval(days => %s) AS active "
            "FROM chat_sessions WHERE id=%s FOR UPDATE",
            (self._ttl, MAX_RETENTION_DAYS, session_id),
        )
        row = await cursor.fetchone()
        if row is None:
            return None
        if not row["active"]:
            await connection.execute(
                "UPDATE chat_sessions SET state='ENDED' WHERE id=%s", (session_id,)
            )
            return None
        return row

    async def _snapshot(self, connection: Connection, row: Row) -> SessionSnapshot:
        cursor = await connection.execute(
            "SELECT m.id,m.role,m.content FROM chat_messages m JOIN chat_turn_requests t "
            "ON m.id IN (t.user_message_id,t.message_id) WHERE t.session_id=%s "
            "AND t.user_message_id IS NOT NULL ORDER BY t.completed_at DESC, "
            "CASE m.role WHEN 'assistant' THEN 0 ELSE 1 END LIMIT %s",
            (row["id"], self._window),
        )
        rows = await cursor.fetchall()
        filters = cast(dict[str, object], row["active_filters"])
        return SessionSnapshot(
            str(row["id"]),
            cast(str | None, filters.get("current_product_sku")),
            tuple(
                HistoryItem(str(item["role"]), str(item["content"]), str(item["id"]))
                for item in reversed(rows)
            ),
        )

    async def _touch(self, connection: Connection, session_id: str) -> None:
        await connection.execute(
            "UPDATE chat_sessions SET last_active_at=clock_timestamp() WHERE id=%s", (session_id,)
        )

    async def create(self, current_product_sku: str | None) -> SessionSnapshot:
        session_id = str(uuid.uuid4())
        snapshot = SessionSnapshot(session_id, current_product_sku)
        async with self._connection() as connection:
            await connection.execute(
                "INSERT INTO chat_sessions(id,active_filters) VALUES(%s,%s)",
                (session_id, Jsonb({"current_product_sku": current_product_sku})),
            )
            await self._cache.sync(snapshot)
        return snapshot

    async def get(self, session_id: str) -> SessionSnapshot | None:
        async with self._connection() as connection:
            row = await self._active(connection, session_id)
            if row is None:
                await self._cache.delete(session_id)
                return None
            snapshot = await self._snapshot(connection, row)
            await self._touch(connection, session_id)
            await self._cache.sync(snapshot)
            return snapshot

    async def delete(self, session_id: str) -> bool:
        async with self._connection() as connection:
            row = await self._active(connection, session_id)
            if row is None:
                await self._cache.delete(session_id)
                return False
            await connection.execute(
                "UPDATE chat_sessions SET state='ENDED' WHERE id=%s", (session_id,)
            )
            await connection.execute(
                "UPDATE chat_turn_requests SET terminal_payload=NULL,status='EXPIRED' "
                "WHERE session_id=%s",
                (session_id,),
            )
            await self._cache.delete(session_id)
            return True

    async def _record(self, connection: Connection, session_id: str, request_id: str) -> Row | None:
        cursor = await connection.execute(
            "SELECT *,lease_expires_at > clock_timestamp() AS live, "
            "expires_at <= clock_timestamp() AS expired FROM chat_turn_requests "
            "WHERE session_id=%s AND client_request_id=%s FOR UPDATE",
            (session_id, request_id),
        )
        return await cursor.fetchone()

    async def _terminal(self, connection: Connection, row: Row, turn: CompletedTurn) -> None:
        await connection.execute(
            "UPDATE chat_turn_requests SET status=%s,terminal_payload=%s,completed_at=clock_timestamp(),"
            "lease_expires_at=NULL WHERE session_id=%s AND client_request_id=%s",
            (
                "FAILED" if turn.finish_reason == "error" else "COMPLETED",
                Jsonb(dataclasses.asdict(turn)),
                row["session_id"],
                row["client_request_id"],
            ),
        )

    async def _settled(self, connection: Connection, row: Row, payload_hash: str) -> TurnStart:
        if row["payload_hash"] != payload_hash:
            return TurnStart(TurnDecision.CONFLICT)
        if row["expired"] or row["status"] == "EXPIRED":
            await connection.execute(
                "UPDATE chat_turn_requests SET status='EXPIRED',terminal_payload=NULL "
                "WHERE session_id=%s AND client_request_id=%s",
                (row["session_id"], row["client_request_id"]),
            )
            return TurnStart(TurnDecision.EXPIRED)
        if row["status"] == "RUNNING":
            if row["live"]:
                return TurnStart(TurnDecision.IN_PROGRESS)
            turn = abandoned_turn(str(row["session_id"]), str(row["reserved_message_id"]))
            await self._terminal(connection, row, turn)
            await self._cache.owned("release", str(row["session_id"]), str(row["owner_token"]))
        else:
            turn = decode_turn(cast(dict[str, object], row["terminal_payload"]))
        turn = await validated_replay(connection, turn)
        return TurnStart(TurnDecision.REPLAY, turn.message_id, turn)

    async def begin_turn(
        self, session_id: str, client_request_id: str, payload_hash: str
    ) -> TurnStart:
        async with self._connection() as connection:
            row = await self._active(connection, session_id)
            if row is None:
                return TurnStart(TurnDecision.NOT_FOUND)
            record = await self._record(connection, session_id, client_request_id)
            if record is not None:
                return await self._settled(connection, record, payload_hash)
            cursor = await connection.execute(
                "SELECT client_request_id FROM chat_turn_requests WHERE session_id=%s AND status='RUNNING'",
                (session_id,),
            )
            for running in await cursor.fetchall():
                orphan = await self._record(
                    connection, session_id, str(running["client_request_id"])
                )
                assert orphan is not None
                if orphan["live"]:
                    return TurnStart(TurnDecision.IN_PROGRESS)
                await self._settled(connection, orphan, str(orphan["payload_hash"]))
            token, message_id = str(uuid.uuid4()), str(uuid.uuid4())
            await connection.execute(
                "INSERT INTO chat_turn_requests(session_id,client_request_id,payload_hash,reserved_message_id,"
                "owner_token,status,lease_expires_at,expires_at) VALUES(%s,%s,%s,%s,%s,'RUNNING',"
                "clock_timestamp()+make_interval(secs => %s),clock_timestamp()+make_interval(secs => %s)) "
                "ON CONFLICT DO NOTHING",
                (
                    session_id,
                    client_request_id,
                    payload_hash,
                    message_id,
                    token,
                    self._lease,
                    PAYLOAD_TTL_SECONDS,
                ),
            )
            snapshot = await self._snapshot(connection, row)
            await self._cache.sync(snapshot, token)
            await self._touch(connection, session_id)
            return TurnStart(TurnDecision.NEW, message_id, lock_token=token, snapshot=snapshot)

    async def _owned(
        self, connection: Connection, session_id: str, request_id: str, token: str
    ) -> Row:
        if await self._active(connection, session_id) is None:
            raise TurnLost("Session ended or expired")
        record = await self._record(connection, session_id, request_id)
        if (
            record is None
            or str(record["owner_token"]) != token
            or record["status"] != "RUNNING"
            or not record["live"]
        ):
            raise TurnLost("Session lease lost")
        return record

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
        async with self._connection() as connection:
            # Repeated completion by this same owner is a no-op, not a duplicate message pair.
            if await self._active(connection, session_id) is None:
                raise TurnLost("Session ended or expired")
            prior = await self._record(connection, session_id, client_request_id)
            if (
                prior
                and str(prior["owner_token"]) == lock_token
                and prior["status"] in ("COMPLETED", "FAILED")
            ):
                if decode_turn(cast(dict[str, object], prior["terminal_payload"])) != turn:
                    raise TurnLost("Terminal reservation already settled")
                return
            record = await self._owned(connection, session_id, client_request_id, lock_token)
            if (
                str(record["reserved_message_id"]) != turn.message_id
                or turn.session_id != session_id
            ):
                raise TurnLost("Terminal identity differs from reservation")
            if turn.finish_reason != "error" and not await self._cache.owned(
                "check", session_id, lock_token
            ):
                raise TurnLost("Redis lease lost")
            await self._messages(connection, record, question, turn)
            await self._terminal(connection, record, turn)
            await self._touch(connection, session_id)
        # SQL is committed before acknowledging done; Redis failure cannot erase that commit.
        try:
            await self.get(session_id)
        except (RedisError, DatabaseError):
            logger.warning("session_projection_failed", extra={"session_id": session_id})

    async def _messages(
        self, connection: Connection, record: Row, question: str, turn: CompletedTurn
    ) -> None:
        user, assistant = turn_messages(question, turn)
        if turn.finish_reason != "error":
            await connection.execute(
                "INSERT INTO chat_messages(id,session_id,role,content) VALUES(%s,%s,%s,%s)",
                (user.message_id, record["session_id"], user.role, user.content),
            )
        await connection.execute(
            "INSERT INTO chat_messages(id,session_id,role,content,citations,recommended_skus,ttft_ms,"
            "total_latency_ms,tokens_used,intent,cache_hit) VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
            (
                assistant.message_id,
                record["session_id"],
                assistant.role,
                assistant.content,
                Jsonb(list(turn.citations)),
                Jsonb([card["sku"] for card in turn.products]),
                turn.ttft_ms,
                turn.total_latency_ms,
                turn.tokens_used,
                turn.intent,
                turn.cache_hit,
            ),
        )
        await connection.execute(
            "UPDATE chat_turn_requests SET message_id=%s,user_message_id=%s "
            "WHERE session_id=%s AND client_request_id=%s",
            (
                assistant.message_id,
                user.message_id if turn.finish_reason != "error" else None,
                record["session_id"],
                record["client_request_id"],
            ),
        )

    async def release(self, session_id: str, client_request_id: str, lock_token: str) -> None:
        if not lock_token:
            return
        async with self._connection() as connection:
            if await self._active(connection, session_id) is None:
                return
            record = await self._record(connection, session_id, client_request_id)
            if record is None or str(record["owner_token"]) != lock_token:
                return
            if record["status"] == "RUNNING":
                await self._terminal(
                    connection,
                    record,
                    abandoned_turn(session_id, str(record["reserved_message_id"])),
                )
            try:
                await self._cache.owned("release", session_id, lock_token)
            except RedisError:
                logger.warning("session_unlock_failed", extra={"session_id": session_id})

    async def renew(self, session_id: str, client_request_id: str, lock_token: str) -> bool:
        try:
            async with self._connection() as connection:
                await self._owned(connection, session_id, client_request_id, lock_token)
                if not await self._cache.owned("renew", session_id, lock_token):
                    return False
                cursor = await connection.execute(
                    "UPDATE chat_turn_requests SET lease_expires_at=clock_timestamp()+make_interval(secs => %s) "
                    "WHERE session_id=%s AND client_request_id=%s AND lease_expires_at>clock_timestamp() RETURNING 1",
                    (self._lease, session_id, client_request_id),
                )
                if await cursor.fetchone() is None:
                    return False
                await self._touch(connection, session_id)
                return True
        except TurnLost:
            return False

    async def transition(self, session_id: str, lock_token: str, state: TurnState) -> None:
        async with self._connection() as connection:
            if await self._active(connection, session_id) is None:
                raise TurnLost("Session ended or expired")
            cursor = await connection.execute(
                "SELECT 1 FROM chat_turn_requests WHERE session_id=%s AND owner_token=%s AND status='RUNNING' "
                "AND lease_expires_at>clock_timestamp()",
                (session_id, lock_token),
            )
            if await cursor.fetchone() is None or not await self._cache.owned(
                "state", session_id, lock_token, state
            ):
                raise TurnLost("Session lease lost")

    async def ping(self) -> bool:
        try:
            return bool(await self._cache.client.ping())
        except RedisError:
            return False

    async def database_ping(self) -> bool | None:
        try:
            async with self._connection() as connection:
                await connection.execute("SELECT 1")
            return True
        except DatabaseError:
            return False
