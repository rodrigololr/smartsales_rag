"""B05: validate seed offline, or evaluate the actual pipeline with an independent RAGAS judge."""

import argparse
import asyncio
import json
from collections import Counter
from pathlib import Path

from app.clients.openai_client import OpenAIChatModel, OpenAIEmbedder, make_client
from app.config import Settings
from app.db.repository import PostgresCatalog

from .checkpoint import load_checkpoint, make_identity, save_checkpoint, write_json
from .corpus import Corpus
from .judge import CognitiveJudge, JudgeSettings, RagasJudge, checked_score
from .metrics import (
    CITATION,
    aggregate_macro_metrics,
    business_violations,
    calculate_retrieval_precision,
    technical_violations,
)
from .models import EvalCaseResult, EvaluationReport, GoldenSetFixture, ObservedTurn, RunIdentity
from .pipeline import Pipeline, ProductionPipeline
from .retry import ProviderRetry, RetrySettings

ROOT = Path(__file__).resolve().parents[3]
DEFAULT_FIXTURE_PATH = Path(__file__).with_name("golden_set.json")
CATEGORY_COUNTS = {
    "Técnica Exata": 12,
    "Voltagem Crítica": 10,
    "Coloquial / Medida": 10,
    "Upsell + Cross-sell": 10,
    "Adversarial / Sem Evidência": 8,
}


def load_fixtures(path: Path, corpus: Corpus) -> list[GoldenSetFixture]:
    fixtures = [GoldenSetFixture.model_validate(item) for item in json.loads(path.read_bytes())]
    if [f.id for f in fixtures] != [f"RAGAS-GS-{i:02}" for i in range(1, 51)]:
        raise ValueError("The complete ordered Golden Set must contain 50 unique cases")
    if Counter(f.category for f in fixtures) != CATEGORY_COUNTS:
        raise ValueError("Golden Set category counts differ from the B05 specification")
    for fixture in fixtures:
        corpus.validate_fixture(fixture)
    return fixtures


def _deterministic_checks(
    fixture: GoldenSetFixture, turn: ObservedTurn, corpus: Corpus
) -> EvalCaseResult:
    from app.generation.prompt import catalog_block

    result = EvalCaseResult(
        case_id=fixture.id,
        expected_action=fixture.expected_action,
        actual_action=turn.action,
        expected_metrics=fixture.applicable_metrics,
        actual_answer=turn.answer,
        retrieved_chunk_ids=[c.chunk_id for c in turn.retrieved],
        generation_calls=turn.generation_calls,
        errors=list(turn.errors),
        observation=turn,
    )
    evidence = {sku: catalog_block(product) for sku, product in turn.products.items()}
    for chunk in turn.retrieved:
        evidence[chunk.sku] = evidence.get(chunk.sku, "") + "\n" + chunk.content
    evidence_by_page: dict[tuple[str, str, int], str] = {}
    for chunk in turn.retrieved:
        if chunk.chunk_id in turn.citation_chunk_ids:
            key = (chunk.sku, chunk.manual_title, chunk.page_number)
            body = (
                chunk.content.split("\n", 1)[-1]
                if chunk.content.startswith("[PRODUTO:")
                else chunk.content
            )
            evidence_by_page[key] = evidence_by_page.get(key, "") + "\n" + body
    result.technical_violations = technical_violations(
        turn.emitted_content or turn.answer,
        evidence,
        turn.citations,
        primary_sku=fixture.input_filters.sku,
        products=turn.products,
        evidence_by_page=evidence_by_page,
    )
    result.business_violations = business_violations(turn, fixture, corpus.relations)
    if fixture.expected_action != "ANSWER" and turn.generation_calls:
        result.errors.append("Negative case opened generation instead of G-IN/G-RET blocking")
    if "retrieval" in fixture.applicable_metrics:
        result.precision_at_5, result.precision_returned, result.recall = (
            calculate_retrieval_precision(
                result.retrieved_chunk_ids,
                corpus.relevant_ids(fixture),
            )
        )
    if fixture.expected_action == "ANSWER" and turn.action == "ANSWER":
        manual_required = any(e.source.startswith("manual:") for e in fixture.relevant_evidence)
        if manual_required and not CITATION.search(turn.answer):
            result.technical_violations.append("Manual-based answer has no inline citation")
    return result


async def evaluate_case(
    fixture: GoldenSetFixture, pipeline: Pipeline, judge: CognitiveJudge, corpus: Corpus
) -> EvalCaseResult:
    try:
        turn = await pipeline.run(fixture.pipeline_input())
        result = _deterministic_checks(fixture, turn, corpus)
    except Exception as error:
        return EvalCaseResult(
            case_id=fixture.id,
            expected_action=fixture.expected_action,
            actual_action="ERROR",
            expected_metrics=fixture.applicable_metrics,
            errors=[f"Pipeline/evidence failed: {type(error).__name__}"],
        )
    if "faithfulness" not in fixture.applicable_metrics:
        return result
    if turn.action != "ANSWER" or not turn.answer.strip():
        result.faithfulness, result.answer_relevance = 0.0, 0.0
        result.errors.append("Expected ANSWER did not publish a nonempty answer")
        return result
    try:
        faithfulness, relevance = await judge.score(
            fixture.query, turn.answer, turn.evidence_contexts
        )
        result.faithfulness, result.answer_relevance = (
            checked_score(faithfulness),
            checked_score(relevance),
        )
    except Exception as error:
        result.errors.append(f"Judge failed: {type(error).__name__}")
    return result


