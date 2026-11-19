"""Per-IP rate limiter (`ratelimit:ip:{client_ip}`, M01 / RNF09).

Uses atomic INCR + EXPIRE in Redis (60s window, 30 req/min default) with an
in-memory fallback for single-process development when REDIS_URL is unset.
"""

import logging
import math
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol, cast

from fastapi import Request
from redis.asyncio import Redis
from redis.exceptions import RedisError

logger = logging.getLogger(__name__)

RATE_LIMIT_KEY_PREFIX = "ratelimit:ip:"
_REDIS_RATE_LIMIT_LUA = """
local count = redis.call('INCR', KEYS[1])
local ttl = redis.call('TTL', KEYS[1])
if count == 1 or ttl < 0 then
    redis.call('EXPIRE', KEYS[1], tonumber(ARGV[1]))
    ttl = tonumber(ARGV[1])
end
return {count, ttl}
"""


@dataclass(frozen=True)
class RateDecision:
    allowed: bool
    retry_after_seconds: int


class RateLimiter(Protocol):
    async def check(self, client_ip: str) -> RateDecision: ...


def client_ip_from_request(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        first_hop = forwarded.split(",", 1)[0].strip()
        if first_hop:
            return first_hop
    if request.client and request.client.host:
        return request.client.host
    return "127.0.0.1"


class InMemoryRateLimiter:
    """Fixed-window per-IP counter for single-replica development and unit tests."""

    def __init__(
        self,
        *,
        limit: int,
        window_seconds: int,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._limit = limit
        self._window_seconds = window_seconds
        self._clock = clock
        self._windows: dict[str, tuple[int, float]] = {}

    async def check(self, client_ip: str) -> RateDecision:
        now = self._clock()
        entry = self._windows.get(client_ip)
        if entry is None or now >= entry[1]:
            expires_at = now + self._window_seconds
            count = 1
        else:
            count = entry[0] + 1
            expires_at = entry[1]
        self._windows[client_ip] = (count, expires_at)
        remaining = max(1, math.ceil(expires_at - now))
        return RateDecision(allowed=count <= self._limit, retry_after_seconds=remaining)


class RedisRateLimiter:
    """Atomic Redis counter on `ratelimit:ip:{client_ip}` with TTL = window_seconds."""

    def __init__(self, redis: Redis, *, limit: int, window_seconds: int) -> None:
        self._redis = redis
        self._limit = limit
        self._window_seconds = window_seconds

    async def check(self, client_ip: str) -> RateDecision:
        key = f"{RATE_LIMIT_KEY_PREFIX}{client_ip}"
        try:
            raw = await cast(
                object,
                self._redis.eval(_REDIS_RATE_LIMIT_LUA, 1, key, self._window_seconds),  # type: ignore[misc]
            )
            pair = cast(list[int], raw)
            count = int(pair[0])
            ttl = max(1, int(pair[1]))
            return RateDecision(allowed=count <= self._limit, retry_after_seconds=ttl)
        except RedisError:
            # Storage-level failures on session/chat routes still fail-closed via their
            # own handlers; rate limiter degrades gracefully rather than masking 503.
            logger.warning("rate_limit_redis_unavailable", extra={"client_ip": client_ip})
            return RateDecision(allowed=True, retry_after_seconds=0)
