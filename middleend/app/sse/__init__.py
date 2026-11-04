"""Framework-independent M02 SSE contracts and generator."""

from .models import (
    BackendEvent,
    BackendStream,
    Citation,
    CitationsPayload,
    CompletedTurn,
    CorrectionPayload,
    DisconnectRequest,
    DonePayload,
    EndPayload,
    ErrorPayload,
    MetadataPayload,
    ProductCard,
    RecommendationsPayload,
    TokenPayload,
)
from .stream import format_sse, sse_chat_generator

__all__ = [
    "BackendEvent",
    "BackendStream",
    "Citation",
    "CitationsPayload",
    "CompletedTurn",
    "CorrectionPayload",
    "DisconnectRequest",
    "DonePayload",
    "EndPayload",
    "ErrorPayload",
    "MetadataPayload",
    "ProductCard",
    "RecommendationsPayload",
    "TokenPayload",
    "format_sse",
    "sse_chat_generator",
]
