"""Canonical cache identity; transport, storage and history resolution stay outside."""

import hashlib
import json
import unicodedata
from collections.abc import Mapping, Sequence
from decimal import Decimal
from typing import TypeAlias

JSONValue: TypeAlias = (
    str | int | float | Decimal | None | list["JSONValue"] | dict[str, "JSONValue"]
)

_TEXT_FILTERS = frozenset({"preferred_voltage", "category", "current_product_sku"})
_NUMBER_FILTERS = frozenset({"capacity_min", "budget_max"})
_FILTER_FIELDS = _TEXT_FILTERS | _NUMBER_FILTERS


def _resolved_filter_snapshot(resolved_filters: Mapping[str, object]) -> dict[str, JSONValue]:
    if unknown := resolved_filters.keys() - _FILTER_FIELDS:
        raise ValueError(f"Unknown resolved filter fields: {sorted(unknown)}")
    snapshot: dict[str, JSONValue] = {}
    for field in _FILTER_FIELDS:
        value = resolved_filters.get(field)
        if value is None:
            snapshot[field] = None
        elif field in _TEXT_FILTERS and isinstance(value, str):
            snapshot[field] = value
        elif field in _NUMBER_FILTERS and isinstance(value, (int, float, Decimal)):
            if isinstance(value, bool):
                raise TypeError(f"Resolved filter {field} must be a JSON number, not bool")
            snapshot[field] = value
        else:
            raise TypeError(f"Unsupported value for resolved filter {field}")
    return snapshot


def _history_snapshot(history: Sequence[Mapping[str, str]]) -> list[JSONValue]:
    snapshot: list[JSONValue] = []
    for message in history:
        if message.keys() != {"role", "content"}:
            raise ValueError("Each history message requires exactly role and content")
        if message["role"] not in {"user", "assistant"}:
            raise ValueError("Unsupported history role")
        if not isinstance(message["content"], str):
            raise ValueError("History content must be a string")
        snapshot.append({"role": message["role"], "content": message["content"]})
    return snapshot


def _canonical_json(value: JSONValue) -> str:
    """Match sorted compact UTF-8 JSON, with exact fixed-point Decimal numbers.

    Decimal retains its supplied scale, never passes through float, and is emitted
    as a JSON number. Callers should use a consistent numeric representation.
    """
    if isinstance(value, Decimal):
        if not value.is_finite():
            raise ValueError("Nonfinite numbers cannot enter cache identity")
        return format(value, "f")
    if isinstance(value, dict):
        return (
            "{"
            + ",".join(
                f"{_canonical_json(field)}:{_canonical_json(value[field])}"
                for field in sorted(value)
            )
            + "}"
        )
    if isinstance(value, list):
        return "[" + ",".join(_canonical_json(item) for item in value) + "]"
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), allow_nan=False)


def build_cache_key(
    catalog_version: str,
    query: str,
    resolved_filters: Mapping[str, object],
    history: Sequence[Mapping[str, str]],
    policy_version: str,
) -> str:
    """Hash a resolved complete turn context using the normative RN09 contract.

    The caller supplies previous user/assistant messages in chronological order,
    excluding the current turn. Nothing is truncated or inferred here. Only the
    query receives NFC/whitespace normalization; all history text is preserved.
    Missing known filter fields become null, unknown fields fail closed. The
    caller owns catalog/policy version resolution and cache-sharing decisions.
    """
    payload: JSONValue = {
        "catalog": catalog_version,
        "query": " ".join(unicodedata.normalize("NFC", query).split()),
        "filters": _resolved_filter_snapshot(resolved_filters),
        "history": _history_snapshot(history),
        "policy": policy_version,
    }
    digest = hashlib.sha256(_canonical_json(payload).encode("utf-8")).hexdigest()
    return f"cache:sem:{catalog_version}:{digest}"