async def run_ragas_evaluation(
    *,
    fixtures: list[GoldenSetFixture],
    pipeline: Pipeline,
    judge: CognitiveJudge,
    corpus: Corpus,
    identity: RunIdentity,
    checkpoint_path: Path | None = None,
) -> EvaluationReport:
    cached = load_checkpoint(checkpoint_path, identity)
    results: list[EvalCaseResult] = []
    for fixture in fixtures:
        result = cached.get(fixture.id)
        if result is None or result.errors:
            result = await evaluate_case(fixture, pipeline, judge, corpus)
        if (
            result.case_id != fixture.id
            or result.expected_metrics != fixture.applicable_metrics
            or result.expected_action != fixture.expected_action
        ):
            raise ValueError("Checkpoint expectation differs from the current fixture")
        results.append(result)
        save_checkpoint(checkpoint_path, identity, results)
    return aggregate_macro_metrics(results, identity)


def format_markdown_report(report: EvaluationReport) -> str:
    lines = [
        f"# Avaliação B05: {report.status}",
        "",
        f"- Modo: **{report.identity.mode}**",
        f"- Commit: `{report.identity.revision}`",
        f"- Fingerprint: `{report.identity.fingerprint}`",
        f"- Casos: {report.evaluated_cases}/{report.total_cases}",
        "- Corpus: seed sintético de demonstração; auditoria do PO/fabricante não atestada.",
        f"- Sentenças bloqueadas internamente: {sum(r.observation.blocked_sentences for r in report.case_results if r.observation)}",
        "",
        "| Gate | Valor | Amostras | Resultado | Motivo |",
        "|---|---:|---:|---|---|",
    ]
    for gate in report.gates:
        value = f"{gate.value:.4f}" if gate.value is not None else "N/A"
        lines.append(
            f"| {gate.metric_name} | {value} | {gate.denominator} | "
            f"{'PASS' if gate.passed else 'FAIL'} | {gate.reason} |"
        )
    lines.extend(["", "## Falhas por caso"])
    for result in report.case_results:
        failures = [*result.errors, *result.technical_violations, *result.business_violations]
        if not result.action_matched:
            failures.append(
                f"Ação esperada {result.expected_action}, observada {result.actual_action}"
            )
        if failures:
            lines.append(f"- {result.case_id}: " + "; ".join(failures))
    return "\n".join(lines) + "\n"


async def _live(
    settings: Settings,
    judge_settings: JudgeSettings,
    corpus: Corpus,
    fixtures: list[GoldenSetFixture],
    args: argparse.Namespace,
) -> EvaluationReport:
    if not settings.llm_api_key:
        raise ValueError("LLM_API_KEY is required for a live production-pipeline evaluation")
    if settings.llm_model == judge_settings.judge_model:
        raise ValueError("The judge must be configured independently from the generator")
    await corpus.verify_database(settings.database_url)
    identity = make_identity(ROOT, args.fixture, corpus, settings, judge_settings, mode="live")
    catalog = PostgresCatalog(settings.database_url)
    async with make_client(settings) as client:
        embedder = OpenAIEmbedder(
            client,
            model=settings.embedding_model,
            dimensions=settings.embedding_dimensions,
            batch_size=settings.embedding_batch_size,
        )
        model = OpenAIChatModel(
            client,
            model=settings.llm_model,
            temperature=settings.llm_temperature,
            max_tokens=settings.llm_max_tokens,
            first_token_timeout=settings.llm_first_token_timeout_seconds,
            first_token_attempts=settings.llm_first_token_attempts,
        )
        # One pacer for generator and judge: they usually share the provider quota.
        retry = ProviderRetry(RetrySettings())
        pipeline = ProductionPipeline(
            catalog, catalog, embedder, model, settings, corpus, catalog, retry
        )
        report = await run_ragas_evaluation(
            fixtures=fixtures[: args.limit] if args.limit else fixtures,
            pipeline=pipeline,
            judge=RagasJudge.from_settings(judge_settings, retry),
            corpus=corpus,
            identity=identity,
            checkpoint_path=args.checkpoint,
        )
        # Concurrent catalog/vector changes invalidate the run rather than changing its denominator.
        original_index = (dict(corpus.database_ids), corpus.embeddings_sha256)
        await corpus.verify_database(settings.database_url)
        if original_index != (corpus.database_ids, corpus.embeddings_sha256):
            raise ValueError("Evaluation corpus changed during the run")
        return report


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Auditoria de fontes ou avaliação live B05; nenhum modo mock homologa"
    )
    parser.add_argument("--mode", choices=["validate", "live"], default="validate")
    parser.add_argument("--fixture", type=Path, default=DEFAULT_FIXTURE_PATH)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--checkpoint", type=Path)
    parser.add_argument("--limit", type=int, choices=range(1, 51))
    parser.add_argument("--gate-check", action="store_true")
    args = parser.parse_args()
    try:
        settings = Settings()
        corpus = Corpus.from_seed(ROOT, settings)
        fixtures = load_fixtures(args.fixture, corpus)
        if args.mode == "live":
            # Configuration validation happens before any model invocation.
            judge_settings = JudgeSettings.model_validate({})
            report = asyncio.run(_live(settings, judge_settings, corpus, fixtures, args))
        else:
            identity = make_identity(ROOT, args.fixture, corpus, settings, None, mode="validate")
            report = aggregate_macro_metrics([], identity)
            report.errors.append(
                "Sources verified; cognitive evaluation PENDING until a full live run"
            )
        if args.output:
            write_json(args.output, report.model_dump(mode="json"))
        print(format_markdown_report(report))
        return 1 if args.gate_check and not report.all_gates_passed else 0
    except Exception as error:
        # SDK/validation exceptions can contain credentials or user data; show only the error type.
        print(
            f"Evaluation unavailable ({type(error).__name__}); check corpus, database and EVAL_/LLM_ configuration."
        )
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
