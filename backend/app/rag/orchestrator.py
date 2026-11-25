"""Product-context RAG turn with SQL-backed consultative options: G-IN -> retrieval (G-RET) -> generation -> G-OUT.

Yields the internal M02 protocol consumed by the middle-end: approved `token`
sentences, `citations`, `recommendations` (B04 cards read from SQL), `error` and the
mandatory `end` marker.
"""

import asyncio
import logging
import re
from collections.abc import AsyncIterator, Callable, Coroutine, Sequence
from decimal import Decimal
from typing import Any, Protocol, TypeVar

from pydantic import ValidationError

from app.clients.openai_client import LLMUnavailableError
from app.config import Settings
from app.generation.prompt import Message, build_messages
from app.guardrails.input import is_prompt_injection
from app.guardrails.output import SentenceBuffer, technical_claims
from app.guardrails.publication import CITATION_MARK, ConsultativeVerifier, normalized_words
from app.models.schemas import CatalogProduct, ProductRecommendation, RagRequest, RetrievedChunk
from app.recommendation.cards import option_facts
from app.recommendation.engine import UPSELL_MAX_PRICE_INCREASE
from app.recommendation.intent import asks_catalog_voltage, only_consulted_product, wants_upgrade
from app.recommendation.models import Voltage

logger = logging.getLogger(__name__)

InternalEvent = dict[str, object]
_First = TypeVar("_First")
_Second = TypeVar("_Second")

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
_NOTICE_WORDS = normalized_words(MISSING_EVIDENCE_NOTICE)
NO_ALTERNATIVE_MESSAGE = (
    "Não há outra opção em estoque no catálogo ativo que atenda a este pedido (mesma "
    f"categoria, voltagem compatível e até +{UPSELL_MAX_PRICE_INCREASE:.0%} do preço)."
)
EXCERPT_MAX_CHARS = 400
BLOCKED_SENTENCE_LOG_MAX_CHARS = 200  # model output only; enough to diagnose a G-OUT drop
REJECTED_DRAFT_LOG_MAX_CHARS = 1000
ANSWER_INTENT = "TECHNICAL_QA"
_DIRECT_SPEC = re.compile(
    r"(?:qual (?:e )?(?:a |o )?|informe (?:a |o )?)"
    r"(?P<fact>pressao|diametro|tamanho)(?P<subject>(?: [a-z0-9]+)*)"
)
_SPEC_COMPOSITE = re.compile(r"\b(?:e|ou|mas|como|quando|porque)\b")
_NOMINAL_SIZE = re.compile(r"\b(\d+(?:[.,]\d+)?)\s*cm\s*$", re.IGNORECASE)
_ACCESSORY_REQUEST = re.compile(
    r"^(?:mostre|indique|recomende|quero(?: comprar| ver)?|procuro)(?: tambem)? "
    r"(?:(?:um|uma|o|a|algum|alguma) )?(?:acessorio|kit de limpeza|kit de formas)\b"
)


def _direct_spec_name(question: str) -> str | None:
    match = _DIRECT_SPEC.fullmatch(normalized_words(question))
    if match is None or _SPEC_COMPOSITE.search(match["subject"]):
        return None
    return match["fact"]


def _catalog_spec_answer(fact: str, product: CatalogProduct) -> tuple[str, str] | None:
    if fact == "pressao":
        pressure = product.specs_json.get("pressao_bar")
        if type(pressure) in (int, float) and Decimal(str(pressure)).is_finite():
            value = Decimal(str(pressure))
            if value > 0:
                number = format(value.normalize(), "f").replace(".", ",")
                return f"A pressão indicada no catálogo para {product.name} é de {number} bar.", (
                    f"pressao_bar: {pressure}"
                )
    elif product.subcategory == "Acessórios para Airfryer":
        size = _NOMINAL_SIZE.search(product.name)
        if size is not None and re.search(r"\bformas?\b", normalized_words(product.name)):
            answer = f"O catálogo informa o tamanho nominal de {size[1]} cm para {product.name}."
            return answer, f"Ficha técnica oficial do catálogo: {product.name}"
    return None


def _catalog_voltage_answer(voltage: Voltage) -> str:
    if voltage == "N/A":
        return "Segundo a ficha técnica do catálogo, a voltagem não se aplica a este produto."
    if voltage == "BIVOLT":
        return "Segundo a ficha técnica do catálogo, este produto é bivolt."
    return f"Segundo a ficha técnica do catálogo, a voltagem deste produto é {voltage[:-1]} V."


