"""Redis sessions (M02, specs/architecture/02 section 4).

Keys, all under the session TTL (1800 s) unless noted:
    session:{id}:state      HASH   active_sku, state, updated_at
    session:{id}:history    LIST   newest first, LPUSH + LTRIM to the last N messages
    session:{id}:lock       STRING owner token of the turn, SET NX EX 60 (one turn at a time)
    session:{id}:turn:{rid} STRING idempotency record of one client_request_id
    session:{id}:turns      SET    request ids, so DELETE removes every turn record
"""

import dataclasses
import json
import logging
import uuid
from datetime import UTC, datetime
from typing import cast

from redis.asyncio import Redis
from redis.exceptions import RedisError

from app.sessions.store import (
    HistoryItem,
    SessionSnapshot,
    TurnDecision,
    TurnStart,
    turn_messages,
)
from app.sse.models import CompletedTurn

logger = logging.getLogger(__name__)

IDLE_STATE = "IDLE"
# Both scripts act only while ARGV[1] still owns the lock: it may have expired and been
# retaken, even by a retry of the same client_request_id.
# KEYS: lock, turn record, turns set. ARGV: owner token, client_request_id.
# Atomic so a retry cannot slip between the unlock and the cleanup of the unfinished record.
_RELEASE_TURN = """
if redis.call('GET', KEYS[1]) ~= ARGV[1] then
    return 0
end
redis.call('DEL', KEYS[1])
local record = redis.call('GET', KEYS[2])
if record and cjson.decode(record)['completed'] == cjson.null then
    redis.call('DEL', KEYS[2])
    redis.call('SREM', KEYS[3], ARGV[2])
end
return 1
"""
# KEYS: lock, turn record, history. ARGV: owner token, completed record, user message,
# assistant message, session TTL, last index of the history window.
_COMPLETE_TURN = """
if redis.call('GET', KEYS[1]) ~= ARGV[1] then
    return 0
end
local record = redis.call('GET', KEYS[2])
if not record or cjson.decode(record)['completed'] ~= cjson.null then
    return 0
end
redis.call('SET', KEYS[2], ARGV[2], 'EX', ARGV[5])
redis.call('LPUSH', KEYS[3], ARGV[3], ARGV[4])
redis.call('LTRIM', KEYS[3], 0, ARGV[6])
redis.call('EXPIRE', KEYS[3], ARGV[5])
return 1
"""


def _history_json(item: HistoryItem) -> str:
    return json.dumps(
        {"id": item.message_id, "role": item.role, "content": item.content}, ensure_ascii=False
    )


def _history_item(raw: str) -> HistoryItem:
    message = json.loads(raw)
    return HistoryItem(message["role"], message["content"], message["id"])


def _turn_json(payload_hash: str, message_id: str, completed: CompletedTurn | None) -> str:
    return json.dumps(
        {
            "payload_hash": payload_hash,
            "message_id": message_id,
            "completed": dataclasses.asdict(completed) if completed else None,
        },
        ensure_ascii=False,
    )


def _completed_turn(fields: dict[str, object]) -> CompletedTurn:
    values = dict(fields)
    values["citations"] = tuple(cast(list[object], values["citations"]))
    values["products"] = tuple(cast(list[object], values["products"]))
    return CompletedTurn(**values)  # type: ignore[arg-type]


