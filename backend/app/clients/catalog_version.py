"""catalog:version in Redis (RN09): bumped after ingestion to invalidate the semantic cache."""

from typing import Protocol

from redis.asyncio import Redis

CATALOG_VERSION_KEY = "catalog:version"


class CatalogVersionBumper(Protocol):
    async def bump(self) -> int: ...


class RedisCatalogVersion:
    """One short-lived connection per bump: the ingestion CLI bumps once per run."""

    def __init__(self, redis_url: str) -> None:
        self._redis_url = redis_url

    async def bump(self) -> int:
        client = Redis.from_url(self._redis_url)
        try:
            return int(await client.incr(CATALOG_VERSION_KEY))
        finally:
            await client.aclose()
