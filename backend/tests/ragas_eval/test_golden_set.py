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


def test_metrics_calculations_and_gates() -> None:
    """Task 3: Test deterministic metrics calculation and quality gates."""
    from .metrics import (
        calculate_faithfulness,
        calculate_retrieval_precision,
        calculate_technical_hallucination,
        calculate_answer_relevance,
        calculate_business_rule_adherence,
        aggregate_macro_metrics,
    )
    from .models import EvalCaseResult
    
    # 1. Faithfulness
    context = ["A Airfryer SmartChef 4L opera em 220V com potencia de 1500W.", "Manual Airfryer SmartChef 4L, p. 5"]
    faithful_ans = "A Airfryer 4L possui potencia de 1500W e voltagem de 220V."
    hallucinated_ans = "A Airfryer opera em 127V com 3000W e fritura a laser."
    
    f_score_high = calculate_faithfulness(faithful_ans, context)
    f_score_low = calculate_faithfulness(hallucinated_ans, context)
    assert f_score_high >= 0.85
    assert f_score_low < 0.50
    
    # 2. Retrieval Precision & Recall
    rel_ids = ["chunk_1", "chunk_2"]
    ret_ids = ["chunk_1", "chunk_2", "chunk_3"]
    p5, p_ret, rec = calculate_retrieval_precision(ret_ids, rel_ids)
    assert p5 is None  # < 5 relevant chunks in fixture
    assert p_ret == pytest.approx(2 / 3, abs=1e-3)
    assert rec == pytest.approx(1.0)
    
    rel_5 = [f"c_{i}" for i in range(5)]
    ret_5 = ["c_0", "c_1", "c_2", "c_3", "other"]
    p5_val, _, _ = calculate_retrieval_precision(ret_5, rel_5)
    assert p5_val == 0.80
    
    # 3. Technical Hallucination
    # Critical inversion: 220V product claimed as 127V
    has_hallucination = calculate_technical_hallucination(
        actual_answer="Este aparelho funciona perfeitamente em 127V.",
        expected_answer="O modelo opera exclusivamente em 220V.",
        input_filters={"sku": "AF-400-220V", "voltage": "220V"},
        evidence_texts=["Tensao: 220V exclusivo."]
    )
    assert has_hallucination is True
    
    no_hallucination = calculate_technical_hallucination(
        actual_answer="O modelo AF-400-220V opera em 220V e 1500W.",
        expected_answer="O modelo opera exclusivamente em 220V.",
        input_filters={"sku": "AF-400-220V", "voltage": "220V"},
        evidence_texts=["Tensao: 220V exclusivo. Potencia: 1500W."]
    )
    assert no_hallucination is False
    
    # 4. Answer Relevance
    rel = calculate_answer_relevance(
        query="Qual a voltagem?",
        actual_answer="A voltagem do aparelho e 220V, opera em 220V.",
        expected_answer="Opera em 220V."
    )
    assert rel >= 0.85
    
    # 5. Business Rule Adherence
    adherent = calculate_business_rule_adherence(
        actual_answer="Sugerimos a Airfryer 5.5L por R$ 629,90.",
        input_filters={"sku": "AF-400-220V"},
        stock_quantity=8
    )
    assert adherent is True
    
    # 6. Macro aggregation and Gates
    res1 = EvalCaseResult(
        case_id="RAGAS-GS-01",
        category="Técnica Exata",
        expected_action="ANSWER",
        actual_action="ANSWER",
        answerable=True,
        faithfulness=0.95,
        answer_relevance=0.92,
        precision_at_5=0.85,
        precision_returned=0.85,
        recall=1.0,
        technical_hallucination=False,
        business_rule_adherence=True,
        action_matched=True
    )
    res2 = EvalCaseResult(
        case_id="RAGAS-GS-43",
        category="Adversarial / Sem Evidência",
        expected_action="REFUSE",
        actual_action="REFUSE",
        answerable=False,
        faithfulness=None,
        answer_relevance=None,
        precision_at_5=None,
        precision_returned=None,
        recall=None,
        technical_hallucination=False,
        business_rule_adherence=True,
        action_matched=True
    )
    
    report = aggregate_macro_metrics([res1, res2])
    assert report.total_cases == 2
    assert report.faithfulness_macro == 0.95
    assert report.technical_hallucination_rate == 0.0
    assert report.action_accuracy == 1.0
    assert report.all_gates_passed is True