class RedisSessionStore:
    def __init__(
        self,
        client: Redis,
        *,
        ttl_seconds: int,
        history_max_messages: int,
        lock_ttl_seconds: int,
    ) -> None:
        self._redis = client
        self._ttl_seconds = ttl_seconds
        self._history_max_messages = history_max_messages
        self._lock_ttl_seconds = lock_ttl_seconds

    async def create(self, current_product_sku: str | None) -> SessionSnapshot:
        session_id = str(uuid.uuid4())
        async with self._redis.pipeline(transaction=True) as pipe:
            pipe.hset(
                self._state_key(session_id),
                mapping={
                    "state": IDLE_STATE,
                    "active_sku": current_product_sku or "",
                    "updated_at": datetime.now(UTC).isoformat(),
                },
            )
            pipe.expire(self._state_key(session_id), self._ttl_seconds)
            await pipe.execute()
        return SessionSnapshot(session_id, current_product_sku)

    async def get(self, session_id: str) -> SessionSnapshot | None:
        state = await self._redis.hgetall(self._state_key(session_id))
        if not state:
            return None
        newest_first = await self._redis.lrange(self._history_key(session_id), 0, -1)
        await self._renew(session_id)
        return SessionSnapshot(
            session_id,
            str(state.get("active_sku") or "") or None,
            tuple(_history_item(str(raw)) for raw in reversed(newest_first)),
        )

    async def delete(self, session_id: str) -> bool:
        request_ids = await self._redis.smembers(self._turns_key(session_id))
        removed = await self._redis.delete(
            self._state_key(session_id),
            self._history_key(session_id),
            self._lock_key(session_id),
            self._turns_key(session_id),
            *(self._turn_key(session_id, str(request_id)) for request_id in request_ids),
        )
        return bool(removed)

    async def begin_turn(
        self, session_id: str, client_request_id: str, payload_hash: str
    ) -> TurnStart:
        settled = self._settled(await self._turn_record(session_id, client_request_id), payload_hash)
        if settled is not None:
            return settled
        lock_token = str(uuid.uuid4())
        acquired = await self._redis.set(
            self._lock_key(session_id), lock_token, nx=True, ex=self._lock_ttl_seconds
        )
        if not acquired:
            return TurnStart(TurnDecision.IN_PROGRESS)
        # Read again under the lock: the running turn may have completed since the first read.
        settled = self._settled(await self._turn_record(session_id, client_request_id), payload_hash)
        if settled is not None:
            await self.release(session_id, client_request_id, lock_token)
            return settled
        message_id = str(uuid.uuid4())
        await self._save_turn(session_id, client_request_id, payload_hash, message_id)
        return TurnStart(TurnDecision.NEW, message_id, lock_token=lock_token)

    async def complete(
        self,
        session_id: str,
        client_request_id: str,
        lock_token: str,
        question: str,
        turn: CompletedTurn,
    ) -> None:
        if not lock_token:
            return  # replays hold no lock; history must not grow twice
        record = await self._turn_record(session_id, client_request_id)
        if record is None:
            return
        user, assistant = turn_messages(question, turn)
        written = await self._redis.eval(
            _COMPLETE_TURN,
            3,
            self._lock_key(session_id),
            self._turn_key(session_id, client_request_id),
            self._history_key(session_id),
            lock_token,
            _turn_json(str(record["payload_hash"]), str(record["message_id"]), turn),
            _history_json(user),
            _history_json(assistant),
            self._ttl_seconds,
            self._history_max_messages - 1,
        )
        if not written:
            # The turn outlived its lock: whoever retook the session owns the history now.
            logger.warning("turn_not_persisted_lock_lost", extra={"session_id": session_id})

    async def release(self, session_id: str, client_request_id: str, lock_token: str) -> None:
        await self._redis.eval(
            _RELEASE_TURN,
            3,
            self._lock_key(session_id),
            self._turn_key(session_id, client_request_id),
            self._turns_key(session_id),
            lock_token,
            client_request_id,
        )

    async def ping(self) -> bool:
        try:
            return bool(await self._redis.ping())
        except RedisError:
            return False

    async def _turn_record(
        self, session_id: str, client_request_id: str
    ) -> dict[str, object] | None:
        raw = await self._redis.get(self._turn_key(session_id, client_request_id))
        return cast(dict[str, object], json.loads(raw)) if raw else None

    @staticmethod
    def _settled(record: dict[str, object] | None, payload_hash: str) -> TurnStart | None:
        """CONFLICT or REPLAY when the record already decides the request, else None."""
        if record is None:
            return None
        if record["payload_hash"] != payload_hash:
            return TurnStart(TurnDecision.CONFLICT)
        if record["completed"] is None:
            return None
        completed = _completed_turn(cast(dict[str, object], record["completed"]))
        return TurnStart(TurnDecision.REPLAY, str(record["message_id"]), completed)

    async def _save_turn(
        self, session_id: str, client_request_id: str, payload_hash: str, message_id: str
    ) -> None:
        async with self._redis.pipeline(transaction=True) as pipe:
            pipe.set(
                self._turn_key(session_id, client_request_id),
                _turn_json(payload_hash, message_id, None),
                ex=self._ttl_seconds,
            )
            pipe.sadd(self._turns_key(session_id), client_request_id)
            pipe.expire(self._turns_key(session_id), self._ttl_seconds)
            await pipe.execute()

    async def _renew(self, session_id: str) -> None:
        async with self._redis.pipeline(transaction=True) as pipe:
            for key in (
                self._state_key(session_id),
                self._history_key(session_id),
                self._turns_key(session_id),
            ):
                pipe.expire(key, self._ttl_seconds)
            await pipe.execute()

    @staticmethod
    def _state_key(session_id: str) -> str:
        return f"session:{session_id}:state"

    @staticmethod
    def _history_key(session_id: str) -> str:
        return f"session:{session_id}:history"

    @staticmethod
    def _lock_key(session_id: str) -> str:
        return f"session:{session_id}:lock"

    @staticmethod
    def _turns_key(session_id: str) -> str:
        return f"session:{session_id}:turns"

    @staticmethod
    def _turn_key(session_id: str, client_request_id: str) -> str:
        return f"session:{session_id}:turn:{client_request_id}"
