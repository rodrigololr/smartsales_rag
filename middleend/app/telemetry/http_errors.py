"""Source of `error_5xx_rate` (M04, RNF06): the gateway counts its own HTTP responses.

Every HTTP response increments `total` (and `5xx` when status >= 500) in a Redis hash per
UTC hour, `metrics:http:YYYYMMDDHH`, kept for COUNTER_RETENTION. The rate for a window is
sum(5xx) / sum(total) over the hours the window touches, so it has hour granularity.
An exception that escapes before the response starts counts as a 500. Limits: nothing is
counted without Redis (rate 0), nor while Redis itself is down, and SSE turns that fail
after the 200 headers are not 5xx (they end in `done: error`, not in an HTTP status).
"""

import logging
from datetime import UTC, datetime, timedelta

from redis.asyncio import Redis
from redis.exceptions import RedisError
from starlette.types import ASGIApp, Message, Receive, Scope, Send

logger = logging.getLogger(__name__)

KEY_PREFIX = "metrics:http:"
COUNTER_RETENTION = timedelta(days=31)
HOUR = timedelta(hours=1)
SERVER_ERROR = 500
TOTAL_FIELD = "total"
ERROR_FIELD = "5xx"


def _hour_key(moment: datetime) -> str:
    return KEY_PREFIX + moment.astimezone(UTC).strftime("%Y%m%d%H")


def hour_keys(window_from: datetime, window_to: datetime, now: datetime) -> list[str]:
    """Hash keys of every hour overlapping [from, to), clamped to the retained hours."""
    start = max(window_from, now - COUNTER_RETENTION).astimezone(UTC)
    end = min(window_to, now)
    if start >= end:
        return []
    hour = start.replace(minute=0, second=0, microsecond=0)
    keys = []
    while hour < end:
        keys.append(_hour_key(hour))
        hour += HOUR
    return keys


async def error_5xx_rate(
    redis: Redis | None, window_from: datetime, window_to: datetime, now: datetime
) -> float:
    keys = hour_keys(window_from, window_to, now)
    if redis is None or not keys:
        return 0.0
    try:
        async with redis.pipeline(transaction=False) as pipeline:
            for key in keys:
                pipeline.hmget(key, TOTAL_FIELD, ERROR_FIELD)
            buckets: list[list[str | None]] = await pipeline.execute()
    except RedisError:
        # Only this metric depends on Redis: degrade it instead of failing the summary.
        logger.warning("metrics_error_rate_unavailable")
        return 0.0
    total = sum(int(bucket[0] or 0) for bucket in buckets)
    errors = sum(int(bucket[1] or 0) for bucket in buckets)
    return errors / total if total else 0.0


class ResponseCounter:
    """Pure ASGI middleware (streams pass through untouched)."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        status = SERVER_ERROR

        async def capture_status(message: Message) -> None:
            nonlocal status
            if message["type"] == "http.response.start":
                status = message["status"]
            await send(message)

        try:
            await self.app(scope, receive, capture_status)
        finally:
            await _count(getattr(scope["app"].state, "redis", None), status)


async def _count(redis: Redis | None, status: int) -> None:
    if redis is None:
        return
    key = _hour_key(datetime.now(UTC))
    try:
        async with redis.pipeline(transaction=False) as pipeline:
            pipeline.hincrby(key, TOTAL_FIELD, 1)
            if status >= SERVER_ERROR:
                pipeline.hincrby(key, ERROR_FIELD, 1)
            pipeline.expire(key, COUNTER_RETENTION)
            await pipeline.execute()
    except RedisError:
        # Telemetry must never fail the request it measures.
        logger.warning("http_response_counter_failed", extra={"status": status})
