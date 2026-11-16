"""Public API gateway (:8000) for the MVP chat."""

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from redis.asyncio import Redis
from redis.exceptions import RedisError

from app.cache.redis_storage import RedisCacheStorage
from app.cache.service import SemanticCacheService
from app.clients.backend import BackendClient
from app.config import Settings, get_settings
from app.repositories.products import PostgresProductSnapshots
from app.routes.chat import RagBackend, error_response, router
from app.sessions.redis_store import RedisSessionStore
from app.sessions.store import InMemorySessionStore, SessionStore

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def redis_unavailable(request: Request, failure: Exception) -> JSONResponse:
    """Session storage is down before the stream started: 503 in the REST error envelope."""
    session_id = getattr(request.state, "session_id", None)
    logger.error("redis_unavailable", extra={"session_id": session_id}, exc_info=failure)
    return error_response(
        503, "SERVICE_UNAVAILABLE", "Serviço temporariamente indisponível. Tente novamente."
    )


def build_session_store(settings: Settings, redis: Redis | None) -> SessionStore:
    if redis is None:
        return InMemorySessionStore(
            ttl_seconds=settings.session_ttl_seconds,
            history_max_messages=settings.session_history_max_messages,
        )
    return RedisSessionStore(
        redis,
        ttl_seconds=settings.session_ttl_seconds,
        history_max_messages=settings.session_history_max_messages,
        lock_ttl_seconds=settings.session_lock_ttl_seconds,
    )


def build_cache(settings: Settings, redis: Redis | None) -> SemanticCacheService | None:
    """The cache serves only what it can revalidate: it needs Redis and PostgreSQL."""
    if redis is None or not settings.database_url:
        return None
    return SemanticCacheService(
        RedisCacheStorage(redis),
        PostgresProductSnapshots(
            settings.database_url,
            connect_timeout_seconds=settings.database_connect_timeout_seconds,
        ),
        ttl_seconds=settings.cache_ttl_seconds,
        policy_version=settings.cache_policy_version,
    )


def create_app(
    settings: Settings | None = None,
    backend: RagBackend | None = None,
    store: SessionStore | None = None,
    cache: SemanticCacheService | None = None,
) -> FastAPI:
    settings = settings or get_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        redis: Redis | None = (
            Redis.from_url(
                settings.redis_url,
                decode_responses=True,
                socket_timeout=settings.redis_socket_timeout_seconds,
                socket_connect_timeout=settings.redis_socket_connect_timeout_seconds,
            )
            if settings.redis_url
            else None
        )
        app.state.store = store or build_session_store(settings, redis)
        app.state.cache = cache or build_cache(settings, redis)
        app.state.redis_enabled = redis is not None
        async with httpx.AsyncClient(timeout=settings.backend_timeout_seconds) as http:
            app.state.http = http
            app.state.backend = backend or BackendClient(http, settings.backend_internal_url)
            try:
                yield
            finally:
                if redis is not None:
                    await redis.aclose()

    app = FastAPI(title="SmartSales RAG Gateway", version=settings.app_version, lifespan=lifespan)
    app.state.settings = settings
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_allowed_origins,
        allow_methods=["GET", "POST", "DELETE", "OPTIONS"],
        allow_headers=["Content-Type", "Accept"],
        expose_headers=["Retry-After"],
    )
    app.add_exception_handler(RedisError, redis_unavailable)
    app.include_router(router)
    return app


app = create_app()