class ProductReader(Protocol):
    async def get_product(self, sku: str) -> CatalogProduct | None: ...


class ChunkSearcher(Protocol):
    async def search(
        self, sku: str, embedding: Sequence[float], limit: int
    ) -> list[RetrievedChunk]: ...

    async def catalog_sheet(self, sku: str) -> list[RetrievedChunk]: ...


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
        category: str | None = None,
        capacity_min: Decimal | None = None,
        budget_max: Decimal | None = None,
        allow_secondary: bool = True,
    ) -> list[dict[str, object]]: ...


def _error(code: str, message: str) -> InternalEvent:
    return {"event": "error", "data": {"code": code, "recoverable": True, "fallback_message": message}}


def _end(tokens_used: int, intent: str) -> InternalEvent:
    return {"event": "end", "data": {"tokens_used": tokens_used, "intent": intent}}


def _token(delta: str) -> InternalEvent:
    return {"event": "token", "data": {"delta": delta}}


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


def _planned_cards(events: list[InternalEvent]) -> list[ProductRecommendation]:
    # The recommender is injected; malformed card facts must never authorize prose.
    if not events:
        return []
    payload = events[0].get("data")
    if not isinstance(payload, dict) or not isinstance(payload.get("products"), list):
        return []
    try:
        return [ProductRecommendation.model_validate(card) for card in payload["products"]]
    except ValidationError:
        logger.exception("invalid_recommendation_evidence")
        return []


def _unbuyable(request: RagRequest, product: CatalogProduct) -> bool:
    """Sold out, or not usable on the customer's stated outlet."""
    incompatible = request.preferred_voltage is not None and product.voltage not in (
        request.preferred_voltage, "BIVOLT", "N/A"
    )
    return incompatible or product.stock_quantity <= 0


def _asks_for_alternative(request: RagRequest, product: CatalogProduct) -> bool:
    return wants_upgrade(request.question) or _unbuyable(request, product)


def _has_upsell(events: list[InternalEvent]) -> bool:
    return any(card.recommendation_type == "UPSELL" for card in _planned_cards(events))


def _explain_recommendations(
    question: str, cards: Sequence[ProductRecommendation]
) -> list[str]:
    wants_accessory = _ACCESSORY_REQUEST.search(normalized_words(question)) is not None
    wants_larger = wants_upgrade(question)
    explanations = []
    for card in cards:
        if not card.justification or card.stock_quantity <= 0:
            continue
        if (card.recommendation_type == "UPSELL" and wants_larger) or (
            card.recommendation_type == "CROSS_SELL" and wants_accessory
        ):
            explanations.append(f"SKU {card.sku} ({card.name}). {card.justification}")
    return explanations


def _alternative_answer(
    product: CatalogProduct, cards: Sequence[ProductRecommendation]
) -> list[str]:
    """SQL-only answer to an alternative request: the upsell's facts, or that none exists."""
    upsells = [card for card in cards if card.recommendation_type == "UPSELL"]
    if upsells:
        return [f"{fact}\n" for card in upsells for fact in option_facts(card)]
    return [f"{NO_ALTERNATIVE_MESSAGE}\n", *(f"{fact}\n" for fact in option_facts(product))]


