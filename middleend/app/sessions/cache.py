"""Redis projection of durable sessions; never a second source of truth."""

import json

from redis.asyncio import Redis

from app.sessions.redis_store import history_json
from app.sessions.store import SessionSnapshot, TurnState

_SYNC = """
local lock = redis.call('GET',KEYS[3])
if ARGV[1] == 'claim' then
    redis.call('SET',KEYS[3],ARGV[2],'EX',ARGV[4]); lock=ARGV[2]
end
redis.call('HSET',KEYS[1],'active_sku',ARGV[5],'updated_at',redis.call('TIME')[1])
if not lock then redis.call('HSET',KEYS[1],'state','IDLE') end
if ARGV[1] == 'claim' then redis.call('HSET',KEYS[1],'state','VALIDATING_CACHE') end
redis.call('DEL',KEYS[2])
for _, message in ipairs(cjson.decode(ARGV[6])) do redis.call('LPUSH',KEYS[2],message) end
redis.call('EXPIRE',KEYS[1],ARGV[3]); redis.call('EXPIRE',KEYS[2],ARGV[3])
return 1
"""
_OWNED = """
if redis.call('GET',KEYS[3]) ~= ARGV[2] or redis.call('EXISTS',KEYS[1]) == 0 then return 0 end
if ARGV[1] == 'release' then
    redis.call('DEL',KEYS[3]); redis.call('HSET',KEYS[1],'state','IDLE')
elseif ARGV[1] == 'renew' then
    redis.call('EXPIRE',KEYS[3],ARGV[4])
    redis.call('EXPIRE',KEYS[1],ARGV[3]); redis.call('EXPIRE',KEYS[2],ARGV[3])
elseif ARGV[1] == 'state' then
    redis.call('HSET',KEYS[1],'state',ARGV[5],'updated_at',redis.call('TIME')[1])
end
return 1
"""


class SessionCache:
    def __init__(self, client: Redis, ttl: int, lock_ttl: int) -> None:
        self.client, self.ttl, self.lock_ttl = client, ttl, lock_ttl

    @staticmethod
    def keys(session_id: str) -> tuple[str, str, str]:
        return tuple(f"session:{session_id}:{suffix}" for suffix in ("state", "history", "lock"))  # type: ignore[return-value]

    async def sync(self, snapshot: SessionSnapshot, token: str = "") -> None:
        await self.client.eval(
            _SYNC,
            3,
            *self.keys(snapshot.session_id),
            "claim" if token else "sync",
            token,
            self.ttl,
            self.lock_ttl,
            snapshot.current_product_sku or "",
            json.dumps([history_json(item) for item in snapshot.history]),
        )

    async def owned(
        self, operation: str, session_id: str, token: str, state: TurnState = "IDLE"
    ) -> bool:
        return bool(
            await self.client.eval(
                _OWNED, 3, *self.keys(session_id), operation, token, self.ttl, self.lock_ttl, state
            )
        )

    async def delete(self, session_id: str) -> None:
        await self.client.delete(*self.keys(session_id))
