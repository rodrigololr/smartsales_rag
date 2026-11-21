"""Observe production orchestration and SQL recommendations without reference leakage."""

import logging
import re
from collections.abc import AsyncIterator, Sequence
from contextlib import asynccontextmanager
from dataclasses import replace
from typing import Protocol, cast

import tiktoken
from app.config import Settings
from app.generation.prompt import Message
from app.main import TOKEN_COUNT_ENCODING
from app.models.schemas import CatalogProduct, RagRequest, RetrievedChunk
from app.rag.orchestrator import ChatModel, ChunkSearcher, Embedder, ProductReader, RAGOrchestrator
from app.recommendation.service import (
    CrossSellRelation,
    RecommendationCatalog,
    RecommendationService,
)

from .corpus import Corpus
from .models import ObservedOffer, ObservedTurn, PipelineInput


class Pipeline(Protocol):
    async def run(self, request: PipelineInput) -> ObservedTurn: ...


class ObservedCatalog:
    """Transparent SQL tracing; controlled depletion affects every purchase read."""

    def __init__(
        self,
        reader: ProductReader,
        source: RecommendationCatalog,
        request: PipelineInput,
        products: dict[str, CatalogProduct] | None = None,
    ) -> None:
        self.reader, self.source, self.request = reader, source, request
        self.products = products if products is not None else {}

    def _record(self, product: CatalogProduct | None) -> CatalogProduct | None:
        if product is not None:
            if product.sku in self.request.stock_overrides:
                # Evaluation-only scenario, never an UPDATE against the production database.
                product = product.model_copy(update={"stock_quantity": 0})
            self.products[product.sku] = product
        return product

    async def get_product(self, sku: str) -> CatalogProduct | None:
        return self._record(await self.reader.get_product(sku))

    @asynccontextmanager
    async def snapshot(self) -> AsyncIterator["ObservedCatalog"]:
        async with self.source.snapshot() as source:
            yield ObservedCatalog(self.reader, source, self.request, self.products)

    async def current_product(self, sku: str) -> CatalogProduct | None:
        return self._record(await self.source.current_product(sku))

    async def upsell_candidates(self, base: CatalogProduct) -> list[CatalogProduct]:
        return [
            cast(CatalogProduct, self._record(p)) for p in await self.source.upsell_candidates(base)
        ]

    async def cross_sell_relations(self, sku: str) -> list[CrossSellRelation]:
        return [
            replace(r, product=cast(CatalogProduct, self._record(r.product)))
            for r in await self.source.cross_sell_relations(sku)
        ]

    async def max_similarities(
        self, skus: Sequence[str], embedding: Sequence[float]
    ) -> dict[str, float]:
        return await self.source.max_similarities(skus, embedding)


class ObservedChat:
    def __init__(self, model: ChatModel) -> None:
        self.model, self.calls = model, 0
        self.contexts: list[str] = []

    async def stream(self, messages: Sequence[Message]) -> AsyncIterator[str]:
        self.calls += 1
        system = messages[0]["content"] if messages and messages[0]["role"] == "system" else ""
        # Only the actual production evidence blocks, never the user question or fixture answer.
        self.contexts = [
            value.strip()
            for tag in ("CATALOGO_SQL", "CHUNKS_MANUAIS", "RECOMENDACOES_SQL")
            for value in re.findall(rf"<{tag}>(.*?)</{tag}>", system, re.DOTALL)
            if value.strip() not in {"", "[]"}
        ]
        async for delta in self.model.stream(messages):
            yield delta


class ObservedOrchestrator(RAGOrchestrator):
    """Tracing only: production filtering still decides which chunks are used."""

    retrieved: list[RetrievedChunk]

    async def _retrieve(self, request: RagRequest) -> tuple[list[float], list[RetrievedChunk]]:
        embedding, self.retrieved = await super()._retrieve(request)
        return embedding, self.retrieved


class BlockedSentences(logging.Handler):
    def __init__(self, sku: str) -> None:
        super().__init__()
        self.sku, self.count = sku, 0

    def emit(self, record: logging.LogRecord) -> None:
        if str(record.msg).startswith("gout_blocked_sentence") and getattr(record, "sku", None) == self.sku:
            self.count += 1


