"""Public API gateway (:8000) for chat and commerce."""

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from redis.asyncio import Redis

from app.clients.backend import BackendClient
from app.config import Settings, get_settings
from app.repositories.commerce import PostgresCommerce
from app.routes.chat import RagBackend, router
from app.routes.commerce import router as commerce_router
from app.sessions.store import SessionStore

logging.basicConfig(level=logging.INFO)
REDIS_TIMEOUT_SECONDS = 2.0


def create_app(settings: Settings | None = None, backend: RagBackend | None = None) -> FastAPI:
    settings = settings or get_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        if app.state.commerce is not None:
            await app.state.commerce.initialize()
        cache = (
            Redis.from_url(
                settings.redis_url,
                socket_timeout=REDIS_TIMEOUT_SECONDS,
                socket_connect_timeout=REDIS_TIMEOUT_SECONDS,
            )
            if settings.redis_url
            else None
        )
        app.state.catalog_cache = cache
        async with httpx.AsyncClient(timeout=settings.backend_timeout_seconds) as http:
            app.state.http = http
            app.state.backend = backend or BackendClient(http, settings.backend_internal_url)
            try:
                yield
            finally:
                if cache is not None:
                    await cache.aclose()

    app = FastAPI(title="SmartSales RAG Gateway", version=settings.app_version, lifespan=lifespan)
    app.state.settings = settings
    app.state.store = SessionStore(ttl_seconds=settings.session_ttl_seconds)
    app.state.commerce = (
        PostgresCommerce(settings.database_url, decrement_stock=settings.checkout_decrement_stock)
        if settings.database_url
        else None
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_allowed_origins,
        allow_methods=["GET", "POST", "DELETE", "OPTIONS"],
        allow_headers=["Content-Type", "Accept"],
        expose_headers=["Retry-After"],
    )
    app.include_router(router)
    app.include_router(commerce_router)
    return app


app = create_app()
