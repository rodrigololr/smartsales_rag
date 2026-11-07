"""Strict validation at the backend transport boundary (no domain calculations)."""

from __future__ import annotations

import json
import math
from collections.abc import Mapping
from decimal import Decimal
from typing import cast

from .models import Citation, ProductCard

ERROR_CODES = {"GUARDRAIL_BLOCKED", "LOW_SIMILARITY_FALLBACK", "LLM_UNAVAILABLE", "INTERNAL_ERROR"}
CONTENT_EVENTS = {"token", "correction", "citations", "recommendations", "error"}
CENT = Decimal("0.01")


def require(condition: bool) -> None:
    if not condition:
        raise ValueError("Invalid internal stream payload or event order")


def object_payload(payload: object) -> Mapping[str, object]:
    require(isinstance(payload, dict))
    return cast(Mapping[str, object], payload)


def integer(value: object, *, minimum: int = 0) -> bool:
    return type(value) is int and value >= minimum


def number(value: object, *, minimum: float = 0) -> bool:
    return (
        type(value) in (int, float)
        and math.isfinite(cast(float, value))
        and cast(float, value) >= minimum
    )


def strings(payload: Mapping[str, object], fields: tuple[str, ...]) -> None:
    require(all(isinstance(payload.get(field), str) for field in fields))


def citations(payload: object) -> list[Citation]:
    require(isinstance(payload, list))
    for item in cast(list[object], payload):
        citation = object_payload(item)
        strings(citation, ("chunk_id", "sku", "manual_title", "excerpt"))
        require(integer(citation.get("page_number"), minimum=1))
        require(number(citation.get("similarity_score")))
        require(cast(float, citation["similarity_score"]) <= 1)
        require(
            citation.get("section_title") is None or isinstance(citation.get("section_title"), str)
        )
    return cast(list[Citation], payload)


def products(payload: object) -> list[ProductCard]:
    require(isinstance(payload, list) and len(cast(list[object], payload)) <= 3)
    roles: set[str] = set()
    for item in cast(list[object], payload):
        card = object_payload(item)
        strings(
            card,
            ("sku", "name", "voltage", "image_url", "checkout_url", "badge_label", "justification"),
        )
        require(number(card.get("price")) and cast(float, card["price"]) > 0)
        require(Decimal(str(card["price"])) % CENT == 0)
        require(integer(card.get("stock_quantity"), minimum=1))
        require(card.get("voltage") in ("127V", "220V", "BIVOLT", "N/A"))
        require(card.get("capacity_liters") is None or number(card["capacity_liters"]))
        require(card.get("power_watts") is None or integer(card["power_watts"]))
        require(card.get("marketplace") in ("AMAZON", "MERCADO_LIVRE", "SHOPEE", "LOJA_OFICIAL"))
        role = card.get("recommendation_type")
        require(role in ("PRIMARY", "UPSELL", "CROSS_SELL") and role not in roles)
        roles.add(cast(str, role))
    return cast(list[ProductCard], payload)


def parse(item: Mapping[str, object]) -> tuple[str, Mapping[str, object]]:
    event = item.get("event")
    require(isinstance(event, str) and event in CONTENT_EVENTS | {"end"})
    payload = object_payload(item.get("data"))
    # Reject NaN, non-JSON values and unexpected adapter types before publication.
    json.dumps(payload, allow_nan=False)
    if event == "token":
        strings(payload, ("delta",))
    elif event == "correction":
        require(payload.get("violation_code") == "STREAM_INTERRUPTED")
        strings(payload, ("content",))
    elif event == "citations":
        citations(payload.get("citations"))
    elif event == "recommendations":
        products(payload.get("products"))
    elif event == "error":
        require(payload.get("code") in ERROR_CODES)
        require(type(payload.get("recoverable")) is bool)
        strings(payload, ("fallback_message",))
    elif event == "end":
        require(integer(payload.get("tokens_used")))
        require("intent" not in payload or isinstance(payload["intent"], str))
    return cast(str, event), payload
