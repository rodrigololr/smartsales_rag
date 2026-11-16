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
