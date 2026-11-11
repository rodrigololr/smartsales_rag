"""Public API gateway (:8000) for the MVP chat."""

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from redis.asyncio import Redis

from app.clients.backend import BackendClient
from app.config import Settings, get_settings
from app.routes.chat import RagBackend, router
from app.sessions.redis_store import RedisSessionStore
from app.sessions.store import InMemorySessionStore, SessionStore

logging.basicConfig(level=logging.INFO)


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


def create_app(
    settings: Settings | None = None,
    backend: RagBackend | None = None,
    store: SessionStore | None = None,
) -> FastAPI:
    settings = settings or get_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        redis: Redis | None = (
            Redis.from_url(settings.redis_url, decode_responses=True)
            if settings.redis_url and store is None
            else None
        )
        app.state.store = store or build_session_store(settings, redis)
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
    app.include_router(router)
    return app


app = create_app()
