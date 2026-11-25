"""Bounded retry and pacing for provider quota/timeouts in the live evaluation only.

Production keeps its own RNF07 policy; this only stops a 429 from being scored as a
quality failure. It never changes a metric, threshold or gate.
"""

import asyncio
import time
from collections.abc import Awaitable, Callable, Iterator
from typing import TypeVar

import openai
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

_Result = TypeVar("_Result")
BACKOFF_BASE_SECONDS = 2.0
BACKOFF_MAX_SECONDS = 60.0
_TRANSIENT = (
    openai.RateLimitError,
    openai.APITimeoutError,
    openai.APIConnectionError,
    openai.InternalServerError,
    TimeoutError,
)


class RetrySettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="EVAL_", extra="ignore")
    max_retries: int = Field(default=6, ge=0)
    min_interval_seconds: float = Field(default=0.0, ge=0)


def _chain(error: BaseException) -> Iterator[BaseException]:
    """The error and its causes: production adapters wrap provider errors (LLMUnavailableError)."""
    seen: set[int] = set()
    current: BaseException | None = error
    while current is not None and id(current) not in seen:
        seen.add(id(current))
        yield current
        current = current.__cause__ or current.__context__


def _retry_after(error: BaseException) -> float | None:
    for link in _chain(error):
        response = getattr(link, "response", None)
        value = getattr(response, "headers", {}).get("retry-after")
        if value is not None:
            try:
                return max(float(value), 0.0)
            except ValueError:
                return None  # HTTP-date form: fall back to exponential backoff
    return None


class ProviderRetry:
    def __init__(
        self,
        settings: RetrySettings,
        *,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.settings, self._sleep, self._clock = settings, sleep, clock
        self._next_call = 0.0

    async def pace(self) -> None:
        """Keep at least `min_interval_seconds` between call starts (shared by every caller)."""
        wait = self._next_call - self._clock()
        if wait > 0:
            await self._sleep(wait)
        self._next_call = self._clock() + self.settings.min_interval_seconds

    async def backoff(self, error: BaseException, attempt: int) -> bool:
        """Sleep before retry `attempt` (0-based); False when the error must propagate."""
        if attempt >= self.settings.max_retries or not any(
            isinstance(link, _TRANSIENT) for link in _chain(error)
        ):
            return False
        delay = _retry_after(error)
        if delay is None:
            delay = min(BACKOFF_BASE_SECONDS * 2**attempt, BACKOFF_MAX_SECONDS)
        await self._sleep(delay)
        return True

    async def run(self, call: Callable[[], Awaitable[_Result]]) -> _Result:
        attempt = 0
        while True:
            await self.pace()
            try:
                return await call()
            except Exception as error:
                if not await self.backoff(error, attempt):
                    raise
                attempt += 1
