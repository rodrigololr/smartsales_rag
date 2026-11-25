"""Public API gateway (:8000) for chat and commerce."""

import asyncio
import logging
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
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.cache.redis_storage import RedisCacheStorage
from app.cache.service import SemanticCacheService
from app.clients.backend import BackendClient
from app.config import Settings, get_settings
from app.ratelimit import (
    CATALOG_READS_PER_IP,
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
from app.telemetry.tracing import (
    REQUEST_ID_HEADER,
    RequestIdMiddleware,
    configure_logging,
    current_trace_id,
)

configure_logging()
logger = logging.getLogger(__name__)

# /chat/stream: per session_id in the route, plus a coarse per-IP bucket here.
_CHAT_STREAM_PATH = "/api/v1/chat/stream"
_EXEMPT_IP_LIMIT_PATHS = {
    "/api/v1/health",
    "/docs",
    "/openapi.json",
    "/redoc",
}
# Read-only catalog: the Next.js SSR fetches it for every visitor from one container IP.
_CATALOG_PATH = "/api/v1/products"


def _ip_limit_exempt(request: Request) -> bool:
    return request.method == "OPTIONS" or request.url.path in _EXEMPT_IP_LIMIT_PATHS


def _catalog_read(request: Request) -> bool:
    path = request.url.path
    if request.method != "GET":
        return False
    sku = path.removeprefix(_CATALOG_PATH + "/")  # GET /products/{sku}, nothing deeper
    return path == _CATALOG_PATH or (sku != path and sku != "" and "/" not in sku)


def _ip_bucket(request: Request) -> tuple[RateLimiter, str, int]:
    state = request.app.state
    if request.url.path == _CHAT_STREAM_PATH:
        return state.chat_ip_limiter, "ip-chat", CHAT_SESSIONS_PER_IP
    if _catalog_read(request):
        return state.catalog_ip_limiter, "ip-catalog", CATALOG_READS_PER_IP
    return state.rate_limiter, "ip", 1


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
            "trace_id": current_trace_id(),
            "details": {"errors": errors},
        }
    }
    return JSONResponse(body, status_code=422)


_HTTP_ERROR_CODES = {
    404: ("NOT_FOUND", "Recurso não encontrado."),
    405: ("METHOD_NOT_ALLOWED", "Método não permitido para este recurso."),
}


async def http_error(request: Request, failure: Exception) -> JSONResponse:
    """Router-level 404/405 (and any other HTTPException) in the REST error envelope."""
    status = failure.status_code if isinstance(failure, StarletteHTTPException) else 500
    headers = failure.headers if isinstance(failure, StarletteHTTPException) else None
    code, message = _HTTP_ERROR_CODES.get(status, ("HTTP_ERROR", "Requisição não atendida."))
    return error_response(status, code, message, headers=headers)


async def unhandled_error(request: Request, failure: Exception) -> JSONResponse:
    """Last resort: logged with its trace_id, never a stack trace to the client."""
    trace_id = current_trace_id()
    logger.error(
        "unhandled_error",
        exc_info=failure,
        extra={"trace_id": trace_id, "session_id": getattr(request.state, "session_id", None)},
    )
    # Sent by Starlette's outermost middleware, outside RequestIdMiddleware: add the header here.
    return error_response(
        500,
        "INTERNAL_ERROR",
        "Erro interno. Tente novamente.",
        headers={REQUEST_ID_HEADER: trace_id},
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


def build_redis(settings: Settings, url: str) -> Redis:
    return Redis.from_url(
        url,
        decode_responses=True,
        retry=Retry(NoBackoff(), 0),
        socket_timeout=settings.redis_socket_timeout_seconds,
        socket_connect_timeout=settings.redis_socket_connect_timeout_seconds,
        # PING a connection idle longer than this before reusing it (Upstash/NAT drop idle TCP).
        health_check_interval=settings.redis_health_check_interval_seconds,
    )


def build_rate_limiter(
    settings: Settings, redis: Redis | None, *, per_ip_factor: int = 1
) -> RateLimiter:
    limit = settings.rate_limit_per_minute * per_ip_factor
    if redis is not None:
        return RedisRateLimiter(redis, limit=limit, window_seconds=RATE_LIMIT_WINDOW_SECONDS)
    return InMemoryRateLimiter(limit=limit, window_seconds=RATE_LIMIT_WINDOW_SECONDS)


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
            redis = (
                build_redis(settings, settings.redis_url)
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
            app.state.catalog_ip_limiter = build_rate_limiter(
                settings, redis, per_ip_factor=CATALOG_READS_PER_IP
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
    app.state.catalog_ip_limiter = build_rate_limiter(
        settings, None, per_ip_factor=CATALOG_READS_PER_IP
    )

    @app.middleware("http")
    async def enforce_rate_limit(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        if not _ip_limit_exempt(request):
            client_ip = client_ip_from_request(
                request, trusted_proxy_hops=settings.rate_limit_trusted_proxy_hops
            )
            limiter, bucket, factor = _ip_bucket(request)
            decision = await limiter.check(f"{bucket}:{client_ip}")
            if not decision.allowed:
                return rate_limited(decision, settings.rate_limit_per_minute * factor)
        try:
            return await call_next(request)
        except Exception as failure:  # noqa: BLE001 - last resort, logged with trace_id
            # Answered here, inside CORSMiddleware, so the browser can read the envelope.
            return await unhandled_error(request, failure)

    app.state.commerce = build_commerce(settings)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_allowed_origins,
        allow_methods=["GET", "POST", "DELETE", "OPTIONS"],
        allow_headers=["Content-Type", "Accept", "X-Admin-Token", REQUEST_ID_HEADER],
        expose_headers=["Retry-After", REQUEST_ID_HEADER],
    )
    # Added last = outside CORS: counts every response, CORS preflights included (M04).
    app.add_middleware(ResponseCounter)
    # Outermost: every response, 429 and CORS preflight included, carries the request id.
    app.add_middleware(RequestIdMiddleware)
    app.add_exception_handler(RedisError, redis_unavailable)
    app.add_exception_handler(DatabaseError, storage_unavailable)
    app.add_exception_handler(RequestValidationError, validation_failed)
    app.add_exception_handler(StarletteHTTPException, http_error)
    app.add_exception_handler(Exception, unhandled_error)
    app.include_router(router)
    app.include_router(commerce_router)
    return app


app = create_app()
