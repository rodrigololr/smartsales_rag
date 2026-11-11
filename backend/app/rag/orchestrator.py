"""Single-product RAG turn: G-IN -> retrieval (G-RET) -> generation -> G-OUT.

Yields the internal M02 protocol consumed by the middle-end: approved `token`
sentences, `citations`, `recommendations` (B04 cards read from SQL), `error` and the
mandatory `end` marker.
"""

import logging
import re
from collections.abc import AsyncIterator, Callable, Sequence
from typing import Protocol

from app.clients.openai_client import LLMUnavailableError
from app.config import Settings
from app.generation.prompt import Message, build_messages, catalog_block
from app.guardrails.input import is_prompt_injection
from app.guardrails.output import Claim, SentenceBuffer, technical_claims, unsupported_claims
from app.models.schemas import CatalogProduct, RagRequest, RetrievedChunk
from app.recommendation.intent import wants_upgrade
from app.recommendation.models import Voltage

logger = logging.getLogger(__name__)

InternalEvent = dict[str, object]

LOW_SIMILARITY_MESSAGE = (
    "Essa especificação não consta no manual técnico oficial nem no catálogo ativo "
    "deste produto. Posso ajudar com outra dúvida sobre ele?"
)
UNAVAILABLE_PRODUCT_MESSAGE = "Este produto não está disponível no catálogo ativo no momento."
BLOCKED_MESSAGE = (
    "Só posso responder dúvidas técnicas sobre este produto, com base no manual e no "
    "catálogo oficial."
)
LLM_UNAVAILABLE_MESSAGE = "O consultor está indisponível no momento. Tente novamente em instantes."
MISSING_EVIDENCE_NOTICE = (
    "Essa especificação específica não consta no manual técnico oficial deste modelo. "
)
EXCERPT_MAX_CHARS = 400
_CITATION_MARK = re.compile(r"\[Fonte:\s*(.+?),\s*p\.\s*(\d+)\]")
ANSWER_INTENT = "TECHNICAL_QA"


class ProductReader(Protocol):
    async def get_product(self, sku: str) -> CatalogProduct | None: ...


class ChunkSearcher(Protocol):
    async def search(
        self, sku: str, embedding: Sequence[float], limit: int
    ) -> list[RetrievedChunk]: ...


class Embedder(Protocol):
    async def embed(self, texts: Sequence[str]) -> list[list[float]]: ...


class ChatModel(Protocol):
    def stream(self, messages: Sequence[Message]) -> AsyncIterator[str]: ...


class Recommender(Protocol):
    async def cards(
        self,
        base: CatalogProduct,
        *,
        query_embedding: Sequence[float] | None,
        allow_upsell: bool,
        requested_voltage: Voltage | None = None,
    ) -> list[dict[str, object]]: ...


def _error(code: str, message: str) -> InternalEvent:
    return {"event": "error", "data": {"code": code, "recoverable": True, "fallback_message": message}}


def _end(tokens_used: int, intent: str) -> InternalEvent:
    return {"event": "end", "data": {"tokens_used": tokens_used, "intent": intent}}


def _token(delta: str) -> InternalEvent:
    return {"event": "token", "data": {"delta": delta}}


def _cited_chunks(published: str, chunks: list[RetrievedChunk]) -> list[RetrievedChunk]:
    """Chunks the answer actually cites; all retrieved evidence if it cites none."""
    marks = {(title.strip(), int(page)) for title, page in _CITATION_MARK.findall(published)}
    cited = [c for c in chunks if (c.manual_title, c.page_number) in marks]
    return cited or chunks


def _citation(chunk: RetrievedChunk) -> dict[str, object]:
    # Stored content starts with the [PRODUTO: ...] context header line.
    excerpt = chunk.content.split("\n", 1)[-1].strip()[:EXCERPT_MAX_CHARS]
    return {
        "chunk_id": str(chunk.chunk_id),
        "sku": chunk.sku,
        "manual_title": chunk.manual_title,
        "page_number": chunk.page_number,
        "section_title": chunk.section_title,
        "similarity_score": round(chunk.similarity_score, 4),
        "excerpt": excerpt,
    }


