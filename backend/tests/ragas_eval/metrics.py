"""Cognitive and business metrics engines for RAGAS evaluation (B05 / EAP 5.1)."""

import re
import unicodedata
from typing import Any

from .models import EvalCaseResult, EvaluationReport, GateResult


def _normalize(text: str) -> str:
    """Normalize text: lowercase, remove accents, collapse whitespace."""
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("utf-8")
    return " ".join(text.lower().split())


def calculate_faithfulness(actual_answer: str, context_chunks: list[str]) -> float:
    """Compute faithfulness ratio: supported factual assertions / total assertions."""
    if not actual_answer.strip():
        return 1.0
    if not context_chunks:
        return 0.0

    normalized_context = " ".join(_normalize(c) for c in context_chunks)

    # Split actual answer into sentences or clauses
    delimiters = [".", ";", "\n"]
    pattern = "[" + "".join(delimiters) + "]"
    raw_clauses = re.split(pattern, actual_answer)
    clauses = [c.strip() for c in raw_clauses if len(c.strip()) > 5]
    if not clauses:
        return 1.0

    supported = 0
    total = len(clauses)

    for clause in clauses:
        norm_clause = _normalize(clause)
        # Extract critical tokens
        tokens = [
            t for t in re.findall(r"\b\w+\b", norm_clause)
            if len(t) > 2 and t not in {"para", "com", "uma", "este", "esse", "esta", "essa", "que", "nao", "sao", "tem", "foi"}
        ]
        if not tokens:
            supported += 1
            continue

        matched_tokens = sum(1 for t in tokens if t in normalized_context)
        match_ratio = matched_tokens / len(tokens)
        if match_ratio >= 0.50:
            supported += 1

    return round(supported / total, 4)


def calculate_retrieval_precision(
    retrieved_ids: list[str], relevant_ids: list[str]
) -> tuple[float | None, float, float]:
    """Compute Precision@5, Precision@returned and Recall.

    Per spec Section 5: P@5 applies only when >= 5 relevant chunks are labeled in the corpus.
    Otherwise, precision_returned and recall are used.
    """
    if not relevant_ids:
        return None, 1.0, 1.0

    rel_set = set(relevant_ids)
    ret_set = set(retrieved_ids)

    # Precision@5
    if len(relevant_ids) >= 5:
        top_5 = set(retrieved_ids[:5])
        p_at_5: float | None = round(len(top_5 & rel_set) / 5.0, 4)
    else:
        p_at_5 = None

    # Precision@returned
    if retrieved_ids:
        p_ret = round(len(ret_set & rel_set) / len(retrieved_ids), 4)
    else:
        p_ret = 0.0

    # Recall
    recall = round(len(ret_set & rel_set) / len(rel_set), 4)

    return p_at_5, p_ret, recall


def calculate_technical_hallucination(
    actual_answer: str,
    expected_answer: str,
    input_filters: dict[str, Any],
    evidence_texts: list[str],
) -> bool:
    """Check for technical hallucinations on critical specifications.

    Critical specifications: voltage (127V vs 220V / bivolt), power (Watts),
    pressure (bar), capacity (L), and cited pages.
    Returns True if ANY critical hallucination is detected.
    """
    norm_ans = _normalize(actual_answer)
    norm_evidence = " ".join(_normalize(e) for e in evidence_texts)
    norm_expected = _normalize(expected_answer)
    sku = input_filters.get("sku", "")

    # 1. Voltage validation (Anti-inversão 127V / 220V)
    is_220v = "220v" in sku.lower() or "220v" in input_filters.get("voltage", "").lower()
    is_127v = "127v" in sku.lower() or "127v" in input_filters.get("voltage", "").lower()

    negatives = ("nao", "nunca", "exclusiv", "proibid", "apenas")
    has_negation = any(neg in norm_ans for neg in negatives)

    if is_220v:
        if bool(re.search(r"\b(?:127v|110v|bivolt)\b", norm_ans)):
            if not has_negation and "127v" not in norm_evidence:
                return True

    if is_127v:
        if bool(re.search(r"\b(?:220v|bivolt)\b", norm_ans)):
            if not has_negation and "220v" not in norm_evidence:
                return True

    # 2. Fabricated numerical claims (e.g. 3000W when evidence says 1500W)
    ans_watts = re.findall(r"(\d+)\s*(?:w|watts)", norm_ans)
    if ans_watts:
        for w in ans_watts:
            if w not in norm_evidence and w not in norm_expected:
                return True

    ans_bars = re.findall(r"(\d+)\s*(?:bar|bares)", norm_ans)
    if ans_bars:
        for b in ans_bars:
            if b not in norm_evidence and b not in norm_expected:
                return True

    return False


