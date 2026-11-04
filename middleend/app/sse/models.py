"""Typed public and internal SSE contracts; adapters provide JSON-ready DTOs."""

from __future__ import annotations

from collections.abc import AsyncIterator, Mapping
from dataclasses import dataclass
from typing import Literal, NotRequired, Protocol, TypedDict

PublicEventName = Literal[
    "metadata", "token", "correction", "citations", "recommendations", "error", "done"
]
FinishReason = Literal["stop", "fallback", "error"]
ErrorCode = Literal[
    "GUARDRAIL_BLOCKED", "LOW_SIMILARITY_FALLBACK", "LLM_UNAVAILABLE", "INTERNAL_ERROR"
]


class Citation(TypedDict):
    chunk_id: str
    sku: str
    manual_title: str
    page_number: int
    section_title: NotRequired[str | None]
    similarity_score: float
    excerpt: str


class ProductCard(TypedDict):
    sku: str
    name: str
    price: int | float
    stock_quantity: int
    voltage: Literal["127V", "220V", "BIVOLT", "N/A"]
    capacity_liters: NotRequired[float | None]
    power_watts: NotRequired[int | None]
    image_url: str
    marketplace: Literal["AMAZON", "MERCADO_LIVRE", "SHOPEE", "LOJA_OFICIAL"]
    checkout_url: str
    recommendation_type: Literal["PRIMARY", "UPSELL", "CROSS_SELL"]
    badge_label: str
    justification: str


class MetadataPayload(TypedDict):
    session_id: str
    message_id: str
    cache_hit: bool
    ttft_ms: int


class TokenPayload(TypedDict):
    delta: str


class CorrectionPayload(TypedDict):
    violation_code: Literal["STREAM_INTERRUPTED"]
    content: str


class CitationsPayload(TypedDict):
    citations: list[Citation]


class RecommendationsPayload(TypedDict):
    products: list[ProductCard]


class ErrorPayload(TypedDict):
    code: ErrorCode
    recoverable: bool
    fallback_message: str


class EndPayload(TypedDict):
    tokens_used: int
    intent: NotRequired[str]


class DonePayload(TypedDict):
    finish_reason: FinishReason
    total_latency_ms: int
    tokens_used: int


class BackendEvent(TypedDict):
    event: Literal["token", "correction", "citations", "recommendations", "error", "end"]
    data: (
        TokenPayload
        | CorrectionPayload
        | CitationsPayload
        | RecommendationsPayload
        | ErrorPayload
        | EndPayload
    )


class DisconnectRequest(Protocol):
    async def is_disconnected(self) -> bool: ...


class BackendStream(AsyncIterator[Mapping[str, object]], Protocol):
    async def aclose(self) -> None: ...


@dataclass(frozen=True)
class CompletedTurn:
    """Approved terminal snapshot for atomic history/idempotency/cache persistence."""

    session_id: str
    message_id: str
    content: str
    citations: tuple[Citation, ...]
    products: tuple[ProductCard, ...]
    finish_reason: Literal["stop", "fallback"]
    tokens_used: int
    intent: str | None
    cache_hit: bool
    ttft_ms: int
    total_latency_ms: int
