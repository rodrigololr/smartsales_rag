"""Public API gateway (:8000) for the MVP chat."""

import asyncio
import logging
from collections.abc import AsyncIterator
from contextlib import AsyncExitStack, asynccontextmanager, suppress

import httpx
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from psycopg import Error as DatabaseError
from redis.asyncio import Redis
from redis.asyncio.retry import Retry
from redis.backoff import NoBackoff
from redis.exceptions import RedisError

from app.cache.redis_storage import RedisCacheStorage
from app.cache.service import SemanticCacheService
from app.clients.backend import BackendClient
from app.config import Settings, get_settings
from app.repositories.products import PostgresProductSnapshots
from app.routes.chat import RagBackend, error_response, router
from app.sessions.cache import SessionCache
from app.sessions.postgres_store import PostgresSessionStore
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


async def storage_unavailable(request: Request, failure: Exception) -> JSONResponse:
    logger.error(
        "session_database_unavailable",
        extra={"session_id": getattr(request.state, "session_id", None)},
    )
    return error_response(
        503, "SERVICE_UNAVAILABLE", "Serviço temporariamente indisponível. Tente novamente."
    )


async def maintain_sessions(store: PostgresSessionStore, interval: float) -> None:
    while True:
        await asyncio.sleep(interval)
        try:
            await store.maintain()
        except DatabaseError:
            logger.error("session_maintenance_failed")


async def stop_maintenance(task: asyncio.Task[None]) -> None:
    task.cancel()
    with suppress(asyncio.CancelledError):
        await task


def build_session_store(settings: Settings, redis: Redis | None) -> SessionStore:
    if redis is None:
        return InMemorySessionStore(
            ttl_seconds=settings.session_ttl_seconds,
            history_max_messages=settings.session_history_max_messages,
            lock_ttl_seconds=settings.session_lock_ttl_seconds,
        )
    if settings.database_url:
        return PostgresSessionStore(
            settings.database_url,
            SessionCache(redis, settings.session_ttl_seconds, settings.session_lock_ttl_seconds),
            ttl_seconds=settings.session_ttl_seconds,
            history_max_messages=settings.session_history_max_messages,
            lock_ttl_seconds=settings.session_lock_ttl_seconds,
            connect_timeout_seconds=settings.session_db_connect_timeout_seconds,
            query_timeout_ms=settings.session_db_query_timeout_ms,
        )
    logger.warning("redis_only_sessions_development_mode")
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
        async with AsyncExitStack() as resources:
            redis: Redis | None = (
                Redis.from_url(
                    settings.redis_url,
                    decode_responses=True,
                    retry=Retry(NoBackoff(), 0),
                    socket_timeout=settings.redis_socket_timeout_seconds,
                    socket_connect_timeout=settings.redis_socket_connect_timeout_seconds,
                )
                if settings.redis_url and store is None
                else None
            )
            if redis is not None:
                resources.push_async_callback(redis.aclose)
            app.state.store = store or build_session_store(settings, redis)
            app.state.cache = cache or build_cache(settings, redis)
            app.state.redis_enabled = redis is not None
            if isinstance(app.state.store, PostgresSessionStore):
                await app.state.store.initialize()
                maintenance = asyncio.create_task(
                    maintain_sessions(app.state.store, settings.session_maintenance_seconds)
                )
                resources.push_async_callback(stop_maintenance, maintenance)
            http = await resources.enter_async_context(
                httpx.AsyncClient(timeout=settings.backend_timeout_seconds)
            )
            app.state.http = http
            app.state.backend = backend or BackendClient(
                http,
                settings.backend_internal_url,
                first_event_timeout_seconds=settings.backend_first_event_timeout_seconds,
            )
            yield

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
    app.add_exception_handler(DatabaseError, storage_unavailable)
    app.include_router(router)
    return app


app = create_app()
