"""Unified ConsultantOrchestrator wrapping RAGOrchestrator (spec §1–§5)."""

import logging
import re
from collections.abc import AsyncIterator, Callable, Sequence
from dataclasses import replace
from decimal import Decimal
from typing import Literal, Protocol

from app.clients.openai_client import LLMUnavailableError
from app.config import Settings
from app.consultant.builders import (
    GREETING_MESSAGE,
    NO_COMPARISON_SET_MESSAGE,
    ConsultantAnswer,
    brand_opinion_answer,
    clarify_product_message,
    comparison_answer,
    dimension_fit_answer,
    discovery_answer,
    game_fit_answer,
    price_rank_answer,
    set_voltage_answer,
    stream_fit_answer,
)
from app.consultant.conversation import CategoryTarget, ConversationState, conversation_state
from app.consultant.evidence import (
    GameRow,
    KbFactHit,
    kb_measure,
    kb_sentence,
    parse_game_rows,
    webcam_capability,
)
from app.consultant.knowledge_facts import (
    KB_GTA6_NO_PC,
    KB_GTA6_PLATFORMS,
    KB_GTA_RP,
    KB_SOFA_CLEARANCE,
    KB_TWITCH_FPS,
    KB_TWITCH_HEIGHT,
)
from app.consultant.router import Route, comparison_set, route, route_intent
from app.consultant.slots import parse_game, parse_voltage
from app.db.consultant_repository import (
    CatalogQuery,
    ConsultantCatalog,
    ConsultantLookupError,
)
from app.generation.prompt import build_catalog_messages
from app.guardrails.input import is_prompt_injection
from app.guardrails.output import SentenceBuffer
from app.guardrails.publication import (
    CATALOG_MISSING_NOTICE,
    ConsultativeVerifier,
    _PublicationGate,
)
from app.models.schemas import (
    CatalogProduct,
    ConsultantRequest,
    RagRequest,
    RetrievedChunk,
)
from app.rag.orchestrator import (
    BLOCKED_MESSAGE,
    LLM_UNAVAILABLE_MESSAGE,
    ChatModel,
    Embedder,
    InternalEvent,
    _citation,
    _end,
    _error,
    _token,
)
from app.recommendation.intent import folded

logger = logging.getLogger(__name__)

CATALOG_BLOCKED_MESSAGE = (
    "Só posso responder dúvidas sobre os produtos do catálogo e a base de conhecimento oficial da loja."
)
CATALOG_LOW_SIMILARITY_MESSAGE = (
    "Essa informação não consta na base de conhecimento nem no catálogo ativo da loja. "
    "Posso ajudar a buscar ou comparar produtos do catálogo?"
)
INTERNAL_ERROR_MESSAGE = (
    "Ocorreu um erro interno ao consultar o catálogo. Tente novamente em instantes."
)
_PRICIEST_RE = re.compile(r"\b(mais car[oa]s?|maior preco)\b")


class RagDelegate(Protocol):
    def stream(self, request: RagRequest) -> AsyncIterator[InternalEvent]: ...


def _match_game_rows(
    skus: Sequence[str], chunks: Sequence[RetrievedChunk], target_game: str
) -> dict[str, GameRow | None]:
    wanted = folded(target_game)
    matched: dict[str, GameRow | None] = {sku: None for sku in skus}
    for chunk in chunks:
        if chunk.sku not in matched or matched[chunk.sku] is not None:
            continue
        for row in parse_game_rows(chunk):
            if folded(row.game) == wanted:
                matched[chunk.sku] = row
                break
    return matched


def _publish_deterministic(answer: ConsultantAnswer) -> list[InternalEvent]:
    events: list[InternalEvent] = [_token(sentence) for sentence in answer.sentences]
    if answer.cited:
        events.append(
            {"event": "citations", "data": {"citations": [_citation(c) for c in answer.cited]}}
        )
    if answer.cards:
        events.append({"event": "recommendations", "data": {"products": list(answer.cards)}})
    events.append(_end(0, answer.intent))
    return events