async def _concurrently(
    first: Coroutine[Any, Any, _First], second: Coroutine[Any, Any, _Second]
) -> tuple[_First, _Second]:
    """Run two reads concurrently; a failure cancels the sibling and re-raises unwrapped."""
    try:
        async with asyncio.TaskGroup() as group:
            first_task, second_task = group.create_task(first), group.create_task(second)
    except BaseExceptionGroup as failures:
        raise failures.exceptions[0] from None
    return first_task.result(), second_task.result()


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
        injected = is_prompt_injection(request.question)
        catalog_voltage = asks_catalog_voltage(request.question)
        direct_spec = _direct_spec_name(request.question)
        product, query_embedding = await self._product_and_embedding(
            request, embed=not (injected or catalog_voltage or direct_spec)
        )
        if product is None or not product.is_active:
            yield _error("LOW_SIMILARITY_FALLBACK", UNAVAILABLE_PRODUCT_MESSAGE)
            yield _end(0, "UNAVAILABLE_PRODUCT")
            return
        if injected:
            logger.warning("guardrail_blocked", extra={"sku": request.sku})
            yield _error("GUARDRAIL_BLOCKED", BLOCKED_MESSAGE)
            yield _end(0, "BLOCKED")
            return
        if catalog_voltage:
            yield _token(_catalog_voltage_answer(product.voltage))
            for event in await self._recommendations(request, product, None, substitutes=False):
                yield event
            yield _end(0, ANSWER_INTENT)
            return
        if direct_spec is not None:
            fact = _catalog_spec_answer(direct_spec, product)
            if fact is not None:
                answer, source_text = fact
                sheet = await self._catalog_evidence(product.sku, source_text)
                if sheet:
                    source = sheet[0]
                    answer = f"{answer.rstrip('.')} [Fonte: {source.manual_title}, p. {source.page_number}]."
                yield _token(answer)
                if sheet:
                    yield {"event": "citations", "data": {"citations": [_citation(sheet[0])]}}
                for event in await self._recommendations(request, product, None, substitutes=False):
                    yield event
                yield _end(0, ANSWER_INTENT)
                return
            query_embedding = await self._embed_question(request)
        if query_embedding is None:
            yield _error("LLM_UNAVAILABLE", LLM_UNAVAILABLE_MESSAGE)
            for event in await self._recommendations(request, product, None, substitutes=True):
                yield event
            yield _end(0, ANSWER_INTENT)
            return
        # Independent reads: the prompt's card snapshot does not need the chunks. On a
        # fallback turn it is discarded and the substitutes branch is read instead.
        evidence_chunks, planned_events = await _concurrently(
            self._evidence(request, query_embedding),
            self._recommendations(request, product, query_embedding, substitutes=False),
        )
        if not evidence_chunks:
            yield _error("LOW_SIMILARITY_FALLBACK", LOW_SIMILARITY_MESSAGE)
            for event in await self._similar_in_stock(request, product, query_embedding):
                yield event
            yield _end(0, "LOW_SIMILARITY")
            return
        async for event in self._generate(
            request, product, evidence_chunks, query_embedding, planned_events
        ):
            yield event

    async def _product_and_embedding(
        self, request: RagRequest, *, embed: bool
    ) -> tuple[CatalogProduct | None, list[float] | None]:
        """Catalog lookup and query embedding in parallel; None embedding = provider down."""
        if not embed:
            return await self._products.get_product(request.sku), None
        return await _concurrently(
            self._products.get_product(request.sku), self._embed_question(request)
        )

    async def _embed_question(self, request: RagRequest) -> list[float] | None:
        try:
            [query_embedding] = await self._embedder.embed([request.question])
        except LLMUnavailableError:
            logger.exception("embedding_unavailable", extra={"sku": request.sku})
            return None
        return query_embedding

    async def _evidence(
        self, request: RagRequest, query_embedding: Sequence[float]
    ) -> list[RetrievedChunk]:
        found = await self._chunks.search(
            request.sku, query_embedding, self._settings.retrieval_top_k
        )
        return [c for c in found if c.sku == request.sku
                and c.similarity_score >= self._settings.similarity_threshold]

    async def _catalog_evidence(self, sku: str, source_text: str) -> list[RetrievedChunk]:
        for chunk in await self._chunks.catalog_sheet(sku):
            if chunk.sku == sku and source_text in chunk.content.splitlines():
                return [chunk]
        return []

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
        allow_upsell = substitutes or wants_upgrade(request.question)
        cards = await self._recommender.cards(
            product,
            query_embedding=query_embedding,
            allow_upsell=allow_upsell,
            requested_voltage=request.preferred_voltage,
            category=request.category,
            capacity_min=request.capacity_min,
            budget_max=request.budget_max,
            allow_secondary=not only_consulted_product(request.question),
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
        planned_events: list[InternalEvent],
    ) -> AsyncIterator[InternalEvent]:
        planned_cards = _planned_cards(planned_events)
        messages = build_messages(
            product,
            chunks,
            request.history,
            request.question,
            history_limit=self._settings.history_max_messages,
            recommendations=[card.model_dump(mode="json") for card in planned_cards],
        )
        verifier = ConsultativeVerifier(product, chunks, planned_cards)
        gate = _PublicationGate(verifier, request.sku)
        draft: list[str] = []
        buffer = SentenceBuffer()
        try:
            async for delta in self._chat_model.stream(messages):
                draft.append(delta)
                for sentence in buffer.feed(delta):
                    for approved in gate.review(sentence):
                        yield _token(approved)
        except LLMUnavailableError:
            logger.exception("llm_unavailable", extra={"sku": request.sku})
            yield _error("LLM_UNAVAILABLE", LLM_UNAVAILABLE_MESSAGE)
            for event in await self._similar_in_stock(request, product, query_embedding):
                yield event
            yield _end(0, ANSWER_INTENT)
            return
        for approved in gate.review(buffer.flush()) + gate.close():
            yield _token(approved)
        tokens_used = self._count_tokens("".join(draft))
        if not gate.approved:
            async for event in self._unapproved_draft(
                request, product, query_embedding, "".join(draft), tokens_used
            ):
                yield event
            return
        # Deliberate second SQL read (spec 7, R09): emit the cards as they are after the
        # stream, not the pre-prompt snapshot (stock may have sold out meanwhile). The
        # no-alternative notice is decided on that same fresh read.
        final_events, current = await asyncio.gather(
            self._recommendations(request, product, query_embedding, substitutes=False),
            self._products.get_product(request.sku),
        )
        if _unbuyable(request, current or product) and not _has_upsell(final_events):
            yield _token(f"\n{NO_ALTERNATIVE_MESSAGE}")
        for explanation in _explain_recommendations(request.question, _planned_cards(final_events)):
            yield _token(f"\n{explanation}")
        cited = [chunk for chunk in chunks if chunk.chunk_id in verifier.cited_chunk_ids]
        yield {"event": "citations", "data": {"citations": [_citation(c) for c in cited]}}
        for event in final_events:
            yield event
        yield _end(tokens_used, ANSWER_INTENT)


    async def _unapproved_draft(
        self,
        request: RagRequest,
        product: CatalogProduct,
        query_embedding: Sequence[float],
        draft: str,
        tokens_used: int,
    ) -> AsyncIterator[InternalEvent]:
        """G-OUT approved nothing: an alternative request is answered from SQL cards only;
        anything else is the R02 safe fallback."""
        rejected = draft.strip()[:REJECTED_DRAFT_LOG_MAX_CHARS]
        logger.debug(
            "gout_rejected_draft sku=%s draft=%r", request.sku, rejected,
            extra={"sku": request.sku, "draft": rejected},
        )
        substitutes = await self._similar_in_stock(request, product, query_embedding)
        if not _asks_for_alternative(request, product):
            yield _error("LOW_SIMILARITY_FALLBACK", LOW_SIMILARITY_MESSAGE)
            for event in substitutes:
                yield event
            yield _end(tokens_used, "LOW_SIMILARITY")
            return
        for sentence in _alternative_answer(product, _planned_cards(substitutes)):
            yield _token(sentence)
        for event in substitutes:
            yield event
        yield _end(tokens_used, ANSWER_INTENT)