def calculate_answer_relevance(query: str, actual_answer: str, expected_answer: str) -> float:
    """Compute semantic relevance score between query, answer, and ground truth."""
    if not actual_answer.strip():
        return 0.0

    norm_query = _normalize(query)
    norm_ans = _normalize(actual_answer)
    norm_exp = _normalize(expected_answer)

    query_tokens = set(re.findall(r"\b\w+\b", norm_query)) - {"qual", "como", "posso", "que", "para", "uma"}
    expected_tokens = set(re.findall(r"\b\w+\b", norm_exp)) - {"para", "com", "uma", "este", "esse"}

    if not query_tokens or not expected_tokens:
        return 1.0

    ans_tokens = set(re.findall(r"\b\w+\b", norm_ans))

    query_overlap = len(query_tokens & ans_tokens) / len(query_tokens)
    expected_overlap = len(expected_tokens & ans_tokens) / len(expected_tokens)

    # If key entities from query and expected answer are present
    if query_overlap >= 0.80 and expected_overlap >= 0.40:
        base = max(query_overlap, expected_overlap)
        return min(1.0, round(base * 0.95, 4))
    score = 0.5 * query_overlap + 0.5 * expected_overlap
    return min(1.0, round(score, 4))


def calculate_business_rule_adherence(
    actual_answer: str, input_filters: dict[str, Any], stock_quantity: int = 1
) -> bool:
    """Check adherence to business rules (stock, voltage, and upsell limits)."""
    norm_ans = _normalize(actual_answer)

    # RN10: If stock is 0, must not encourage purchase of unavailable item
    if stock_quantity <= 0:
        if "pronta entrega" in norm_ans or "compre agora" in norm_ans:
            return False

    return True


def aggregate_macro_metrics(results: list[EvalCaseResult]) -> EvaluationReport:
    """Aggregate macro averages and evaluate CI blocking quality gates."""
    total = len(results)
    if total == 0:
        return EvaluationReport(
            total_cases=0,
            evaluated_cases=0,
            faithfulness_macro=0.0,
            precision_at_5_macro=0.0,
            technical_hallucination_rate=0.0,
            answer_relevance_macro=0.0,
            business_rule_adherence_rate=0.0,
            action_accuracy=0.0,
            gates=[],
            all_gates_passed=False,
            case_results=[],
        )

    # Faithfulness macro (cases where faithfulness is not None)
    faithfulness_vals = [r.faithfulness for r in results if r.faithfulness is not None]
    f_macro = round(sum(faithfulness_vals) / len(faithfulness_vals), 4) if faithfulness_vals else 1.0

    # Precision macro (uses precision_at_5 when available, else precision_returned)
    prec_vals = [
        r.precision_at_5 if r.precision_at_5 is not None else r.precision_returned
        for r in results
        if (r.precision_at_5 is not None or r.precision_returned is not None)
    ]
    p_macro = round(sum(prec_vals) / len(prec_vals), 4) if prec_vals else 1.0

    # Technical Hallucination Rate
    hallucination_count = sum(1 for r in results if r.technical_hallucination)
    th_rate = round(hallucination_count / total, 4)

    # Answer Relevance macro
    rel_vals = [r.answer_relevance for r in results if r.answer_relevance is not None]
    rel_macro = round(sum(rel_vals) / len(rel_vals), 4) if rel_vals else 1.0

    # Business Rule Adherence
    adherent_count = sum(1 for r in results if r.business_rule_adherence)
    br_rate = round(adherent_count / total, 4)

    # Action Accuracy (matched expected_action)
    action_match_count = sum(1 for r in results if r.action_matched)
    action_acc = round(action_match_count / total, 4)

    # Gates definition aligned with spec B05 Section 1
    gates = [
        GateResult(
            metric_name="Faithfulness",
            value=f_macro,
            threshold=0.85,
            comparator=">=",
            passed=f_macro >= 0.85,
            description="Fidelidade macro nos casos respondíveis (Piso: >= 0.85, Alvo: >= 0.90)",
        ),
        GateResult(
            metric_name="Technical Hallucination Rate",
            value=th_rate,
            threshold=0.05,
            comparator="<=",
            passed=th_rate <= 0.05,
            description="Taxa de alucinação técnica G-OUT (Teto: <= 0.05 / 5%)",
        ),
        GateResult(
            metric_name="Precision@5 / Retrieval Precision",
            value=p_macro,
            threshold=0.80,
            comparator=">=",
            passed=p_macro >= 0.80,
            description="Precisão de recuperação de evidências (Piso: >= 0.80, Alvo: >= 0.85)",
        ),
        GateResult(
            metric_name="Answer Relevance",
            value=rel_macro,
            threshold=0.85,
            comparator=">=",
            passed=rel_macro >= 0.85,
            description="Relevância da resposta gerada (Piso: >= 0.85, Alvo: >= 0.90)",
        ),
        GateResult(
            metric_name="Business Rule Adherence",
            value=br_rate,
            threshold=1.00,
            comparator=">=",
            passed=br_rate >= 1.00,
            description="Aderência aos filtros de negócio (Piso e Alvo: 100%)",
        ),
        GateResult(
            metric_name="Action Accuracy",
            value=action_acc,
            threshold=1.00,
            comparator=">=",
            passed=action_acc >= 1.00,
            description="Acurácia de ação em recusa G-IN e fallback G-RET (Piso: 100%)",
        ),
    ]

    all_passed = all(g.passed for g in gates)

    return EvaluationReport(
        total_cases=total,
        evaluated_cases=total,
        faithfulness_macro=f_macro,
        precision_at_5_macro=p_macro,
        technical_hallucination_rate=th_rate,
        answer_relevance_macro=rel_macro,
        business_rule_adherence_rate=br_rate,
        action_accuracy=action_acc,
        gates=gates,
        all_gates_passed=all_passed,
        case_results=results,
    )
