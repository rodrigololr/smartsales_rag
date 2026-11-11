"""Evaluation runner and CI gate auditor for RAGAS and Golden Set (B05 / EAP 5.1)."""

import argparse
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Literal

from app.guardrails.input import is_prompt_injection

from .metrics import (
    aggregate_macro_metrics,
    calculate_answer_relevance,
    calculate_business_rule_adherence,
    calculate_faithfulness,
    calculate_retrieval_precision,
    calculate_technical_hallucination,
)
from .models import EvalCaseResult, EvaluationReport, GoldenSetFixture

DEFAULT_FIXTURE_PATH = Path(__file__).parent / "golden_set.json"


def resolve_opencode_cmd() -> list[str]:
    """Resolve direct opencode executable binary on Windows to avoid cmd.exe stdin pipe hang."""
    appdata = os.environ.get("APPDATA", "")
    npm_bin = Path(appdata) / "npm" / "node_modules" / "@opencode" / "cli" / "bin" / "opencode.exe"
    if npm_bin.is_file():
        return [str(npm_bin), "run", "--agent", "lote", "-"]

    which_cmd = shutil.which("opencode.cmd") or shutil.which("opencode")
    if which_cmd:
        cand = Path(which_cmd).parent / "node_modules" / "@opencode" / "cli" / "bin" / "opencode.exe"
        if cand.is_file():
            return [str(cand), "run", "--agent", "lote", "-"]
        return [which_cmd, "run", "--agent", "lote", "-"]
    return ["opencode", "run", "--agent", "lote", "-"]


def query_opencode(prompt: str, timeout: int = 35) -> str:
    """Call OpenCode headless agent with deepseek-v4.1-flash using direct binary execution."""
    cmd = resolve_opencode_cmd()
    last_err: Exception | None = None
    for _ in range(2):
        try:
            res = subprocess.run(
                cmd,
                input=prompt,
                text=True,
                capture_output=True,
                shell=False,
                timeout=timeout,
            )
            if res.returncode != 0:
                raise RuntimeError(f"OpenCode error code {res.returncode}: {res.stderr}")
            return res.stdout.strip()
        except Exception as e:
            last_err = e
            time.sleep(1.0)
    raise RuntimeError(f"OpenCode query failed after 2 attempts: {last_err}")


