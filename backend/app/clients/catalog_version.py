"""catalog:version in Redis (RN09): bumped after ingestion to invalidate the semantic cache."""

from typing import Protocol

from redis.asyncio import Redis
from redis.exceptions import RedisError

CATALOG_VERSION_KEY = "catalog:version"


class CatalogVersionUnavailableError(Exception):
    """The version store is unreachable: caches built on the old catalog were not invalidated."""


class CatalogVersionBumper(Protocol):
    async def bump(self) -> int: ...


class RedisCatalogVersion:
    """One short-lived connection per bump: the ingestion CLI bumps once per run."""

    def __init__(self, redis_url: str, *, connect_timeout_seconds: float) -> None:
        self._redis_url = redis_url
        self._connect_timeout_seconds = connect_timeout_seconds

    async def bump(self) -> int:
        client = Redis.from_url(
            self._redis_url, socket_connect_timeout=self._connect_timeout_seconds
        )
        try:
            return int(await client.incr(CATALOG_VERSION_KEY))
        except RedisError as error:
            raise CatalogVersionUnavailableError(repr(error)) from error
        finally:
            await client.aclose()
