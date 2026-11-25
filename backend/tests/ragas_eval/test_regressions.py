"""Negative controls: offline tests cannot certify live RAG quality."""

import json
from pathlib import Path

import pytest

from .corpus import Corpus
from .metrics import aggregate_macro_metrics, calculate_retrieval_precision, technical_violations
from .models import EvalCaseResult, GoldenSetFixture, RunIdentity

ROOT = Path(__file__).resolve().parents[3]


def test_fifty_cases_have_verifiable_sources_and_stock_zero_scenario() -> None:
    corpus = Corpus.from_seed(ROOT)
    fixtures = [
        GoldenSetFixture.model_validate(item)
        for item in json.loads((Path(__file__).with_name("golden_set.json")).read_text())
    ]
    assert len(fixtures) == 50
    for fixture in fixtures:
        corpus.validate_fixture(fixture)
    assert any(0 in f.stock_overrides.values() for f in fixtures)


@pytest.mark.parametrize(
    "answer",
    [
        "Sim, ela tem 3000W.",
        "Funciona em 127V, não possui temporizador.",
        "Custa R$ 99,90 e tem 99L.",
        "[Fonte: Manual Airfryer SmartChef 4L, p. 999]",
    ],
)
def test_question_negation_and_other_units_do_not_authorize_false_facts(answer: str) -> None:
    violations = technical_violations(
        answer,
        {"AF-400-220V": "Opera em 220V com potência de 1500W. Preço R$ 499,90."},
        [("AF-400-220V", "Manual Airfryer SmartChef 4L", 6)],
        primary_sku="AF-400-220V",
    )
    assert violations


def test_empty_retrieval_is_zero_not_missing_or_perfect() -> None:
    assert calculate_retrieval_precision([], ["evidence"]) == (None, 0.0, 0.0)


def test_absence_of_applicable_samples_cannot_pass() -> None:
    result = EvalCaseResult(case_id="negative", expected_action="REFUSE", actual_action="REFUSE")
    report = aggregate_macro_metrics([result], RunIdentity(mode="test"))
    assert report.faithfulness_macro is None
    assert report.precision_macro is None
    assert not report.all_gates_passed


def test_low_recall_cannot_be_hidden_by_perfect_precision() -> None:
    result = EvalCaseResult(
        case_id="answer",
        expected_action="ANSWER",
        actual_action="ANSWER",
        faithfulness=1.0,
        answer_relevance=1.0,
        precision_returned=1.0,
        recall=0.2,
        expected_metrics=["faithfulness", "answer_relevance", "retrieval"],
    )
    report = aggregate_macro_metrics([result], RunIdentity(mode="test"))
    assert not next(g for g in report.gates if g.metric_name == "Recall").passed


def test_offline_success_never_becomes_live_homologation() -> None:
    result = EvalCaseResult(
        case_id="answer",
        expected_action="ANSWER",
        actual_action="ANSWER",
        faithfulness=1.0,
        answer_relevance=1.0,
        precision_returned=1.0,
        recall=1.0,
        expected_metrics=["faithfulness", "answer_relevance", "retrieval"],
    )
    assert not aggregate_macro_metrics([result], RunIdentity(mode="test")).all_gates_passed


@pytest.mark.parametrize(
    "answer",
    [
        "A potência é 3000 W.",
        "A capacidade é 99 L.",
        "Custa 99,90 reais.",
        "A voltagem é 1500 W.",
    ],
)
def test_sql_attributes_override_stale_manual_numbers(answer: str) -> None:
    from .corpus import Corpus

    product = Corpus.from_seed(ROOT).products["AF-400-220V"]
    assert technical_violations(
        answer,
        {product.sku: "Potência 3000 W, capacidade 99 L."},
        [],
        primary_sku=product.sku,
        products={product.sku: product},
    )


def test_duplicate_fifty_results_cannot_certify_a_full_run() -> None:
    result = EvalCaseResult(
        case_id="RAGAS-GS-01",
        expected_action="ANSWER",
        actual_action="ANSWER",
        expected_metrics=["faithfulness", "answer_relevance", "retrieval"],
        faithfulness=1,
        answer_relevance=1,
        precision_returned=1,
        recall=1,
    )
    identity = RunIdentity(
        mode="live",
        revision="revision",
        fingerprint="fingerprint",
        corpus_verified=True,
        clean_checkout=True,
        integrated_b04=True,
        po_audit_approved=True,
        judge_model="independent",
        generator_model="generator",
    )
    report = aggregate_macro_metrics([result] * 50, identity)
    assert not report.all_gates_passed


