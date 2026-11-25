"""Offline replay of tests/conversational/dialogs.json against ConsultantOrchestrator with fakes."""

import asyncio
import json
import re
from collections.abc import AsyncIterator, Sequence
from decimal import Decimal
from pathlib import Path
from uuid import uuid4

import pytest
from app.config import Settings
from app.consultant.conversation import conversation_state
from app.consultant.router import Route, route
from app.consultant.service import ConsultantOrchestrator
from app.db.consultant_repository import CatalogQuery, ConsultantLookupError
from app.generation.prompt import Message
from app.guardrails.output import length_measures_cm, pt_br_number
from app.guardrails.publication import CATALOG_MISSING_NOTICE
from app.ingestion.knowledge import knowledge_docs
from app.ingestion.manuals import read_manual_pages
from app.ingestion.run import load_catalog
from app.models.schemas import (
    CatalogProduct,
    ChatTurn,
    ConsultantRequest,
    RagRequest,
    RetrievedChunk,
)
from app.recommendation.cards import build_card

ROOT = Path(__file__).resolve().parents[3]
DATA_DIR = ROOT / "data"
DIALOGS_PATH = ROOT / "tests" / "conversational" / "dialogs.json"
_NUMERAL = re.compile(r"\d+(?:[.,]\d+)*")


class FakeConsultantCatalog:
    """In-memory ConsultantCatalog loaded from data/catalog.json + data/catalog_consultor.json."""

    def __init__(self) -> None:
        base = load_catalog(DATA_DIR / "catalog.json")
        consultor = load_catalog(DATA_DIR / "catalog_consultor.json")
        self.by_sku: dict[str, CatalogProduct] = {p.sku: p for p in [*base, *consultor]}
        self.manual_chunks: dict[str, list[RetrievedChunk]] = {}
        for sku, product in self.by_sku.items():
            manual_path = DATA_DIR / "manuals" / f"{sku}.txt"
            if not manual_path.exists():
                continue
            pages = read_manual_pages(manual_path)
            title = product.manual_title or f"Manual {product.name}"
            self.manual_chunks[sku] = [
                RetrievedChunk(
                    chunk_id=uuid4(),
                    sku=sku,
                    manual_title=title,
                    page_number=page_num,
                    section_title=None,
                    content=f"[PRODUTO: {product.name} | SKU: {sku} | MANUAL PÁG: {page_num}]\n{text}",
                    similarity_score=1.0,
                )
                for page_num, text in enumerate(pages, start=1)
            ]
        self.kb_by_doc: dict[str, list[RetrievedChunk]] = {}
        for doc in knowledge_docs(DATA_DIR / "knowledge"):
            self.kb_by_doc[doc.doc_id] = [
                RetrievedChunk(
                    chunk_id=uuid4(),
                    sku=doc.doc_id,
                    manual_title=doc.title,
                    page_number=page_num,
                    section_title=None,
                    content=(
                        f"[BASE DE CONHECIMENTO: {doc.title} | PÁG: {page_num}]\n"
                        f"{page_text}"
                    ),
                    similarity_score=1.0,
                )
                for page_num, page_text in enumerate(doc.pages, start=1)
            ]
        self.kb_search_results: list[RetrievedChunk] = []

    async def products(self, skus: Sequence[str]) -> list[CatalogProduct]:
        return [
            self.by_sku[sku]
            for sku in skus
            if sku in self.by_sku and self.by_sku[sku].is_active
        ]

    async def search(self, query: CatalogQuery) -> list[CatalogProduct]:
        matched = [
            product
            for product in self.by_sku.values()
            if product.is_active
            and product.stock_quantity > 0
            and product.category in query.categories
            and (query.subcategories is None or product.subcategory in query.subcategories)
            and (query.budget_max is None or product.price <= query.budget_max)
            and (
                query.voltage is None
                or product.voltage in {query.voltage, "BIVOLT", "N/A"}
            )
        ]
        return sorted(matched, key=lambda p: (p.price, p.sku))

    async def categories_in_stock(self) -> list[tuple[str, str]]:
        pairs = {
            (p.category, p.subcategory)
            for p in self.by_sku.values()
            if p.is_active and p.stock_quantity > 0
        }
        return sorted(pairs)

    async def game_tables(self, skus: Sequence[str]) -> list[RetrievedChunk]:
        chunks: list[RetrievedChunk] = []
        for sku in skus:
            for chunk in self.manual_chunks.get(sku, ()):
                if "desempenho em jogos" in chunk.content.casefold():
                    chunks.append(chunk)
        return chunks

    async def knowledge_doc(self, doc_id: str) -> list[RetrievedChunk]:
        return list(self.kb_by_doc.get(doc_id, ()))

    async def knowledge_page(self, doc_id: str, page: int) -> list[RetrievedChunk]:
        return [
            chunk
            for chunk in self.kb_by_doc.get(doc_id, ())
            if chunk.page_number == page
        ]

    async def search_knowledge(
        self, embedding: Sequence[float], limit: int
    ) -> list[RetrievedChunk]:
        return self.kb_search_results[:limit]


