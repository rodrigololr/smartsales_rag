"""Atomic Redis-only adapter for development; durable production uses PostgreSQL.

All mutations validate session existence and ownership inside one Lua execution.
Redis-only idempotency lasts while this development session's keys survive.
"""

import dataclasses
import json
import uuid
from typing import cast

from redis.asyncio import Redis
from redis.exceptions import RedisError

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

# KEYS: state, history, lock, turns, current turn. All belong to the same session.
# ARGV: operation, TTL, lock TTL, request id, hash, token, message id,
# terminal, user, assistant, max index, state, abandoned terminal, session id.
_OPERATE = """
local op, ttl, lockttl = ARGV[1], tonumber(ARGV[2]), tonumber(ARGV[3])
local exists = redis.call('EXISTS', KEYS[1]) == 1
local function snapshot()
    return {sku=redis.call('HGET', KEYS[1], 'active_sku') or '',
            state=redis.call('HGET', KEYS[1], 'state') or 'IDLE',
            history=redis.call('LRANGE', KEYS[2], 0, -1)}
end
local function touch()
    for _, key in ipairs({KEYS[1],KEYS[2],KEYS[4]}) do
        redis.call('EXPIRE',key,ttl)
    end
end
local function state(value)
    redis.call('HSET',KEYS[1],'state',value,'updated_at',redis.call('TIME')[1])
end
if op == 'delete' then
    local ids = redis.call('SMEMBERS',KEYS[4])
    local prefix = string.sub(KEYS[1],1,-7)
    for _, id in ipairs(ids) do redis.call('DEL',prefix .. ':turn:' .. id) end
    redis.call('DEL',KEYS[1],KEYS[2],KEYS[3],KEYS[4])
    return exists and '1' or '0'
end
if not exists then return cjson.encode({kind='NOT_FOUND'}) end
if op == 'get' then touch(); return cjson.encode(snapshot()) end
local lock = redis.call('GET',KEYS[3])
local raw = redis.call('GET',KEYS[5])
local record = raw and cjson.decode(raw) or nil
if op == 'begin' then
    if record then
        if record.payload_hash ~= ARGV[5] then return cjson.encode({kind='CONFLICT'}) end
        if record.completed ~= cjson.null then
            return cjson.encode({kind='REPLAY',record=record})
        end
        if not lock then
            local failed = cjson.decode(ARGV[13])
            failed.message_id = record.message_id
            record.completed = failed
            state('IDLE')
            redis.call('SET',KEYS[5],cjson.encode(record),'EX',ttl)
            return cjson.encode({kind='REPLAY',record=record})
        end
    end
    if lock then return cjson.encode({kind='IN_PROGRESS'}) end
    redis.call('SET',KEYS[3],ARGV[6],'NX','EX',lockttl)
    local fresh = {payload_hash=ARGV[5],message_id=ARGV[7],lock_token=ARGV[6],completed=cjson.null}
    redis.call('SET',KEYS[5],cjson.encode(fresh),'EX',ttl)
    redis.call('SADD',KEYS[4],ARGV[4]); touch(); state('VALIDATING_CACHE')
    return cjson.encode({kind='NEW',snapshot=snapshot()})
end
local owns = lock == ARGV[6] and ARGV[6] ~= ''
if op == 'release' then
    if not owns and lock then return '0' end
    if record and record.lock_token == ARGV[6] and record.completed == cjson.null then
        record.completed = cjson.decode(ARGV[13])
        record.completed.message_id = record.message_id
        redis.call('SET',KEYS[5],cjson.encode(record),'EX',ttl)
    end
    if owns then redis.call('DEL',KEYS[3]) end
    if owns or not lock then state('IDLE') end
    return '1'
end
if not owns then return '0' end
if op == 'renew' then
    redis.call('EXPIRE',KEYS[3],lockttl); touch()
    if raw then redis.call('EXPIRE',KEYS[5],ttl) end
    return '1'
end
if op == 'transition' then state(ARGV[12]); return '1' end
if op == 'complete' then
    if not record or record.lock_token ~= ARGV[6] then return '0' end
    if record.completed ~= cjson.null then return '1' end
    record.completed = cjson.decode(ARGV[8])
    redis.call('SET',KEYS[5],cjson.encode(record),'EX',ttl)
    if record.completed.finish_reason ~= 'error' then
        redis.call('LPUSH',KEYS[2],ARGV[9],ARGV[10])
        redis.call('LTRIM',KEYS[2],0,tonumber(ARGV[11]))
    end
    touch(); return '1'
end
return '0'
"""


def encode_turn(turn: CompletedTurn) -> str:
    return json.dumps(dataclasses.asdict(turn), ensure_ascii=False, allow_nan=False)