def test_unintegrated_live_execution_cannot_be_homologated() -> None:
    results = [
        EvalCaseResult(
            case_id=f"RAGAS-GS-{i:02}",
            expected_action="ANSWER",
            actual_action="ANSWER",
            expected_metrics=["faithfulness", "answer_relevance", "retrieval"],
            faithfulness=1,
            answer_relevance=1,
            precision_returned=1,
            recall=1,
        )
        for i in range(1, 51)
    ]
    report = aggregate_macro_metrics(
        results,
        RunIdentity(
            mode="live",
            revision="revision",
            fingerprint="fingerprint",
            corpus_verified=True,
            clean_checkout=True,
            po_audit_approved=True,
            judge_model="independent",
            generator_model="generator",
        ),
    )
    assert not report.all_gates_passed


def test_complete_integrated_audited_observations_can_pass_the_aggregator() -> None:
    from .models import ObservedTurn

    results = [
        EvalCaseResult(
            case_id=f"RAGAS-GS-{i:02}",
            expected_action="ANSWER",
            actual_action="ANSWER",
            expected_metrics=["faithfulness", "answer_relevance", "retrieval"],
            faithfulness=1,
            answer_relevance=1,
            precision_returned=1,
            recall=1,
            observation=ObservedTurn(action="ANSWER", answer="Dados de teste"),
        )
        for i in range(1, 51)
    ]
    identity = RunIdentity(
        mode="live",
        revision="revision",
        fingerprint="fingerprint",
        corpus_verified=True,
        clean_checkout=True,
        integrated_b04=True,
        po_audit_approved=True,
        judge_model="independent",
        generator_model="generator",
    )
    assert aggregate_macro_metrics(results, identity).all_gates_passed
    results[0].technical_violations.append("Critical voltage inversion")
    assert not aggregate_macro_metrics(results, identity).all_gates_passed


def test_valid_sql_price_and_units_are_not_reported_as_hallucinations(corpus: Corpus) -> None:
    product = corpus.products["AF-400-220V"]
    for text in (
        "Voltagem: 220V.",
        "A potência é 1,5 kW.",
        "Possui capacidade de 4000 mL.",
        "Preço atual: R$ 499,90.",
        "Custa 499.90 reais.",
    ):
        assert not technical_violations(
            text,
            {product.sku: "Manual de demonstração"},
            [],
            primary_sku=product.sku,
            products={product.sku: product},
        ), text


def test_pressure_in_catalog_sheet_only_supports_its_recorded_value(corpus: Corpus) -> None:
    product = corpus.products["CF-20B-127V"]
    citation = (product.sku, "Ficha técnica Aroma Pro 2L", 1)

    def violations(pressure: int) -> list[str]:
        return technical_violations(
            f"A pressão é de {pressure} bar [Fonte: Ficha técnica Aroma Pro 2L, p. 1].",
            {product.sku: "pressao_bar: 19\nOutro manual menciona 21 bar."},
            [citation],
            primary_sku=product.sku,
            products={product.sku: product},
            evidence_by_page={citation: "pressao_bar: 19\r\n"},
        )

    assert not violations(19)
    assert violations(21)


def test_citation_page_must_support_the_claim_not_just_exist(corpus: Corpus) -> None:
    product = corpus.products["AF-400-220V"]
    answer = "A potência é 1500 W [Fonte: Manual Airfryer SmartChef 4L, p. 7]."
    assert technical_violations(
        answer,
        {product.sku: "Potência de 1500 W."},
        [(product.sku, "Manual Airfryer SmartChef 4L", 7)],
        primary_sku=product.sku,
        products={product.sku: product},
        evidence_by_page={
            (product.sku, "Manual Airfryer SmartChef 4L", 7): "Limpe o cesto com detergente neutro."
        },
    )


def test_unknown_sku_cannot_borrow_the_consulted_products_price(corpus: Corpus) -> None:
    product = corpus.products["AF-400-220V"]
    assert technical_violations(
        "O AF-999-220V custa R$ 499,90.",
        {product.sku: "Preço R$ 499,90."},
        [],
        primary_sku=product.sku,
        products={product.sku: product},
    )