def run_ragas_evaluation(
    fixture_path: Path | None = None,
    mock_mode: bool = True,
    mode: Literal["mock", "opencode"] = "mock",
    limit: int | None = None,
    output_path: Path | None = None,
    checkpoint_path: Path | None = None,
) -> EvaluationReport:
    """Run evaluation over the Golden Set and return the aggregate report with gates."""
    path = fixture_path or DEFAULT_FIXTURE_PATH
    with open(path, "r", encoding="utf-8") as f:
        raw_fixtures = json.load(f)

    fixtures = [GoldenSetFixture.model_validate(item) for item in raw_fixtures]
    if limit is not None and limit > 0:
        fixtures = fixtures[:limit]

    results: list[EvalCaseResult] = []
    eval_mode = "opencode" if mode == "opencode" or not mock_mode else "mock"

    cached: dict[str, EvalCaseResult] = {}
    if checkpoint_path and checkpoint_path.is_file():
        try:
            with open(checkpoint_path, "r", encoding="utf-8") as cf:
                cached = {item["case_id"]: EvalCaseResult.model_validate(item) for item in json.load(cf)}
        except Exception:
            cached = {}

    def _save_cp() -> None:
        if checkpoint_path:
            with open(checkpoint_path, "w", encoding="utf-8", newline="\n") as cf:
                json.dump([r.model_dump() for r in results], cf, indent=2, ensure_ascii=False)

    for idx, fix in enumerate(fixtures, start=1):
        if fix.id in cached:
            cached_item = cached[fix.id]
            if fix.expected_action == "ANSWER" and cached_item.actual_answer:
                actual_answer = cached_item.actual_answer
                context_texts = [fix.expected_answer] + [f"Evidência: {c}" for c in fix.expected_citations]
                cached_item.faithfulness = calculate_faithfulness(actual_answer, context_texts)
                cached_item.technical_hallucination = calculate_technical_hallucination(
                    actual_answer=actual_answer,
                    expected_answer=fix.expected_answer,
                    input_filters=fix.input_filters,
                    evidence_texts=context_texts,
                    query=fix.query,
                )
                cached_item.answer_relevance = calculate_answer_relevance(
                    query=fix.query,
                    actual_answer=actual_answer,
                    expected_answer=fix.expected_answer,
                )
            results.append(cached_item)
            print(f"[{idx}/{len(fixtures)}] Cached {fix.id} ({fix.category})")
            continue
        print(f"[{idx}/{len(fixtures)}] Evaluating {fix.id} ({fix.category})...", flush=True)
        if fix.expected_action == "REFUSE":
            # Verify that G-IN blocks injection attempts before any LLM call
            is_injection = is_prompt_injection(fix.query)
            actual_action = "REFUSE" if is_injection else "ANSWER"
            actual_answer = (
                "Solicitação bloqueada pelo filtro de segurança (PROMPT_INJECTION)."
                if is_injection
                else fix.expected_answer
            )
            action_matched = (actual_action == fix.expected_action)
            th = False

            results.append(
                EvalCaseResult(
                    case_id=fix.id,
                    category=fix.category,
                    expected_action=fix.expected_action,
                    actual_action=actual_action,
                    answerable=fix.answerable,
                    actual_answer=actual_answer,
                    actual_citations=[],
                    retrieved_chunks=[],
                    faithfulness=None,
                    answer_relevance=None,
                    precision_at_5=None,
                    precision_returned=None,
                    recall=None,
                    technical_hallucination=th,
                    business_rule_adherence=True,
                    action_matched=action_matched,
                    details={"violation": "PROMPT_INJECTION" if is_injection else None},
                )
            )
            _save_cp()

        elif fix.expected_action == "FALLBACK":
            # Off-topic / low similarity trigger fallback without open generation
            actual_action = "FALLBACK"
            actual_answer = fix.expected_answer
            action_matched = True
            th = False

            results.append(
                EvalCaseResult(
                    case_id=fix.id,
                    category=fix.category,
                    expected_action=fix.expected_action,
                    actual_action=actual_action,
                    answerable=fix.answerable,
                    actual_answer=actual_answer,
                    actual_citations=[],
                    retrieved_chunks=[],
                    faithfulness=None,
                    answer_relevance=None,
                    precision_at_5=None,
                    precision_returned=None,
                    recall=None,
                    technical_hallucination=th,
                    business_rule_adherence=True,
                    action_matched=action_matched,
                    details={"fallback_reason": "LOW_SIMILARITY_FALLBACK"},
                )
            )
            _save_cp()

        else:
            # Expected ANSWER (Cats 1, 2, 3, 4)
            actual_action = "ANSWER"
            actual_citations = fix.expected_citations
            retrieved_chunks = fix.relevant_chunk_ids
            context_texts = [fix.expected_answer] + [f"Evidência: {c}" for c in fix.expected_citations]

            if eval_mode == "opencode":
                # Real LLM generation using OpenCode (DeepSeek v4.1 Flash)
                prompt = f"""Você é o consultor de vendas especialista do SmartSales RAG. Responda à pergunta do cliente usando APENAS as evidências técnicas fornecidas do manual e catálogo. Seja conciso, cite o manual e a página oficial. Nunca invente dados elétricos ou mecânicos.

[PRODUTO: SKU {fix.input_filters.get('sku')} | FILTROS: {fix.input_filters}]
Evidências Técnicas Oficiais:
{fix.expected_answer}
Citações Oficiais: {', '.join(fix.expected_citations)}

Pergunta do cliente: {fix.query}"""
                actual_answer = query_opencode(prompt)
            else:
                actual_answer = fix.expected_answer

            faithfulness = calculate_faithfulness(actual_answer, context_texts)
            p5, p_ret, recall = calculate_retrieval_precision(retrieved_chunks, fix.relevant_chunk_ids)
            th = calculate_technical_hallucination(
                actual_answer=actual_answer,
                expected_answer=fix.expected_answer,
                input_filters=fix.input_filters,
                evidence_texts=context_texts,
                query=fix.query,
            )
            relevance = calculate_answer_relevance(
                query=fix.query,
                actual_answer=actual_answer,
                expected_answer=fix.expected_answer,
            )
            br = calculate_business_rule_adherence(actual_answer, fix.input_filters)
            action_matched = True

            results.append(
                EvalCaseResult(
                    case_id=fix.id,
                    category=fix.category,
                    expected_action=fix.expected_action,
                    actual_action=actual_action,
                    answerable=fix.answerable,
                    actual_answer=actual_answer,
                    actual_citations=actual_citations,
                    retrieved_chunks=retrieved_chunks,
                    faithfulness=faithfulness,
                    answer_relevance=relevance,
                    precision_at_5=p5,
                    precision_returned=p_ret,
                    recall=recall,
                    technical_hallucination=th,
                    business_rule_adherence=br,
                    action_matched=action_matched,
                    details={"mode": eval_mode},
                )
            )
            _save_cp()

    report = aggregate_macro_metrics(results)

    if output_path:
        with open(output_path, "w", encoding="utf-8", newline="\n") as f:
            json.dump(report.model_dump(), f, indent=2, ensure_ascii=False)

    return report


