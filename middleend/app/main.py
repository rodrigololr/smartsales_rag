"""Public API gateway (:8000) for the MVP chat."""

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.clients.backend import BackendClient
from app.config import Settings, get_settings
from app.routes.chat import RagBackend, router
from app.sessions.store import SessionStore

logging.basicConfig(level=logging.INFO)


def create_app(settings: Settings | None = None, backend: RagBackend | None = None) -> FastAPI:
    settings = settings or get_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        async with httpx.AsyncClient(timeout=settings.backend_timeout_seconds) as http:
            app.state.http = http
            app.state.backend = backend or BackendClient(http, settings.backend_internal_url)
            yield

    app = FastAPI(title="SmartSales RAG Gateway", version=settings.app_version, lifespan=lifespan)
    app.state.settings = settings
    app.state.store = SessionStore(ttl_seconds=settings.session_ttl_seconds)
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