class _PublicationGate:
    """Publishes approved sentences; a blocked technical claim becomes the missing-evidence
    notice, emitted only next to approved text so a fully rejected draft publishes nothing."""

    def __init__(self, verifier: ConsultativeVerifier, sku: str) -> None:
        self._verifier = verifier
        self._sku = sku
        self._notice_pending = False
        self._notice_sent = False
        self.approved = 0

    def review(self, sentence: str) -> list[str]:
        if not sentence.strip():
            self._verifier.end_block()  # a blank line closes an "SKU <code>:" block
            return [sentence] if self.approved else []
        if normalized_words(sentence) == _NOTICE_WORDS:
            # Prompt rule 3 wording: publish our canonical notice (once, next to approved text).
            self._notice_pending = True
            return []
        approved = self._verifier.approve(sentence)
        if approved is None:
            # Only a dropped spec (number + unit, price, bivolt) is "missing from the
            # manual"; a dropped courtesy or paraphrase is discarded silently.
            technical = bool(technical_claims(CITATION_MARK.sub("", sentence)))
            reason = "UNSUPPORTED_TECHNICAL_CLAIM" if technical else "UNSUPPORTED_SENTENCE"
            # Values in the message too: the default basicConfig format drops `extra`.
            logger.info(
                "gout_blocked_sentence sku=%s reason=%s", self._sku, reason,
                extra={"sku": self._sku, "reason": reason},
            )
            blocked_text = sentence.strip()[:BLOCKED_SENTENCE_LOG_MAX_CHARS]
            logger.debug(
                "gout_blocked_text sku=%s sentence=%r", self._sku, blocked_text,
                extra={"sku": self._sku, "sentence": blocked_text},
            )
            self._notice_pending = self._notice_pending or technical
            return []
        if not approved:
            return []  # "SKU <code>:" header, held and published with its first verified fact
        self.approved += 1
        return [*self._notice(), approved]

    def close(self) -> list[str]:
        return self._notice() if self.approved else []

    def _notice(self) -> list[str]:
        if not self._notice_pending or self._notice_sent:
            return []
        self._notice_pending = False
        self._notice_sent = True
        return [MISSING_EVIDENCE_NOTICE]
