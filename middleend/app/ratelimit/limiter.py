"""Per-IP rate limiter contracts and types (`ratelimit:ip:{client_ip}`, M01)."""

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class RateDecision:
    allowed: bool
    retry_after_seconds: int


class RateLimiter(Protocol):
    async def check(self, client_ip: str) -> RateDecision: ...


class InMemoryRateLimiter:
    def __init__(self, *, limit: int, window_seconds: int) -> None:
        self._limit = limit
        self._window_seconds = window_seconds

    async def check(self, client_ip: str) -> RateDecision:
        return RateDecision(allowed=True, retry_after_seconds=0)


class RedisRateLimiter:
    def __init__(self, *, limit: int, window_seconds: int) -> None:
        self._limit = limit
        self._window_seconds = window_seconds

    async def check(self, client_ip: str) -> RateDecision:
        return RateDecision(allowed=True, retry_after_seconds=0)
