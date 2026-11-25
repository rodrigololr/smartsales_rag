"""Rate limiter per bucket (`ratelimit:ip:{client_ip}`, `ratelimit:session:{id}`; M01 / R16).

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

RATE_LIMIT_KEY_PREFIX = "ratelimit:"
RATE_LIMIT_WINDOW_SECONDS = 60  # fixed: the limit and the 429 message are "per minute"
# Chat is limited per session; this coarse per-IP bucket (sessions sharing one NAT,
# e.g. a classroom) still bounds requests that never reach a valid session.
CHAT_SESSIONS_PER_IP = 10
# Catalog GETs: the Next.js SSR renders every visitor from one container IP, so they get
# their own generous bucket (20x) instead of none, which still caps a scraper.
CATALOG_READS_PER_IP = 20
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
    async def check(self, bucket: str) -> RateDecision: ...


def client_ip_from_request(request: Request, *, trusted_proxy_hops: int = 0) -> str:
    """Address of the client as seen by the first trusted hop.

    Each trusted proxy appends the address it received the request from, so only the
    last `trusted_proxy_hops` entries of X-Forwarded-For can be believed; anything to
    their left was written by the client itself.
    """
    peer = request.client.host if request.client and request.client.host else "127.0.0.1"
    if trusted_proxy_hops <= 0:
        return peer
    forwarded = [
        hop.strip() for hop in request.headers.get("x-forwarded-for", "").split(",") if hop.strip()
    ]
    if len(forwarded) < trusted_proxy_hops:
        return peer  # the request skipped a trusted proxy: every entry was client-written
    return forwarded[len(forwarded) - trusted_proxy_hops]


class InMemoryRateLimiter:
    """Fixed-window per-bucket counter for single-replica development and unit tests."""

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

    @property
    def tracked_clients(self) -> int:
        return len(self._windows)

    async def check(self, bucket: str) -> RateDecision:
        now = self._clock()
        # Forget closed windows so the table stays bounded by the clients of one window.
        # shortcut: O(n) sweep per request, switch to a periodic sweep if the in-memory
        # mode ever serves many clients (production uses RedisRateLimiter).
        self._windows = {key: entry for key, entry in self._windows.items() if entry[1] > now}
        entry = self._windows.get(bucket)
        if entry is None or now >= entry[1]:
            expires_at = now + self._window_seconds
            count = 1
        else:
            count = entry[0] + 1
            expires_at = entry[1]
        self._windows[bucket] = (count, expires_at)
        remaining = max(1, math.ceil(expires_at - now))
        return RateDecision(allowed=count <= self._limit, retry_after_seconds=remaining)


class RedisRateLimiter:
    """Atomic Redis counter on `ratelimit:{bucket}` with TTL = window_seconds."""

    def __init__(self, redis: Redis, *, limit: int, window_seconds: int) -> None:
        self._redis = redis
        self._limit = limit
        self._window_seconds = window_seconds

    async def check(self, bucket: str) -> RateDecision:
        key = f"{RATE_LIMIT_KEY_PREFIX}{bucket}"
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
            logger.warning("rate_limit_redis_unavailable", extra={"bucket": bucket})
            return RateDecision(allowed=True, retry_after_seconds=0)
