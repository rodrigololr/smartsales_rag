"""Redis adapter of the semantic cache: cache:sem:* entries and catalog:version (RN09)."""

from redis.asyncio import Redis
from redis.exceptions import RedisError

from app.cache.service import CacheUnavailableError

CATALOG_VERSION_KEY = "catalog:version"


class RedisCacheStorage:
    def __init__(self, client: Redis) -> None:
        self._redis = client

    async def catalog_version(self) -> int:
        """Counter bumped by the ingestion CLI and the mock checkout; 0 before the first bump."""
        try:
            return int(await self._redis.get(CATALOG_VERSION_KEY) or 0)
        except RedisError as error:
            raise CacheUnavailableError("catalog:version unavailable") from error

    async def get(self, key: str) -> str | None:
        try:
            value = await self._redis.get(key)
        except RedisError as error:
            raise CacheUnavailableError("cache read failed") from error
        return str(value) if value is not None else None

    async def set(self, key: str, value: str, ttl_seconds: int) -> None:
        try:
            await self._redis.set(key, value, ex=ttl_seconds)
        except RedisError as error:
            raise CacheUnavailableError("cache write failed") from error

    async def delete(self, key: str) -> None:
        try:
            await self._redis.delete(key)
        except RedisError as error:
            raise CacheUnavailableError("cache delete failed") from error