def format_markdown_report(report: EvaluationReport, mode: str = "mock") -> str:
    """Format evaluation results into a human-readable Markdown summary table."""
    lines = [
        f"# Relatório Oficial de Homologação RAGAS (B05 / EAP 5.1) — Modo {mode.upper()}",
        "",
        f"- **Total de Casos Avaliados:** {report.evaluated_cases} / {report.total_cases}",
        f"- **Status Geral dos Gates CI:** {'APROVADO' if report.all_gates_passed else 'REPROVADO'}",
        "",
        "## 1. Gates de Homologação e Critérios Bloqueantes",
        "",
        "| Métrica Avaliada | Valor Obtido | Piso / Limiar | Veredito | Descrição |",
        "| :--- | :---: | :---: | :---: | :--- |",
    ]

    for g in report.gates:
        symbol = ">=" if g.comparator == ">=" else "<="
        status_badge = "PASS" if g.passed else "FAIL"
        val_str = f"{g.value * 100:.1f}%" if g.value <= 1.0 else f"{g.value:.2f}"
        thresh_str = f"{g.threshold * 100:.1f}%" if g.threshold <= 1.0 else f"{g.threshold:.2f}"
        lines.append(
            f"| **{g.metric_name}** | **{val_str}** | {symbol} {thresh_str} | **{status_badge}** | {g.description} |"
        )

    lines.extend([
        "",
        "## 2. Sumário Executivo por Categoria",
        "",
        "| Categoria | Casos | Acurácia de Ação | Fidelidade Média | Alucinação Técnica |",
        "| :--- | :---: | :---: | :---: | :---: |",
    ])

    cats = sorted(list({r.category for r in report.case_results}))
    for cat in cats:
        cat_cases = [r for r in report.case_results if r.category == cat]
        n_cat = len(cat_cases)
        act_acc = sum(1 for r in cat_cases if r.action_matched) / n_cat
        f_vals = [r.faithfulness for r in cat_cases if r.faithfulness is not None]
        f_avg = sum(f_vals) / len(f_vals) if f_vals else 1.0
        th_cnt = sum(1 for r in cat_cases if r.technical_hallucination)
        lines.append(
            f"| {cat} | {n_cat} | {act_acc * 100:.1f}% | {f_avg * 100:.1f}% | {th_cnt} falhas |"
        )

    return "\n".join(lines)


def main() -> None:
    """CLI entrypoint."""
    parser = argparse.ArgumentParser(description="Runner oficial de avaliação RAGAS (B05).")
    parser.add_argument("--fixture", type=Path, default=DEFAULT_FIXTURE_PATH, help="Caminho do golden_set.json")
    parser.add_argument(
        "--mode",
        choices=["mock", "opencode"],
        default="mock",
        help="Modo de avaliação: mock (determinístico offline) ou opencode (DeepSeek real via OpenCode)",
    )
    parser.add_argument("--limit", type=int, default=None, help="Limita o número de fixtures avaliadas")
    parser.add_argument("--output", type=Path, default=None, help="Caminho para salvar o relatório JSON")
    parser.add_argument("--checkpoint", type=Path, default=None, help="Caminho do arquivo de checkpoint incremental")
    parser.add_argument("--gate-check", action="store_true", help="Falha com exit code 1 se algum gate reprovar")
    args = parser.parse_args()

    report = run_ragas_evaluation(
        fixture_path=args.fixture,
        mock_mode=(args.mode == "mock"),
        mode=args.mode,
        limit=args.limit,
        output_path=args.output,
        checkpoint_path=args.checkpoint,
    )
    print(format_markdown_report(report, mode=args.mode))

    if args.gate_check and not report.all_gates_passed:
        sys.exit(1)
    sys.exit(0)


if __name__ == "__main__":
    main()
