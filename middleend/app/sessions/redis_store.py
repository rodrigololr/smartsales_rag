"""Redis sessions (M02, specs/architecture/02 section 4).

Keys, all under the session TTL (1800 s) unless noted:
    session:{id}:state      HASH   active_sku, state, updated_at
    session:{id}:history    LIST   newest first, LPUSH + LTRIM to the last N messages
    session:{id}:lock       STRING client_request_id, SET NX EX 60 (one turn at a time)
    session:{id}:turn:{rid} STRING idempotency record of one client_request_id
    session:{id}:turns      SET    request ids, so DELETE removes every turn record
"""

import dataclasses
import json
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

IDLE_STATE = "IDLE"
# Delete the lock only if this request still owns it (it may have expired and been retaken).
_RELEASE_LOCK = """
if redis.call('GET', KEYS[1]) == ARGV[1] then
    return redis.call('DEL', KEYS[1])
end
return 0
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
        await self._redis.hset(
            self._state_key(session_id),
            mapping={
                "state": IDLE_STATE,
                "active_sku": current_product_sku or "",
                "updated_at": datetime.now(UTC).isoformat(),
            },
        )
        await self._redis.expire(self._state_key(session_id), self._ttl_seconds)
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
        record = await self._turn_record(session_id, client_request_id)
        if record is not None and record["payload_hash"] != payload_hash:
            return TurnStart(TurnDecision.CONFLICT)
        if record is not None and record["completed"] is not None:
            completed = _completed_turn(cast(dict[str, object], record["completed"]))
            return TurnStart(TurnDecision.REPLAY, str(record["message_id"]), completed)
        acquired = await self._redis.set(
            self._lock_key(session_id), client_request_id, nx=True, ex=self._lock_ttl_seconds
        )
        if not acquired:
            return TurnStart(TurnDecision.IN_PROGRESS)
        message_id = str(uuid.uuid4())
        await self._save_turn(session_id, client_request_id, payload_hash, message_id, None)
        return TurnStart(TurnDecision.NEW, message_id)

    async def complete(
        self, session_id: str, client_request_id: str, question: str, turn: CompletedTurn
    ) -> None:
        record = await self._turn_record(session_id, client_request_id)
        if record is None or record["completed"] is not None:
            return  # replays complete again; history must not grow twice
        user, assistant = turn_messages(question, turn)
        history_key = self._history_key(session_id)
        async with self._redis.pipeline(transaction=True) as pipe:
            pipe.set(
                self._turn_key(session_id, client_request_id),
                _turn_json(str(record["payload_hash"]), str(record["message_id"]), turn),
                ex=self._ttl_seconds,
            )
            pipe.lpush(history_key, _history_json(user), _history_json(assistant))
            pipe.ltrim(history_key, 0, self._history_max_messages - 1)
            pipe.expire(history_key, self._ttl_seconds)
            await pipe.execute()

    async def release(self, session_id: str, client_request_id: str) -> None:
        await self._redis.eval(_RELEASE_LOCK, 1, self._lock_key(session_id), client_request_id)
        record = await self._turn_record(session_id, client_request_id)
        if record is not None and record["completed"] is None:
            # Unfinished turns are forgotten so the browser's reconnect regenerates them.
            await self._redis.delete(self._turn_key(session_id, client_request_id))
            await self._redis.srem(self._turns_key(session_id), client_request_id)

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

    async def _save_turn(
        self,
        session_id: str,
        client_request_id: str,
        payload_hash: str,
        message_id: str,
        completed: CompletedTurn | None,
    ) -> None:
        await self._redis.set(
            self._turn_key(session_id, client_request_id),
            _turn_json(payload_hash, message_id, completed),
            ex=self._ttl_seconds,
        )
        await self._redis.sadd(self._turns_key(session_id), client_request_id)
        await self._redis.expire(self._turns_key(session_id), self._ttl_seconds)

    async def _renew(self, session_id: str) -> None:
        for key in (
            self._state_key(session_id),
            self._history_key(session_id),
            self._turns_key(session_id),
        ):
            await self._redis.expire(key, self._ttl_seconds)

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
