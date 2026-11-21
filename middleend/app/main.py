"""Public API gateway (:8000) for chat and commerce."""

import asyncio
import logging
import uuid
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import AsyncExitStack, asynccontextmanager, suppress

import httpx
from fastapi import FastAPI, Request, Response
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
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
from app.ratelimit import (
    CHAT_SESSIONS_PER_IP,
    RATE_LIMIT_WINDOW_SECONDS,
    InMemoryRateLimiter,
    RateLimiter,
    RedisRateLimiter,
    client_ip_from_request,
)
from app.repositories.commerce import PostgresCommerce
from app.repositories.products import PostgresProductSnapshots
from app.routes.chat import RagBackend, error_response, rate_limited, router
from app.routes.commerce import router as commerce_router
from app.sessions.cache import SessionCache
from app.sessions.postgres_store import PostgresSessionStore
from app.sessions.redis_store import RedisSessionStore
from app.sessions.store import InMemorySessionStore, SessionStore
from app.telemetry.http_errors import ResponseCounter

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# /chat/stream: per session_id in the route, plus a coarse per-IP bucket here.
_CHAT_STREAM_PATH = "/api/v1/chat/stream"
_EXEMPT_IP_LIMIT_PATHS = {
    "/api/v1/health",
    "/docs",
    "/openapi.json",
    "/redoc",
}


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


async def validation_failed(request: Request, failure: Exception) -> JSONResponse:
    # jsonable_encoder: Pydantic puts non-JSON values (e.g. Decimal limits) in `ctx`.
    # `input` is dropped so the envelope never echoes the customer's message back.
    errors = (
        [
            {key: value for key, value in error.items() if key != "input"}
            for error in jsonable_encoder(failure.errors())
        ]
        if isinstance(failure, RequestValidationError)
        else []
    )
    body = {
        "error": {
            "code": "VALIDATION_ERROR",
            "message": "Payload de requisição inválido.",
            "trace_id": str(uuid.uuid4()),
            "details": {"errors": errors},
        }
    }
    return JSONResponse(body, status_code=422)


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


def build_rate_limiter(
    settings: Settings, redis: Redis | None, *, per_ip_factor: int = 1
) -> RateLimiter:
    limit = settings.rate_limit_per_minute * per_ip_factor
    if redis is not None:
        return RedisRateLimiter(redis, limit=limit, window_seconds=RATE_LIMIT_WINDOW_SECONDS)
    return InMemoryRateLimiter(limit=limit, window_seconds=RATE_LIMIT_WINDOW_SECONDS)


def build_commerce(settings: Settings) -> PostgresCommerce | None:
    if not settings.database_url:
        return None
    return PostgresCommerce(
        settings.database_url,
        decrement_stock=settings.checkout_decrement_stock,
        session_ttl_seconds=settings.session_ttl_seconds,
        connect_timeout_seconds=settings.database_connect_timeout_seconds,
        query_timeout_ms=settings.session_db_query_timeout_ms,
    )


def create_app(
    settings: Settings | None = None,
    backend: RagBackend | None = None,
    store: SessionStore | None = None,
    cache: SemanticCacheService | None = None,
    rate_limiter: RateLimiter | None = None,
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
            app.state.rate_limiter = rate_limiter or build_rate_limiter(settings, redis)
            app.state.chat_ip_limiter = build_rate_limiter(
                settings, redis, per_ip_factor=CHAT_SESSIONS_PER_IP
            )
            app.state.redis_enabled = redis is not None
            app.state.redis = redis  # INCR catalog:version on mock checkout (M05)
            if isinstance(app.state.store, PostgresSessionStore):
                await app.state.store.initialize()
                maintenance = asyncio.create_task(
                    maintain_sessions(app.state.store, settings.session_maintenance_seconds)
                )
                resources.push_async_callback(stop_maintenance, maintenance)
            # After the session schema: feedback/checkout reference chat_messages.
            if app.state.commerce is not None and not await app.state.commerce.initialize():
                logger.warning("commerce_schema_waiting_for_products_ingestion")
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
    app.state.rate_limiter = rate_limiter or build_rate_limiter(settings, None)
    app.state.chat_ip_limiter = build_rate_limiter(
        settings, None, per_ip_factor=CHAT_SESSIONS_PER_IP
    )

    @app.middleware("http")
    async def enforce_rate_limit(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        if request.method != "OPTIONS" and request.url.path not in _EXEMPT_IP_LIMIT_PATHS:
            client_ip = client_ip_from_request(
                request, trusted_proxy_hops=settings.rate_limit_trusted_proxy_hops
            )
            chat = request.url.path == _CHAT_STREAM_PATH
            limiter: RateLimiter = (
                request.app.state.chat_ip_limiter if chat else request.app.state.rate_limiter
            )
            decision = await limiter.check(f"{'ip-chat' if chat else 'ip'}:{client_ip}")
            if not decision.allowed:
                factor = CHAT_SESSIONS_PER_IP if chat else 1
                return rate_limited(decision, settings.rate_limit_per_minute * factor)
        return await call_next(request)

    app.state.commerce = build_commerce(settings)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_allowed_origins,
        allow_methods=["GET", "POST", "DELETE", "OPTIONS"],
        allow_headers=["Content-Type", "Accept", "X-Admin-Token"],
        expose_headers=["Retry-After"],
    )
    # Added last = outside CORS: counts every response, CORS preflights included (M04).
    app.add_middleware(ResponseCounter)
    app.add_exception_handler(RedisError, redis_unavailable)
    app.add_exception_handler(DatabaseError, storage_unavailable)
    app.add_exception_handler(RequestValidationError, validation_failed)
    app.include_router(router)
    app.include_router(commerce_router)
    return app


app = create_app()
