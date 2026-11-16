"""B03: catalog:version store failures and ingestion retry settings."""

import asyncio

import pytest
from app.clients.catalog_version import CatalogVersionUnavailableError, RedisCatalogVersion
from app.config import Settings
from pydantic import ValidationError

UNREACHABLE_REDIS_URL = "redis://127.0.0.1:1/0"


def test_unreachable_redis_raises_the_domain_error() -> None:
    bumper = RedisCatalogVersion(UNREACHABLE_REDIS_URL, connect_timeout_seconds=1.0)
    with pytest.raises(CatalogVersionUnavailableError):
        asyncio.run(bumper.bump())


def test_ingestion_needs_at_least_one_attempt() -> None:
    with pytest.raises(ValidationError):
        Settings(ingestion_max_attempts=0)


@pytest.mark.parametrize(
    "settings",
    [{"redis_connect_timeout_seconds": 0}, {"ingestion_backoff_seconds": -1}],
)
def test_ingestion_rejects_unbounded_timeout_or_negative_backoff(settings: dict[str, int]) -> None:
    with pytest.raises(ValidationError):
        Settings(**settings)


def test_redis_that_accepts_connections_but_never_replies_is_bounded() -> None:
    async def scenario() -> None:
        async def stall(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
            try:
                await reader.read()
            finally:
                writer.close()
                await writer.wait_closed()

        server = await asyncio.start_server(stall, "127.0.0.1", 0)
        async with server:
            port = server.sockets[0].getsockname()[1]
            bumper = RedisCatalogVersion(
                f"redis://127.0.0.1:{port}/0", connect_timeout_seconds=0.02
            )
            with pytest.raises(CatalogVersionUnavailableError):
                await asyncio.wait_for(bumper.bump(), 0.5)

    asyncio.run(scenario())