class FakeEmbedder:
    def __init__(self) -> None:
        self.calls: list[list[str]] = []

    async def embed(self, texts: Sequence[str]) -> list[list[float]]:
        self.calls.append(list(texts))
        return [[0.5] * 8 for _ in texts]


class FakeChatModel:
    def __init__(self, deltas: Sequence[str] = ()) -> None:
        self.deltas = list(deltas)
        self.calls: list[list[Message]] = []

    async def stream(self, messages: Sequence[Message]) -> AsyncIterator[str]:
        self.calls.append(list(messages))
        for delta in self.deltas:
            yield delta


class FakeRag:
    def __init__(self, catalog: FakeConsultantCatalog) -> None:
        self.catalog = catalog
        self.requests: list[RagRequest] = []

    async def stream(self, request: RagRequest) -> AsyncIterator[dict[str, object]]:
        self.requests.append(request)
        base = self.catalog.by_sku[request.sku]
        upsell = self.catalog.by_sku["AF-550-220V"]
        cross = self.catalog.by_sku["KIT-SIL-01"]
        yield {
            "event": "token",
            "data": {"delta": f"Possui capacidade de 4 L. SKU {upsell.sku}: Possui capacidade de 5,5 L.\n"},
        }
        yield {
            "event": "recommendations",
            "data": {
                "products": [
                    build_card(base, "PRIMARY", ""),
                    build_card(upsell, "UPSELL", "Capacidade superior."),
                    build_card(cross, "CROSS_SELL", "Acessório compatível."),
                ]
            },
        }
        yield {"event": "end", "data": {"tokens_used": 12, "intent": "TECHNICAL_QA"}}


def _valid_event_sequence(events: Sequence[dict[str, object]]) -> bool:
    names = [str(e["event"]) for e in events]
    if not names or names[-1] != "end":
        return False
    body = names[:-1]
    if body and body[0] == "error":
        rest = body[1:]
        return rest in ([], ["recommendations"])
    idx = 0
    while idx < len(body) and body[idx] == "token":
        idx += 1
    if idx == 0:
        return False
    if idx < len(body) and body[idx] == "citations":
        idx += 1
    if idx < len(body) and body[idx] == "recommendations":
        idx += 1
    return idx == len(body)


def _evidence_numbers(
    catalog: FakeConsultantCatalog,
    events: Sequence[dict[str, object]],
    question: str,
) -> set[str]:
    allowed: set[str] = {"1", "2", "3", "4", "5"}
    for num in _NUMERAL.findall(question):
        allowed.add(pt_br_number(num))
    for measure in length_measures_cm(question):
        allowed.add(format(measure.normalize(), "f"))

    for product in catalog.by_sku.values():
        allowed.add(format(product.price.normalize(), "f"))
        allowed.add(str(product.stock_quantity))
        if product.power_watts is not None:
            allowed.add(str(product.power_watts))
        if product.capacity_liters is not None:
            allowed.add(format(product.capacity_liters.normalize(), "f"))
        for num in _NUMERAL.findall(f"{product.sku} {product.name} {product.voltage}"):
            allowed.add(pt_br_number(num))
        for val in product.specs_json.values():
            for num in _NUMERAL.findall(str(val)):
                allowed.add(pt_br_number(num))
        if product.specs_json.get("largura_cm") is not None:
            width = Decimal(str(product.specs_json["largura_cm"]))
            allowed.add(format((width + Decimal("20")).normalize(), "f"))

    for event in events:
        if event["event"] == "citations":
            citations = event["data"]["citations"]  # type: ignore[index]
            for cit in citations:
                allowed.add(str(cit["page_number"]))
                for num in _NUMERAL.findall(f"{cit['manual_title']} {cit['excerpt']}"):
                    allowed.add(pt_br_number(num))
    return allowed


