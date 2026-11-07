"""Synthetic M03 / RN09 identity cases; no Redis or real catalog fixtures."""

import hashlib
import json
from decimal import Decimal

import pytest
from app.cache import build_cache_key


def test_matches_normative_sorted_utf8_json() -> None:
    filters = {
        "preferred_voltage": "220V",
        "category": "eletroportáteis",
        "current_product_sku": "SYNTHETIC-4L",
        "capacity_min": 4,
        "budget_max": 600,
    }
    history = [
        {"role": "user", "content": "Minha bancada tem 30cm."},
        {"role": "assistant", "content": "Vamos conferir o manual."},
    ]
    # Independent wire-contract oracle, directly from the normative spec example.
    canonical = json.dumps(
        {
            "catalog": "v10",
            "query": "O cesto 4L cabe no 5L?",
            "filters": filters,
            "history": history,
            "policy": "policy-1",
        },
        sort_keys=True,
        ensure_ascii=False,
        separators=(",", ":"),
    )
    expected = "cache:sem:v10:" + hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    assert (
        build_cache_key("v10", "O cesto 4L cabe no 5L?", filters, history, "policy-1") == expected
    )


def test_nfc_and_whitespace_are_the_only_query_equivalences() -> None:
    assert build_cache_key("v10", "  É  4L?\n220V\t", {}, [], "p1") == build_cache_key(
        "v10", "E\u0301 4L? 220V", {}, [], "p1"
    )


@pytest.mark.parametrize(
    ("original", "changed"),
    [
        ("O cesto 4L cabe no 5L?", "O cesto 5L cabe no 4L?"),
        ("É 4L?", "é 4L?"),
        ("É 4L?", "E 4L?"),
        ("É 4L?", "É 4L!"),
        ("É 4L?", "É 5L?"),
    ],
)
def test_query_meaning_is_not_discarded(original: str, changed: str) -> None:
    assert build_cache_key("v10", original, {}, [], "p1") != build_cache_key(
        "v10", changed, {}, [], "p1"
    )


def test_missing_filters_equal_explicit_null_and_key_order_does_not_matter() -> None:
    complete = {
        "budget_max": None,
        "capacity_min": None,
        "current_product_sku": None,
        "category": None,
        "preferred_voltage": None,
    }
    assert build_cache_key("v10", "Qual?", {}, [], "p1") == build_cache_key(
        "v10", "Qual?", complete, [], "p1"
    )
    left = {"budget_max": 600, "preferred_voltage": "220V"}
    right = {"preferred_voltage": "220V", "budget_max": 600}
    assert build_cache_key("v10", "Qual?", left, [], "p1") == build_cache_key(
        "v10", "Qual?", right, [], "p1"
    )


@pytest.mark.parametrize(
    ("field", "first", "second"),
    [
        ("budget_max", 600, 700),
        ("capacity_min", 4, 5),
        ("current_product_sku", "SYNTHETIC-4L", "SYNTHETIC-5L"),
        ("preferred_voltage", "127V", "220V"),
        ("category", "eletroportateis", "monitores"),
    ],
)
def test_every_resolved_filter_participates(field: str, first: object, second: object) -> None:
    assert build_cache_key("v10", "Qual?", {field: first}, [], "p1") != build_cache_key(
        "v10", "Qual?", {field: second}, [], "p1"
    )


@pytest.mark.parametrize("change", ["content", "chronology", "role", "empty"])
def test_complete_history_snapshot_participates(change: str) -> None:
    original = [
        {"role": "user", "content": "Minha bancada tem 30cm."},
        {"role": "assistant", "content": "Vou conferir."},
    ]
    changed = [message.copy() for message in original]
    if change == "content":
        changed[0]["content"] = "Minha bancada tem 60cm."
    elif change == "chronology":
        changed.reverse()
    elif change == "role":
        changed[0]["role"] = "assistant"
    else:
        changed = []
    assert build_cache_key("v10", "Qual?", {}, original, "p1") != build_cache_key(
        "v10", "Qual?", {}, changed, "p1"
    )


def test_history_content_is_preserved_without_query_normalization() -> None:
    assert build_cache_key("v10", "Qual?", {}, [{"role": "user", "content": "É  4L"}], "p1") != (
        build_cache_key("v10", "Qual?", {}, [{"role": "user", "content": "É 4L"}], "p1")
    )


def test_catalog_and_policy_versions_invalidate_identity() -> None:
    original = build_cache_key("v10", "Qual?", {}, [], "p1")
    assert original != build_cache_key("v11", "Qual?", {}, [], "p1")
    assert original != build_cache_key("v10", "Qual?", {}, [], "p2")


def test_decimal_budget_is_exact_json_number_without_float_conversion() -> None:
    filters = {
        "budget_max": Decimal("12345678901234567890.12"),
        "capacity_min": None,
        "category": None,
        "current_product_sku": None,
        "preferred_voltage": None,
    }
    canonical = (
        '{"catalog":"v10","filters":{"budget_max":12345678901234567890.12,'
        '"capacity_min":null,"category":null,"current_product_sku":null,'
        '"preferred_voltage":null},"history":[],"policy":"p1","query":"Qual?"}'
    )
    expected = "cache:sem:v10:" + hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    assert build_cache_key("v10", "Qual?", filters, [], "p1") == expected


@pytest.mark.parametrize(
    "invalid", [float("nan"), float("inf"), float("-inf"), Decimal("NaN"), Decimal("Infinity")]
)
def test_nonfinite_numbers_fail_closed(invalid: object) -> None:
    with pytest.raises(ValueError):
        build_cache_key("v10", "Qual?", {"budget_max": invalid}, [], "p1")


@pytest.mark.parametrize("invalid", [object(), {1, 2}, b"600", True])
def test_unsupported_filter_values_fail_closed(invalid: object) -> None:
    with pytest.raises((TypeError, ValueError)):
        build_cache_key("v10", "Qual?", {"budget_max": invalid}, [], "p1")


def test_unknown_filters_are_rejected_instead_of_silently_dropped() -> None:
    with pytest.raises(ValueError, match="filter"):
        build_cache_key("v10", "Qual?", {"budget_max": 600, "voltage": "220V"}, [], "p1")


def test_invalid_history_is_not_silently_dropped() -> None:
    with pytest.raises(ValueError, match="history"):
        build_cache_key("v10", "Qual?", {}, [{"role": "system", "content": "instruction"}], "p1")