class RAGOrchestrator:
    def __init__(
        self,
        products: ProductReader,
        chunks: ChunkSearcher,
        embedder: Embedder,
        chat_model: ChatModel,
        settings: Settings,
        *,
        count_tokens: Callable[[str], int],
        recommender: Recommender | None = None,
    ) -> None:
        self._recommender = recommender
        self._products = products
        self._chunks = chunks
        self._embedder = embedder
        self._chat_model = chat_model
        self._settings = settings
        self._count_tokens = count_tokens

    async def stream(self, request: RagRequest) -> AsyncIterator[InternalEvent]:
        product = await self._products.get_product(request.sku)
        if product is None or not product.is_active:
            yield _error("LOW_SIMILARITY_FALLBACK", UNAVAILABLE_PRODUCT_MESSAGE)
            yield _end(0, "UNAVAILABLE_PRODUCT")
            return
        if is_prompt_injection(request.question):
            logger.warning("guardrail_blocked", extra={"sku": request.sku})
            yield _error("GUARDRAIL_BLOCKED", BLOCKED_MESSAGE)
            yield _end(0, "BLOCKED")
            return
        try:
            query_embedding, evidence_chunks = await self._retrieve(request)
        except LLMUnavailableError:
            logger.exception("embedding_unavailable", extra={"sku": request.sku})
            yield _error("LLM_UNAVAILABLE", LLM_UNAVAILABLE_MESSAGE)
            for event in await self._recommendations(request, product, None, substitutes=True):
                yield event
            yield _end(0, ANSWER_INTENT)
            return
        if not evidence_chunks:
            yield _error("LOW_SIMILARITY_FALLBACK", LOW_SIMILARITY_MESSAGE)
            for event in await self._similar_in_stock(request, product, query_embedding):
                yield event
            yield _end(0, "LOW_SIMILARITY")
            return
        async for event in self._generate(request, product, evidence_chunks, query_embedding):
            yield event

    async def _retrieve(self, request: RagRequest) -> tuple[list[float], list[RetrievedChunk]]:
        [query_embedding] = await self._embedder.embed([request.question])
        found = await self._chunks.search(
            request.sku, query_embedding, self._settings.retrieval_top_k
        )
        evidence = [c for c in found if c.similarity_score >= self._settings.similarity_threshold]
        return query_embedding, evidence

    async def _recommendations(
        self,
        request: RagRequest,
        product: CatalogProduct,
        query_embedding: Sequence[float] | None,
        *,
        substitutes: bool,
    ) -> list[InternalEvent]:
        """Cards for this turn. `substitutes` (fallback turns) always opens the upsell
        branch; an answered turn opens it only for a sold-out base or a stated need."""
        if self._recommender is None:
            return []
        allow_upsell = (
            substitutes or product.stock_quantity <= 0 or wants_upgrade(request.question)
        )
        cards = await self._recommender.cards(
            product,
            query_embedding=query_embedding,
            allow_upsell=allow_upsell,
            requested_voltage=request.preferred_voltage,
        )
        return [{"event": "recommendations", "data": {"products": cards}}] if cards else []

    async def _similar_in_stock(
        self, request: RagRequest, product: CatalogProduct, query_embedding: Sequence[float]
    ) -> list[InternalEvent]:
        return await self._recommendations(request, product, query_embedding, substitutes=True)

    async def _generate(
        self,
        request: RagRequest,
        product: CatalogProduct,
        chunks: list[RetrievedChunk],
        query_embedding: Sequence[float],
    ) -> AsyncIterator[InternalEvent]:
        messages = build_messages(
            product,
            chunks,
            request.history,
            request.question,
            history_limit=self._settings.history_max_messages,
        )
        evidence = technical_claims(
            catalog_block(product) + "\n" + "\n".join(c.content for c in chunks)
        )
        gate = _PublicationGate(evidence, request.sku)
        draft: list[str] = []
        published: list[str] = []
        buffer = SentenceBuffer()
        try:
            async for delta in self._chat_model.stream(messages):
                draft.append(delta)
                for sentence in buffer.feed(delta):
                    for approved in gate.review(sentence):
                        published.append(approved)
                        yield _token(approved)
        except LLMUnavailableError:
            logger.exception("llm_unavailable", extra={"sku": request.sku})
            yield _error("LLM_UNAVAILABLE", LLM_UNAVAILABLE_MESSAGE)
            for event in await self._similar_in_stock(request, product, query_embedding):
                yield event
            yield _end(0, ANSWER_INTENT)
            return
        for approved in gate.review(buffer.flush()) + gate.close():
            published.append(approved)
            yield _token(approved)
        tokens_used = self._count_tokens("".join(draft))
        if not gate.approved:
            yield _error("LOW_SIMILARITY_FALLBACK", LOW_SIMILARITY_MESSAGE)
            for event in await self._similar_in_stock(request, product, query_embedding):
                yield event
            yield _end(tokens_used, "LOW_SIMILARITY")
            return
        cited = _cited_chunks("".join(published), chunks)
        yield {"event": "citations", "data": {"citations": [_citation(c) for c in cited]}}
        for event in await self._recommendations(
            request, product, query_embedding, substitutes=False
        ):
            yield event
        yield _end(tokens_used, ANSWER_INTENT)


class _PublicationGate:
    """Publishes approved sentences; a blocked sentence becomes the missing-evidence
    notice, emitted only next to approved text so a fully rejected draft publishes nothing."""

    def __init__(self, evidence: set[Claim], sku: str) -> None:
        self._evidence = evidence
        self._sku = sku
        self._notice_pending = False
        self._notice_sent = False
        self.approved = 0

    def review(self, sentence: str) -> list[str]:
        if not sentence.strip():
            return [sentence] if self.approved else []
        rejected = unsupported_claims(sentence, self._evidence)
        if rejected:
            logger.warning("gout_blocked_sentence", extra={"sku": self._sku, "claims": sorted(rejected)})
            self._notice_pending = True
            return []
        self.approved += 1
        return [*self._notice(), sentence]

    def close(self) -> list[str]:
        return self._notice() if self.approved else []

    def _notice(self) -> list[str]:
        if not self._notice_pending or self._notice_sent:
            return []
        self._notice_pending = False
        self._notice_sent = True
        return [MISSING_EVIDENCE_NOTICE]