def decode_turn(fields: dict[str, object]) -> CompletedTurn:
    values = dict(fields)
    values["citations"] = tuple(cast(list[object], values["citations"]) or ())
    values["products"] = tuple(cast(list[object], values["products"]) or ())
    return CompletedTurn(**values)  # type: ignore[arg-type]


def history_json(item: HistoryItem) -> str:
    return json.dumps(
        {
            "id": item.message_id,
            "role": item.role,
            "content": item.content,
            "skus": list(item.recommended_skus),
        },
        ensure_ascii=False,
    )


def _snapshot(session_id: str, fields: dict[str, object]) -> SessionSnapshot:
    rows = (json.loads(raw) for raw in reversed(cast(list[str], fields["history"]) or []))
    return SessionSnapshot(
        session_id,
        str(fields["sku"]) or None,
        tuple(
            HistoryItem(row["role"], row["content"], row["id"], tuple(row.get("skus") or ()))
            for row in rows
        ),
        cast(TurnState, fields["state"]),
    )


class RedisSessionStore:
    def __init__(
        self, client: Redis, *, ttl_seconds: int, history_max_messages: int, lock_ttl_seconds: int
    ) -> None:
        self._redis = client
        self._ttl_seconds = ttl_seconds
        self._history_max_messages = history_max_messages
        self._lock_ttl_seconds = lock_ttl_seconds

    async def _call(
        self,
        operation: str,
        session_id: str,
        request_id: str = "",
        payload_hash: str = "",
        token: str = "",
        message_id: str = "",
        terminal: str = "",
        user: str = "",
        assistant: str = "",
        state: TurnState = "IDLE",
    ) -> str:
        prefix = f"session:{session_id}"
        return str(
            await self._redis.eval(
                _OPERATE,
                5,
                *(
                    prefix + suffix
                    for suffix in (":state", ":history", ":lock", ":turns", f":turn:{request_id}")
                ),
                operation,
                self._ttl_seconds,
                self._lock_ttl_seconds,
                request_id,
                payload_hash,
                token,
                message_id,
                terminal,
                user,
                assistant,
                self._history_max_messages - 1,
                state,
                encode_turn(abandoned_turn(session_id, message_id)),
                session_id,
            )
        )

    async def create(self, current_product_sku: str | None) -> SessionSnapshot:
        session_id = str(uuid.uuid4())
        async with self._redis.pipeline(transaction=True) as pipe:
            pipe.hset(
                f"session:{session_id}:state",
                mapping={
                    "state": "IDLE",
                    "active_sku": current_product_sku or "",
                    "updated_at": "0",
                },
            )
            pipe.expire(f"session:{session_id}:state", self._ttl_seconds)
            await pipe.execute()
        return SessionSnapshot(session_id, current_product_sku)

    async def get(self, session_id: str) -> SessionSnapshot | None:
        fields = json.loads(await self._call("get", session_id))
        return None if fields.get("kind") == "NOT_FOUND" else _snapshot(session_id, fields)

    async def delete(self, session_id: str) -> bool:
        return await self._call("delete", session_id) == "1"

    async def begin_turn(
        self, session_id: str, client_request_id: str, payload_hash: str
    ) -> TurnStart:
        message_id, token = str(uuid.uuid4()), str(uuid.uuid4())
        fields = json.loads(
            await self._call(
                "begin", session_id, client_request_id, payload_hash, token, message_id
            )
        )
        decision = TurnDecision(fields["kind"])
        if decision == TurnDecision.REPLAY:
            record = fields["record"]
            return TurnStart(decision, record["message_id"], decode_turn(record["completed"]))
        return TurnStart(
            decision,
            message_id if decision == TurnDecision.NEW else "",
            lock_token=token if decision == TurnDecision.NEW else "",
            snapshot=_snapshot(session_id, fields["snapshot"]) if "snapshot" in fields else None,
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
        user, assistant = turn_messages(question, turn)
        written = await self._call(
            "complete",
            session_id,
            client_request_id,
            token=lock_token,
            terminal=encode_turn(turn),
            user=history_json(user),
            assistant=history_json(assistant),
        )
        if written != "1":
            raise TurnLost("Session lease lost")

    async def release(self, session_id: str, client_request_id: str, lock_token: str) -> None:
        if not lock_token:
            return
        # Capture the reserved message id inside Lua rather than trusting stale clients.
        await self._call("release", session_id, client_request_id, token=lock_token)

    async def renew(self, session_id: str, client_request_id: str, lock_token: str) -> bool:
        return await self._call("renew", session_id, client_request_id, token=lock_token) == "1"

    async def transition(self, session_id: str, lock_token: str, state: TurnState) -> None:
        if await self._call("transition", session_id, token=lock_token, state=state) != "1":
            raise TurnLost("Session lease lost")

    async def ping(self) -> bool:
        try:
            return bool(await self._redis.ping())
        except RedisError:
            return False

    async def database_ping(self) -> bool | None:
        return None