@pytest.mark.parametrize(
    "dialog",
    json.loads(DIALOGS_PATH.read_text(encoding="utf-8")),
    ids=lambda d: d["id"],
)
def test_conversational_dialogs_offline_replay(dialog: dict[str, object]) -> None:
    catalog = FakeConsultantCatalog()
    embedder = FakeEmbedder()
    chat_model = FakeChatModel()
    fake_rag = FakeRag(catalog)
    orchestrator = ConsultantOrchestrator(
        catalog,
        embedder,
        chat_model,
        Settings(),
        rag=fake_rag,
    )

    history: list[ChatTurn] = []
    turns: list[dict[str, object]] = dialog["turns"]  # type: ignore[assignment]

    for turn in turns:
        sku = turn["sku"]  # type: ignore[assignment]
        question = str(turn["question"])
        expected_route = Route(str(turn["expected_route"]))
        expected_intent = str(turn["expected_intent"])
        is_llm_turn = bool(turn.get("llm_turn", False))

        if expected_route == Route.KB_QA:
            if turn.get("expect_error") == "LOW_SIMILARITY_FALLBACK":
                catalog.kb_search_results = []
                chat_model.deltas = []
            else:
                roblox_chunks = catalog.kb_by_doc["KB-ROBLOX-REQUISITOS"]
                catalog.kb_search_results = [
                    roblox_chunks[0].model_copy(update={"similarity_score": 0.92})
                ]
                chat_model.deltas = [str(turn.get("fake_llm_response", ""))]

        req = ConsultantRequest(sku=sku, question=question, history=list(history))  # type: ignore[arg-type]
        current = catalog.by_sku.get(sku) if isinstance(sku, str) else None
        state = conversation_state(req)
        shown_products = [catalog.by_sku[s] for s in state.shown_skus if s in catalog.by_sku]
        assert route(question, state, current, shown_products=shown_products) == expected_route

        embeds_before = len(embedder.calls)
        llm_before = len(chat_model.calls)

        async def _collect(r: ConsultantRequest = req) -> list[dict[str, object]]:
            return [event async for event in orchestrator.stream(r)]

        events = asyncio.run(_collect())
        assert _valid_event_sequence(events), f"Invalid event order: {[e['event'] for e in events]}"

        if not is_llm_turn:
            assert len(embedder.calls) == embeds_before
            assert len(chat_model.calls) == llm_before

        end_data = events[-1]["data"]  # type: ignore[index]
        assert end_data["intent"] == expected_intent

        if turn.get("expect_error"):
            assert events[0]["event"] == "error"
            err_data = events[0]["data"]  # type: ignore[index]
            assert err_data["code"] == turn["expect_error"]
            published = str(err_data["fallback_message"])
        else:
            published = "".join(
                str(e["data"]["delta"])  # type: ignore[index]
                for e in events
                if e["event"] == "token"
            )

        for phrase in turn.get("must_contain", ()):  # type: ignore[attr-defined]
            assert str(phrase) in published
        for forbidden in turn.get("must_not_contain", ()):  # type: ignore[attr-defined]
            assert str(forbidden) not in published

        rec_events = [e for e in events if e["event"] == "recommendations"]
        cards = rec_events[0]["data"]["products"] if rec_events else []  # type: ignore[index]
        expected_skus = list(turn.get("expected_card_skus", ()))  # type: ignore[arg-type]
        assert [c["sku"] for c in cards] == expected_skus
        expected_role = turn.get("expected_card_role")
        for card in cards:
            sql_product = catalog.by_sku[card["sku"]]
            assert card["stock_quantity"] == sql_product.stock_quantity > 0
            assert Decimal(str(card["price"])) == sql_product.price
            if expected_role:
                assert card["recommendation_type"] == expected_role
                assert card["badge_label"] == "Opção"

        if not turn.get("expect_error"):
            allowed_numbers = _evidence_numbers(catalog, events, question)
            published_nums = {pt_br_number(n) for n in _NUMERAL.findall(published)}
            assert published_nums <= allowed_numbers, (
                f"Unsupported numbers {published_nums - allowed_numbers} in: {published!r}"
            )

        history.append(ChatTurn(role="user", content=question))
        history.append(
            ChatTurn(
                role="assistant",
                content=published.strip(),
                recommended_skus=[str(c["sku"]) for c in cards],
            )
        )


def test_game_fit_uses_a_new_title_from_the_product_manual() -> None:
    catalog = FakeConsultantCatalog()
    sku = "PC-VX3-BIV"
    page = next(chunk for chunk in catalog.manual_chunks[sku] if chunk.page_number == 4)
    catalog.manual_chunks[sku] = [
        page.model_copy(update={"content": page.content + "\n| Elden Ring | 1080p | Ultra | 58 fps |\r\n"})
    ]
    embedder = FakeEmbedder()
    chat_model = FakeChatModel()
    orchestrator = ConsultantOrchestrator(catalog, embedder, chat_model, rag=FakeRag(catalog))

    async def collect() -> list[dict[str, object]]:
        request = ConsultantRequest(sku=sku, question="Esse PC roda Elden Ring no ultra?")
        return [event async for event in orchestrator.stream(request)]

    events = asyncio.run(collect())
    assert _valid_event_sequence(events)
    assert "58 fps em Elden Ring" in str(events[0]["data"])
    assert [event["event"] for event in events].count("citations") == 1
    assert embedder.calls == []
    assert chat_model.calls == []


