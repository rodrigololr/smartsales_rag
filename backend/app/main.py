"""Internal RAG worker (:8001), called only by the middle-end.

POST /internal/rag/stream answers with NDJSON: one internal M02 event per line.
"""

import json
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from functools import lru_cache

import tiktoken
from fastapi import Depends, FastAPI
from fastapi.responses import StreamingResponse

from app.clients.openai_client import OpenAIChatModel, OpenAIEmbedder, make_client
from app.config import get_settings
from app.consultant.service import ConsultantOrchestrator
from app.db.consultant_repository import PostgresConsultantCatalog
from app.db.repository import PostgresCatalog
from app.models.schemas import ConsultantRequest
from app.rag.orchestrator import InternalEvent, RAGOrchestrator
from app.recommendation.service import RecommendationService

TOKEN_COUNT_ENCODING = "o200k_base"  # gpt-4o family tokenizer

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    # The threshold is calibrated per embedding model (RN02): make the pairing visible.
    settings = get_settings()
    logger.info(
        "rag_settings similarity_threshold=%s embedding_model=%s llm_model=%s llm_fallback_model=%s",
        settings.similarity_threshold, settings.embedding_model, settings.llm_model,
        settings.llm_fallback_model or "-",
    )
    yield


app = FastAPI(title="SmartSales RAG Backend (interno)", lifespan=lifespan)


@lru_cache
def get_orchestrator() -> ConsultantOrchestrator:
    settings = get_settings()
    client = make_client(settings)
    catalog = PostgresCatalog(settings.database_url)
    consultant_catalog = PostgresConsultantCatalog(settings.database_url)
    encoding = tiktoken.get_encoding(TOKEN_COUNT_ENCODING)
    embedder = OpenAIEmbedder(
        client,
        model=settings.embedding_model,
        dimensions=settings.embedding_dimensions,
        batch_size=settings.embedding_batch_size,
        timeout=settings.embedding_timeout_seconds,
    )
    chat_model = OpenAIChatModel(
        client,
        model=settings.llm_model,
        temperature=settings.llm_temperature,
        max_tokens=settings.llm_max_tokens,
        first_token_timeout=settings.llm_first_token_timeout_seconds,
        first_token_attempts=settings.llm_first_token_attempts,
        fallback_model=settings.llm_fallback_model,
    )
    def count_tokens(text: str) -> int:
        return len(encoding.encode(text))

    rag = RAGOrchestrator(
        catalog,
        catalog,
        embedder,
        chat_model,
        settings,
        count_tokens=count_tokens,
        recommender=RecommendationService(catalog),
    )
    return ConsultantOrchestrator(
        consultant_catalog,
        embedder,
        chat_model,
        settings,
        rag=rag,
        count_tokens=count_tokens,
    )


async def _ndjson(events: AsyncIterator[InternalEvent]) -> AsyncIterator[str]:
    async for event in events:
        yield json.dumps(event, ensure_ascii=False) + "\n"


@app.post("/internal/rag/stream")
async def rag_stream(
    request: ConsultantRequest,
    orchestrator: ConsultantOrchestrator = Depends(get_orchestrator),
) -> StreamingResponse:
    return StreamingResponse(_ndjson(orchestrator.stream(request)), media_type="application/x-ndjson")


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}