class ConsultantOrchestrator:
    """Routes turns between deterministic builders, KB_QA and the legacy RAGOrchestrator."""

    def __init__(
        self,
        catalog: ConsultantCatalog,
        embedder: Embedder,
        chat_model: ChatModel,
        settings: Settings | None = None,
        *,
        rag: RagDelegate,
        count_tokens: Callable[[str], int] = lambda text: len(text.split()),
    ) -> None:
        self._catalog = catalog
        self._embedder = embedder
        self._chat_model = chat_model
        self._settings = settings or Settings()
        self._rag = rag
        self._count_tokens = count_tokens

    async def stream(self, request: ConsultantRequest) -> AsyncIterator[InternalEvent]:
        state = conversation_state(request)
        if is_prompt_injection(request.question):
            logger.info("consultant_route route=%s sku=%s", Route.BLOCKED, request.sku or "-")
            message = CATALOG_BLOCKED_MESSAGE if request.sku is None else BLOCKED_MESSAGE
            yield _error("GUARDRAIL_BLOCKED", message)
            yield _end(0, "BLOCKED")
            return

        if route(request.question, state, None) == Route.GREETING:
            logger.info("consultant_route route=%s sku=%s", Route.GREETING, request.sku or "-")
            yield _token(GREETING_MESSAGE)
            yield _end(0, route_intent(Route.GREETING))
            return

        try:
            lookup_skus = list(
                dict.fromkeys(
                    [
                        *([request.sku] if request.sku else []),
                        *state.shown_skus,
                        *state.mentioned_skus,
                    ]
                )
            )
            fetched = await self._catalog.products(lookup_skus) if lookup_skus else []
            by_sku = {p.sku: p for p in fetched}
            current = by_sku.get(request.sku) if request.sku else None
            if request.sku is not None and current is None:
                logger.info(
                    "consultant_route route=%s sku=%s", Route.TECHNICAL, request.sku
                )
                async for event in self._rag.stream(request.rag_request(request.sku)):
                    yield event
                return

            shown_products = [by_sku[sku] for sku in state.shown_skus if sku in by_sku]
            valid_mentioned = tuple(sku for sku in state.mentioned_skus if sku in by_sku)
            if valid_mentioned != state.mentioned_skus:
                state = replace(state, mentioned_skus=valid_mentioned)

            chosen = route(
                request.question, state, current, shown_products=shown_products
            )
            logger.info("consultant_route route=%s sku=%s", chosen, request.sku or "-")

            if chosen == Route.TECHNICAL:
                target_sku = (
                    state.mentioned_skus[0]
                    if state.mentioned_skus
                    else (request.sku or state.shown_skus[0])
                )
                async for event in self._rag.stream(request.rag_request(target_sku)):
                    yield event
                return

            if chosen == Route.KB_QA:
                async for event in self._handle_kb_qa(request, state, shown_products):
                    yield event
                return

            answer = await self._build_deterministic(
                chosen, request, state, current, shown_products, by_sku
            )
            if answer is None:
                yield _token(NO_COMPARISON_SET_MESSAGE)
                yield _end(0, route_intent(chosen))
                return

            for event in _publish_deterministic(answer):
                yield event
        except ConsultantLookupError:
            logger.exception("consultant_lookup_failed", extra={"sku": request.sku})
            yield _error("INTERNAL_ERROR", INTERNAL_ERROR_MESSAGE)
            yield _end(0, "TECHNICAL_QA")

    async def _build_deterministic(
        self,
        chosen: Route,
        request: ConsultantRequest,
        state: ConversationState,
        current: CatalogProduct | None,
        shown_products: Sequence[CatalogProduct],
        by_sku: dict[str, CatalogProduct],
    ) -> ConsultantAnswer | None:
        if chosen == Route.DISCOVERY:
            return await self._handle_discovery(state)
        if chosen == Route.GAME_FIT:
            return await self._handle_game_fit(request, state, current, shown_products, by_sku)
        if chosen == Route.STREAM_FIT:
            return await self._handle_stream_fit(state, current, by_sku)
        if chosen == Route.DIMENSION_FIT:
            return await self._handle_dimension_fit(state, current, shown_products, by_sku)
        return await self._handle_comparison_routes(
            chosen, request, state, current, shown_products, by_sku
        )

    async def _handle_discovery(self, state: ConversationState) -> ConsultantAnswer:
        slots = state.slots
        if slots.category is None:
            cats = await self._catalog.categories_in_stock()
            return discovery_answer(
                (),
                slots,
                game_rows={},
                game_fact=None,
                relaxed=None,
                categories_in_stock=cats,
            )
        cat = slots.category
        found = await self._catalog.search(
            CatalogQuery(
                categories=(cat.category,),
                subcategories=cat.subcategories or None,
                budget_max=slots.budget_max,
                voltage=slots.voltage,
            )
        )
        if slots.seats is not None and "Sofás" in cat.subcategories:
            found = [p for p in found if p.specs_json.get("lugares") == slots.seats]
        options = found[: self._settings.consultant_max_options]

        relaxed: CatalogProduct | None = None
        if not options and slots.budget_max is not None:
            relaxed_found = await self._catalog.search(
                CatalogQuery(
                    categories=(cat.category,),
                    subcategories=cat.subcategories or None,
                    budget_max=None,
                    voltage=slots.voltage,
                )
            )
            if slots.seats is not None and "Sofás" in cat.subcategories:
                relaxed_found = [
                    p for p in relaxed_found if p.specs_json.get("lugares") == slots.seats
                ]
            relaxed = relaxed_found[0] if relaxed_found else None

        game_rows: dict[str, GameRow | None] = {}
        game_fact: KbFactHit | None = None
        if slots.game == "GTA 6":
            kb_chunks = await self._catalog.knowledge_doc(KB_GTA6_NO_PC.doc_id)
            hit_chunk = kb_sentence(kb_chunks, KB_GTA6_NO_PC.text)
            if hit_chunk is not None:
                game_fact = KbFactHit(KB_GTA6_NO_PC.text, hit_chunk)
        elif slots.game is not None and options:
            lookup_game = "GTA V" if slots.game == "GTA RP" else slots.game
            option_skus = [p.sku for p in options]
            table_chunks = await self._catalog.game_tables(option_skus)
            game_rows = _match_game_rows(option_skus, table_chunks, lookup_game)

        return discovery_answer(
            options,
            slots,
            game_rows=game_rows,
            game_fact=game_fact,
            relaxed=relaxed,
            categories_in_stock=(),
        )

    async def _handle_game_fit(
        self,
        request: ConsultantRequest,
        state: ConversationState,
        current: CatalogProduct | None,
        shown_products: Sequence[CatalogProduct],
        by_sku: dict[str, CatalogProduct],
    ) -> ConsultantAnswer:
        game = parse_game(request.question) or state.slots.game or "GTA V"
        if game == "GTA 6":
            kb_chunks = await self._catalog.knowledge_doc(KB_GTA6_PLATFORMS.doc_id)
            platform_hits: list[KbFactHit] = []
            for fact in (KB_GTA6_PLATFORMS, KB_GTA6_NO_PC):
                hit_chunk = kb_sentence(kb_chunks, fact.text)
                if hit_chunk is not None:
                    platform_hits.append(KbFactHit(fact.text, hit_chunk))
            cats = await self._catalog.categories_in_stock()
            consoles = any(
                "console" in sub.casefold() or "console" in cat.casefold()
                for cat, sub in cats
            )
            return game_fit_answer((), game, {}, platform_hits, None, None, consoles)

        alias_hit: KbFactHit | None = None
        lookup_game = game
        if game == "GTA RP":
            rp_chunks = await self._catalog.knowledge_doc(KB_GTA_RP.doc_id)
            rp_chunk = kb_sentence(rp_chunks, KB_GTA_RP.text)
            if rp_chunk is not None:
                alias_hit = KbFactHit(KB_GTA_RP.text, rp_chunk)
            lookup_game = "GTA V"

        if state.mentioned_skus:
            targets = [by_sku[sku] for sku in state.mentioned_skus if sku in by_sku]
        elif current is not None and current.category == "Computadores":
            targets = [current]
        elif any(p.category == "Computadores" for p in shown_products):
            targets = [p for p in shown_products if p.category == "Computadores"]
        else:
            cat = (
                state.slots.category
                if state.slots.category and state.slots.category.category == "Computadores"
                else CategoryTarget("Computadores", ("PCs Gamer", "Notebooks Gamer"))
            )
            found = await self._catalog.search(
                CatalogQuery(
                    categories=(cat.category,),
                    subcategories=cat.subcategories or None,
                    budget_max=state.slots.budget_max,
                    voltage=state.slots.voltage,
                )
            )
            targets = found[: self._settings.consultant_max_options]

        target_skus = [p.sku for p in targets]
        table_chunks = await self._catalog.game_tables(target_skus)
        rows = _match_game_rows(target_skus, table_chunks, lookup_game)

        alternative: tuple[CatalogProduct, GameRow] | None = None
        if len(targets) == 1 and rows.get(targets[0].sku) is None:
            single = targets[0]
            peers = await self._catalog.search(
                CatalogQuery(categories=(single.category,), subcategories=(single.subcategory,))
            )
            peer_skus = [p.sku for p in peers if p.sku != single.sku]
            peer_chunks = await self._catalog.game_tables(peer_skus)
            peer_rows = _match_game_rows(peer_skus, peer_chunks, lookup_game)
            for peer in peers:
                peer_row = peer_rows.get(peer.sku)
                if peer.sku != single.sku and peer_row is not None:
                    alternative = (peer, peer_row)
                    break

        return game_fit_answer(targets, game, rows, (), alias_hit, alternative, False)

    async def _handle_stream_fit(
        self,
        state: ConversationState,
        current: CatalogProduct | None,
        by_sku: dict[str, CatalogProduct],
    ) -> ConsultantAnswer | None:
        kb_chunks = await self._catalog.knowledge_doc(KB_TWITCH_HEIGHT.doc_id)
        height = kb_measure(kb_chunks, KB_TWITCH_HEIGHT.text)
        fps = kb_measure(kb_chunks, KB_TWITCH_FPS.text)
        if height is None or fps is None:
            return None

        target: CatalogProduct | None = None
        if state.mentioned_skus:
            target = next(
                (
                    by_sku[s]
                    for s in state.mentioned_skus
                    if s in by_sku and by_sku[s].subcategory == "Webcams"
                ),
                None,
            )
        elif current is not None and current.subcategory == "Webcams":
            target = current

        webcams = await self._catalog.search(
            CatalogQuery(
                categories=("Periféricos",),
                subcategories=("Webcams",),
                budget_max=state.slots.budget_max,
            )
        )
        req_h, req_f = int(height.value), int(fps.value)
        matches = [
            w
            for w in webcams
            if (cap := webcam_capability(w)) is not None and cap[0] >= req_h and cap[1] >= req_f
        ][: self._settings.consultant_max_options]
        return stream_fit_answer(target, height, fps, matches)

    async def _handle_dimension_fit(
        self,
        state: ConversationState,
        current: CatalogProduct | None,
        shown_products: Sequence[CatalogProduct],
        by_sku: dict[str, CatalogProduct],
    ) -> ConsultantAnswer | None:
        kb_chunks = await self._catalog.knowledge_doc(KB_SOFA_CLEARANCE.doc_id)
        clearance = kb_measure(kb_chunks, KB_SOFA_CLEARANCE.text)
        if clearance is None:
            return None

        target: CatalogProduct | None = None
        if state.mentioned_skus:
            target = next(
                (
                    by_sku[s]
                    for s in state.mentioned_skus
                    if s in by_sku and by_sku[s].subcategory == "Sofás"
                ),
                None,
            )
        elif current is not None and current.subcategory == "Sofás":
            target = current
        elif len(shown_products) == 1 and shown_products[0].subcategory == "Sofás":
            target = shown_products[0]

        sofas = await self._catalog.search(
            CatalogQuery(
                categories=("Móveis",),
                subcategories=("Sofás",),
                budget_max=state.slots.budget_max,
            )
        )
        if state.slots.seats is not None:
            sofas = [s for s in sofas if s.specs_json.get("lugares") == state.slots.seats]
        return dimension_fit_answer(target, state.slots.room_width_cm, clearance, sofas)

    async def _handle_comparison_routes(
        self,
        chosen: Route,
        request: ConsultantRequest,
        state: ConversationState,
        current: CatalogProduct | None,
        shown_products: Sequence[CatalogProduct],
        by_sku: dict[str, CatalogProduct],
    ) -> ConsultantAnswer | None:
        referent: CatalogProduct | None = None
        if state.mentioned_skus:
            referent = by_sku.get(state.mentioned_skus[0])
        elif current is not None:
            referent = current
        elif len(shown_products) == 1:
            referent = shown_products[0]

        filtered_shown = comparison_set(request.question, shown_products)
        if len(filtered_shown) >= 2:
            comp_products = filtered_shown
            from_peers = False
        elif referent is not None:
            peers = await self._catalog.search(
                CatalogQuery(
                    categories=(referent.category,),
                    subcategories=(referent.subcategory,),
                )
            )
            comp_products = comparison_set(
                request.question, shown_products, referent=referent, peers=peers
            )
            from_peers = True
        else:
            comp_products = filtered_shown
            from_peers = False

        if len(comp_products) < 2:
            return None

        if chosen == Route.SET_VOLTAGE:
            voltage = parse_voltage(request.question) or state.slots.voltage
            return set_voltage_answer(comp_products, voltage)

        if chosen == Route.PRICE_RANK:
            direction: Literal["cheapest", "priciest"] = (
                "priciest" if _PRICIEST_RE.search(folded(request.question)) else "cheapest"
            )
            return price_rank_answer(comp_products, referent, direction, from_peers)

        if chosen == Route.OPINION_BRAND:
            return brand_opinion_answer(comp_products)

        game_rows: dict[str, GameRow | None] = {}
        comp_game: str | None = None
        if state.slots.game is not None and state.slots.game != "GTA 6":
            comp_game = "GTA V" if state.slots.game == "GTA RP" else state.slots.game
            comp_skus = [p.sku for p in comp_products]
            table_chunks = await self._catalog.game_tables(comp_skus)
            game_rows = _match_game_rows(comp_skus, table_chunks, comp_game)
        return comparison_answer(comp_products, game_rows, comp_game)

    async def _handle_kb_qa(
        self,
        request: ConsultantRequest,
        state: ConversationState,
        shown_products: Sequence[CatalogProduct],
    ) -> AsyncIterator[InternalEvent]:
        try:
            [query_embedding] = await self._embedder.embed([request.question])
        except LLMUnavailableError:
            logger.exception("kb_embedding_unavailable")
            yield _error("LLM_UNAVAILABLE", LLM_UNAVAILABLE_MESSAGE)
            yield _end(0, route_intent(Route.KB_QA))
            return

        found = await self._catalog.search_knowledge(
            query_embedding, self._settings.retrieval_top_k
        )
        kb_chunks = [
            chunk
            for chunk in found
            if chunk.similarity_score >= self._settings.similarity_threshold
        ]
        if not kb_chunks:
            if len(shown_products) >= 2 or len(state.shown_skus) >= 2:
                first_sku = (
                    shown_products[0].sku if shown_products else state.shown_skus[0]
                )
                yield _token(clarify_product_message(first_sku))
                yield _end(0, route_intent(Route.KB_QA))
                return
            yield _error("LOW_SIMILARITY_FALLBACK", CATALOG_LOW_SIMILARITY_MESSAGE)
            yield _end(0, "LOW_SIMILARITY")
            return

        messages = build_catalog_messages(
            shown_products,
            kb_chunks,
            request.history,
            request.question,
            history_limit=self._settings.history_max_messages,
        )
        verifier = ConsultativeVerifier(
            None,
            kb_chunks,
            shown_products,
            allow_general_information=True,
            user_message=request.question,
        )
        gate = _PublicationGate(verifier, "KB_QA", notice=CATALOG_MISSING_NOTICE)
        draft: list[str] = []
        buffer = SentenceBuffer()
        try:
            async for delta in self._chat_model.stream(messages):
                draft.append(delta)
                for sentence in buffer.feed(delta):
                    for approved in gate.review(sentence):
                        yield _token(approved)
        except LLMUnavailableError:
            logger.exception("kb_llm_unavailable")
            yield _error("LLM_UNAVAILABLE", LLM_UNAVAILABLE_MESSAGE)
            yield _end(0, route_intent(Route.KB_QA))
            return

        for approved in gate.review(buffer.flush()) + gate.close():
            yield _token(approved)

        tokens_used = self._count_tokens("".join(draft))
        if not gate.approved:
            yield _error("LOW_SIMILARITY_FALLBACK", CATALOG_LOW_SIMILARITY_MESSAGE)
            yield _end(tokens_used, "LOW_SIMILARITY")
            return

        cited = [chunk for chunk in kb_chunks if chunk.chunk_id in verifier.cited_chunk_ids]
        yield {"event": "citations", "data": {"citations": [_citation(c) for c in cited]}}
        yield _end(tokens_used, route_intent(Route.KB_QA))