def test_technical_route_delegates_exact_rag_request() -> None:
    catalog = FakeConsultantCatalog()
    fake_rag = FakeRag(catalog)
    orchestrator = ConsultantOrchestrator(
        catalog,
        FakeEmbedder(),
        FakeChatModel(),
        Settings(),
        rag=fake_rag,
    )
    request = ConsultantRequest(
        sku="AF-400-220V",
        question="Qual a potência nominal?",
        preferred_voltage="220V",
        budget_max=Decimal("700.00"),
    )

    async def _run() -> list[dict[str, object]]:
        return [e async for e in orchestrator.stream(request)]

    events = asyncio.run(_run())
    assert len(fake_rag.requests) == 1
    assert fake_rag.requests[0] == request.rag_request("AF-400-220V")
    assert events[-1]["data"]["intent"] == "TECHNICAL_QA"  # type: ignore[index]


def test_kb_qa_zero_chunks_clarifies_when_shown_set_has_multiple_products() -> None:
    catalog = FakeConsultantCatalog()
    catalog.kb_search_results = []
    orchestrator = ConsultantOrchestrator(
        catalog,
        FakeEmbedder(),
        FakeChatModel(),
        Settings(),
        rag=FakeRag(catalog),
    )
    request = ConsultantRequest(
        sku=None,
        question="Como funciona o resfriamento?",
        history=[
            ChatTurn(
                role="assistant",
                content="Opções:",
                recommended_skus=["PC-VX3-BIV", "PC-VX5-BIV"],
            )
        ],
    )

    async def _run() -> list[dict[str, object]]:
        return [e async for e in orchestrator.stream(request)]

    events = asyncio.run(_run())
    published = "".join(str(e["data"]["delta"]) for e in events if e["event"] == "token")  # type: ignore[index]
    assert "Sobre qual dos produtos mostrados? Cite o SKU, por exemplo SKU PC-VX3-BIV" in published


def test_kb_qa_drops_hallucinated_number_and_emits_catalog_missing_notice() -> None:
    catalog = FakeConsultantCatalog()
    roblox_chunk = catalog.kb_by_doc["KB-ROBLOX-REQUISITOS"][0].model_copy(
        update={"similarity_score": 0.91}
    )
    catalog.kb_search_results = [roblox_chunk]
    chat_model = FakeChatModel(
        [
            "Memória: a Roblox recomenda pelo menos 1 GB de RAM no Windows 10 ou 11 "
            "[Fonte: Requisitos do Roblox para PC, p. 1]. ",
            "O Roblox exige 64 GB de RAM e 500 W de potência. ",
        ]
    )
    orchestrator = ConsultantOrchestrator(
        catalog,
        FakeEmbedder(),
        chat_model,
        Settings(),
        rag=FakeRag(catalog),
    )
    request = ConsultantRequest(sku=None, question="quais os requisitos do Roblox?")

    async def _run() -> list[dict[str, object]]:
        return [e async for e in orchestrator.stream(request)]

    events = asyncio.run(_run())
    published = "".join(str(e["data"]["delta"]) for e in events if e["event"] == "token")  # type: ignore[index]
    assert "1 GB de RAM" in published
    assert "64 GB" not in published and "500 W" not in published
    assert CATALOG_MISSING_NOTICE in published


def test_sql_failure_emits_internal_error_and_end() -> None:
    class FailingCatalog(FakeConsultantCatalog):
        async def search(self, query: CatalogQuery) -> list[CatalogProduct]:
            raise ConsultantLookupError("database down")

    catalog = FailingCatalog()
    orchestrator = ConsultantOrchestrator(
        catalog,
        FakeEmbedder(),
        FakeChatModel(),
        Settings(),
        rag=FakeRag(catalog),
    )
    request = ConsultantRequest(sku=None, question="quero um computador novo")

    async def _run() -> list[dict[str, object]]:
        return [e async for e in orchestrator.stream(request)]

    events = asyncio.run(_run())
    assert [e["event"] for e in events] == ["error", "end"]
    assert events[0]["data"]["code"] == "INTERNAL_ERROR"  # type: ignore[index]