class ProductionPipeline:
    def __init__(
        self,
        reader: ProductReader,
        searcher: ChunkSearcher,
        embedder: Embedder,
        model: ChatModel,
        settings: Settings,
        corpus: Corpus,
        recommendation_catalog: RecommendationCatalog,
    ) -> None:
        self.reader, self.searcher, self.embedder = reader, searcher, embedder
        self.model, self.settings, self.corpus = model, settings, corpus
        self.recommendation_catalog = recommendation_catalog
        self.encoding = tiktoken.get_encoding(TOKEN_COUNT_ENCODING)

    async def run(self, request: PipelineInput) -> ObservedTurn:
        if any(stock != 0 for stock in request.stock_overrides.values()):
            raise ValueError("Only explicit depletion scenarios are supported")
        catalog = ObservedCatalog(self.reader, self.recommendation_catalog, request)
        model = ObservedChat(self.model)
        orchestrator = ObservedOrchestrator(
            catalog,
            self.searcher,
            self.embedder,
            model,
            self.settings,
            count_tokens=lambda text: len(self.encoding.encode(text)),
            recommender=RecommendationService(catalog),
        )
        orchestrator.retrieved = []
        turn = ObservedTurn(action="ERROR")
        blocked = BlockedSentences(request.sku)
        logger = logging.getLogger("app.rag.orchestrator")
        logger.addHandler(blocked)
        previous_level = logger.level
        logger.setLevel(logging.INFO)  # blocked sentences are logged at INFO
        try:
            async for event in orchestrator.stream(
                RagRequest(
                    sku=request.sku,
                    question=request.question,
                    preferred_voltage=request.requested_voltage,
                )
            ):
                self._observe_event(turn, event)
            if not turn.events or turn.events[-1] != "end":
                raise ValueError("EOF without mandatory end")
            if turn.action == "ERROR" and not turn.errors and turn.answer.strip():
                turn.action = "ANSWER"
            if turn.action == "ERROR" and not turn.errors:
                turn.errors.append("Turn ended without an answer or classified fallback")
            turn.retrieved = [self.corpus.observed(chunk) for chunk in orchestrator.retrieved]
            if not set(turn.citation_chunk_ids) <= {c.chunk_id for c in turn.retrieved}:
                raise ValueError("Published citation was not retrieved in this turn")
        except Exception as error:
            turn.action = "ERROR"
            turn.errors.append(f"Pipeline failed: {type(error).__name__}")
        finally:
            logger.removeHandler(blocked)
            logger.setLevel(previous_level)
            turn.blocked_sentences = blocked.count
        turn.products, turn.generation_calls = catalog.products, model.calls
        turn.evidence_contexts = model.contexts
        return turn

    def _observe_event(self, turn: ObservedTurn, event: dict[str, object]) -> None:
        kind = str(event["event"])
        if "end" in turn.events or (kind == "token" and "error" in turn.events):
            raise ValueError("Event violates production stream order")
        if kind not in {"token", "citations", "recommendations", "error", "end"}:
            raise ValueError("Unknown production event")
        if kind == "token" and any(k in turn.events for k in ("citations", "recommendations")):
            raise ValueError("Token after terminal content")
        if kind == "citations" and ("token" not in turn.events or "citations" in turn.events):
            raise ValueError("Invalid citations order")
        if kind == "recommendations" and (not turn.events or "recommendations" in turn.events):
            raise ValueError("Invalid recommendations order")
        if kind == "error" and "error" in turn.events:
            raise ValueError("Duplicate error")
        turn.events.append(kind)
        payload = cast(dict[str, object], event["data"])
        if kind == "token":
            turn.answer += str(payload["delta"])
            turn.emitted_content += str(payload["delta"])
        elif kind == "citations":
            self._citations(turn, cast(list[dict[str, object]], payload["citations"]))
        elif kind == "recommendations":
            turn.offers = [
                ObservedOffer.model_validate(
                    {
                        "sku": item["sku"],
                        "role": item["recommendation_type"],
                        "price": item["price"],
                        "stock_quantity": item["stock_quantity"],
                        "voltage": item["voltage"],
                    }
                )
                for item in cast(list[dict[str, object]], payload["products"])
            ]
        elif kind == "error":
            # Match the Gateway: error replaces partial content and clears citations/cards.
            turn.answer = str(payload["fallback_message"])
            turn.emitted_content += "\n" + turn.answer
            turn.citations, turn.citation_chunk_ids, turn.offers = [], [], []
            code = payload.get("code")
            turn.action = (
                "REFUSE"
                if code == "GUARDRAIL_BLOCKED"
                else "FALLBACK"
                if code == "LOW_SIMILARITY_FALLBACK"
                else "ERROR"
            )
            if "token" in turn.events[:-1]:
                turn.action = "ERROR"
            if turn.action == "ERROR":
                turn.errors.append(f"Pipeline error: {code}")

    def _citations(self, turn: ObservedTurn, items: list[dict[str, object]]) -> None:
        for item in items:
            uid = str(item["chunk_id"])
            key = next((k for k, value in self.corpus.database_ids.items() if value == uid), None)
            if key is None:
                raise ValueError("Published citation UUID outside verified corpus")
            entry = self.corpus.entries[key]
            observed = (str(item["sku"]), str(item["manual_title"]), int(str(item["page_number"])))
            if observed != (entry.reference.sku, entry.title, entry.reference.page_number):
                raise ValueError("Citation metadata contradicts its ingested UUID")
            turn.citation_chunk_ids.append(uid)
            turn.citations.append(observed)
