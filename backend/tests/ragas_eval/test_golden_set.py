"""Tests for the RAGAS Golden Set and evaluation runner (B05 / EAP 5.1)."""

import json
from pathlib import Path
import pytest

FIXTURE_PATH = Path(__file__).parent / "golden_set.json"
CATALOG_PATH = Path(__file__).parents[3] / "data" / "catalog.json"


def test_golden_set_file_and_schema() -> None:
    """Task 1: Verify golden_set.json exists, has 50 valid items and matches categories."""
    assert FIXTURE_PATH.is_file(), f"Fixture file not found: {FIXTURE_PATH}"
    
    with open(FIXTURE_PATH, "r", encoding="utf-8") as f:
        cases = json.load(f)
    
    assert isinstance(cases, list)
    assert len(cases) == 50, f"Expected 50 cases, found {len(cases)}"
    
    with open(CATALOG_PATH, "r", encoding="utf-8") as f:
        catalog = json.load(f)
    valid_skus = {item["sku"] for item in catalog}
    
    cat_counts = {
        "Técnica Exata": 0,
        "Voltagem Crítica": 0,
        "Coloquial / Medida": 0,
        "Upsell + Cross-sell": 0,
        "Adversarial / Sem Evidência": 0,
    }
    
    seen_ids = set()
    for idx, case in enumerate(cases, start=1):
        case_id = case.get("id")
        assert case_id == f"RAGAS-GS-{idx:02d}", f"Invalid id {case_id} at index {idx}"
        assert case_id not in seen_ids, f"Duplicate id {case_id}"
        seen_ids.add(case_id)
        
        category = case.get("category")
        assert category in cat_counts, f"Unknown category: {category} in {case_id}"
        cat_counts[category] += 1
        
        assert case.get("query"), f"Missing query in {case_id}"
        assert isinstance(case.get("input_filters"), dict), f"input_filters must be dict in {case_id}"
        sku = case["input_filters"].get("sku")
        if sku:
            assert sku in valid_skus, f"Unknown SKU {sku} in {case_id}"
            
        assert case.get("expected_action") in {"ANSWER", "REFUSE", "FALLBACK"}
        assert isinstance(case.get("answerable"), bool)
        assert case.get("expected_answer"), f"Missing expected_answer in {case_id}"
        assert isinstance(case.get("expected_citations"), list)
        assert isinstance(case.get("relevant_chunk_ids"), list)
        assert isinstance(case.get("applicable_metrics"), list)
        assert case.get("business_rule"), f"Missing business_rule in {case_id}"

    assert cat_counts["Técnica Exata"] == 12
    assert cat_counts["Voltagem Crítica"] == 10
    assert cat_counts["Coloquial / Medida"] == 10
    assert cat_counts["Upsell + Cross-sell"] == 10
    assert cat_counts["Adversarial / Sem Evidência"] == 8


def test_models_parsing_and_validation() -> None:
    """Task 2: Verify Pydantic models parse golden_set.json and validate constraints."""
    from .models import GoldenSetFixture, EvalCaseResult, EvaluationReport, GateResult
    
    with open(FIXTURE_PATH, "r", encoding="utf-8") as f:
        data = json.load(f)
    
    fixtures = [GoldenSetFixture.model_validate(item) for item in data]
    assert len(fixtures) == 50
    assert fixtures[0].id == "RAGAS-GS-01"
    assert fixtures[0].category == "Técnica Exata"
    assert fixtures[0].expected_action == "ANSWER"
    assert fixtures[0].answerable is True
    
    # Test EvalCaseResult instantiation
    case_res = EvalCaseResult(
        case_id="RAGAS-GS-01",
        category="Técnica Exata",
        expected_action="ANSWER",
        actual_action="ANSWER",
        answerable=True,
        actual_answer="Resposta válida",
        actual_citations=["Manual Airfryer SmartChef 4L, p. 14"],
        retrieved_chunks=["AF-400-220V:p14:c1"],
        faithfulness=1.0,
        answer_relevance=0.95,
        precision_at_5=1.0,
        precision_returned=1.0,
        recall=1.0,
        technical_hallucination=False,
        business_rule_adherence=True,
        action_matched=True,
    )
    assert case_res.action_matched is True
    
    # Test GateResult and EvaluationReport
    gate = GateResult(
        metric_name="Faithfulness",
        value=0.92,
        threshold=0.85,
        comparator=">=",
        passed=True,
        description="Fidelidade macro"
    )
    assert gate.passed is True
    
    report = EvaluationReport(
        total_cases=50,
        evaluated_cases=50,
        faithfulness_macro=0.92,
        precision_at_5_macro=0.88,
        technical_hallucination_rate=0.0,
        answer_relevance_macro=0.91,
        business_rule_adherence_rate=1.0,
        action_accuracy=1.0,
        gates=[gate],
        all_gates_passed=True,
        case_results=[case_res]
    )
    assert report.all_gates_passed is True
