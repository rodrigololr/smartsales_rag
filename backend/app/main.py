"""Internal RAG worker (:8001), called only by the middle-end.

POST /internal/rag/stream answers with NDJSON: one internal M02 event per line.
"""

import json
import logging
from collections.abc import AsyncIterator
from functools import lru_cache

import tiktoken
from fastapi import Depends, FastAPI
from fastapi.responses import StreamingResponse
from openai import AsyncOpenAI

from app.clients.openai_client import OpenAIChatModel, OpenAIEmbedder
from app.config import get_settings
from app.db.repository import PostgresCatalog
from app.models.schemas import RagRequest
from app.rag.orchestrator import InternalEvent, RAGOrchestrator

TOKEN_COUNT_ENCODING = "o200k_base"  # gpt-4o family tokenizer

logging.basicConfig(level=logging.INFO)
app = FastAPI(title="SmartSales RAG Backend (interno)")


@lru_cache
def get_orchestrator() -> RAGOrchestrator:
    settings = get_settings()
    client = AsyncOpenAI(api_key=settings.openai_api_key, timeout=settings.llm_timeout_seconds)
    catalog = PostgresCatalog(settings.database_url)
    encoding = tiktoken.get_encoding(TOKEN_COUNT_ENCODING)
    return RAGOrchestrator(
        catalog,
        catalog,
        OpenAIEmbedder(
            client,
            model=settings.embedding_model,
            dimensions=settings.embedding_dimensions,
            batch_size=settings.embedding_batch_size,
        ),
        OpenAIChatModel(
            client,
            model=settings.llm_model,
            temperature=settings.llm_temperature,
            max_tokens=settings.llm_max_tokens,
        ),
        settings,
        count_tokens=lambda text: len(encoding.encode(text)),
    )


async def _ndjson(events: AsyncIterator[InternalEvent]) -> AsyncIterator[str]:
    async for event in events:
        yield json.dumps(event, ensure_ascii=False) + "\n"


@app.post("/internal/rag/stream")
async def rag_stream(
    request: RagRequest, orchestrator: RAGOrchestrator = Depends(get_orchestrator)
) -> StreamingResponse:
    return StreamingResponse(_ndjson(orchestrator.stream(request)), media_type="application/x-ndjson")


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}
