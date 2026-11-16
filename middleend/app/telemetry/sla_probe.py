"""SLA probe for homologation (EAP 5.3): TTFT and total latency p95 through the gateway.

    python -m app.telemetry.sla_probe --base-url http://localhost:8000 --sku AF-400-220V \
        --requests 40 --concurrency 5

Each sample opens its own session and asks one question on POST /api/v1/chat/stream.
Every question carries a per-run, per-sample suffix, so each sample is a cache miss.
TTFT is measured at the client, from the request to the first `token` or `error` frame,
which is what the browser sees. The TTFT and latency gates look only at generated
answers (`finish_reason: stop`, no cache hit): a warm cache or a fast fallback cannot
hide a slow generation. Fallback TTFT and the hit ratio of this synthetic load are
reported apart; that ratio is not the production cache KPI.
Exit code 1 when a ceiling is exceeded, fewer than `--min-generated` answers were
generated, a turn ends in `error` or a request does not reach `done`.
"""

import argparse
import asyncio
import json
import math
import time
import uuid
from collections.abc import AsyncIterator, Sequence
from dataclasses import asdict, dataclass

import httpx

DEFAULT_QUESTIONS = (
    "Posso usar papel alumínio no cesto?",
    "Qual a voltagem deste produto?",
    "Como faço a limpeza depois do uso?",
    "Qual a capacidade do cesto?",
)
TTFT_P95_LIMIT_MS = 2000.0  # CLAUDE.md rule 6: homologation ceiling
TOTAL_P95_LIMIT_MS = 8000.0
MIN_GENERATED_SAMPLES = 20  # below this the nearest-rank p95 is just the maximum
DEFAULT_REQUESTS = 30  # headroom over the minimum for turns that end in fallback
P95 = 95.0
P50 = 50.0
GENERATED = "stop"
FALLBACK = "fallback"
CONTENT_EVENTS = {"token", "error"}
MILLISECONDS = 1000.0
RUN_ID_LENGTH = 8


@dataclass(frozen=True)
class Sample:
    ttft_ms: float | None
    total_ms: float | None
    server_ttft_ms: int | None
    cache_hit: bool
    finish_reason: str | None
    failure: str | None = None

    @property
    def completed(self) -> bool:
        """Reached `done` with an answer or a safe fallback; `error` turns are failures."""
        return self.failure is None and self.finish_reason in (GENERATED, FALLBACK)


@dataclass(frozen=True)
class Report:
    requests: int
    completed: int
    failures: int
    cache_hits: int
    synthetic_load_cache_hit_ratio: float
    fallbacks: int
    fallback_ttft_p95_ms: float | None
    generated: int
    min_generated: int
    ttft_p50_ms: float | None
    ttft_p95_ms: float | None
    total_p50_ms: float | None
    total_p95_ms: float | None
    ttft_p95_limit_ms: float
    total_p95_limit_ms: float
    failed_gates: list[str]
    passed: bool


def percentile(values: Sequence[float], rank: float) -> float | None:
    """Nearest-rank percentile; None for an empty sample."""
    if not values:
        return None
    ordered = sorted(values)
    position = max(1, math.ceil(rank / 100.0 * len(ordered)))
    return ordered[position - 1]


async def sse_events(lines: AsyncIterator[str]) -> AsyncIterator[tuple[str, dict[str, object]]]:
    """Parse `event:`/`data:` frames; a blank line ends a frame."""
    event, data = "", ""
    async for line in lines:
        if line.startswith("event:"):
            event = line.removeprefix("event:").strip()
        elif line.startswith("data:"):
            data = line.removeprefix("data:").strip()
        elif not line.strip() and event:
            yield event, json.loads(data) if data else {}
            event, data = "", ""


async def probe_once(client: httpx.AsyncClient, sku: str, question: str) -> Sample:
    """One session and one question; transport and HTTP failures become a failed sample."""
    try:
        session = await client.post("/api/v1/sessions", json={"current_product_sku": sku})
        session.raise_for_status()
        body = {
            "session_id": session.json()["session_id"],
            "client_request_id": str(uuid.uuid4()),
            "message": question,
            "context_filters": {"current_product_sku": sku},
        }
        return await _stream_sample(client, body)
    except httpx.HTTPError as error:
        return Sample(None, None, None, False, None, failure=f"{type(error).__name__}: {error}")


async def _stream_sample(client: httpx.AsyncClient, body: dict[str, object]) -> Sample:
    started = time.perf_counter()
    ttft_ms: float | None = None
    server_ttft_ms: int | None = None
    cache_hit = False
    async with client.stream("POST", "/api/v1/chat/stream", json=body) as response:
        response.raise_for_status()
        async for event, payload in sse_events(response.aiter_lines()):
            elapsed_ms = (time.perf_counter() - started) * MILLISECONDS
            if event == "metadata":
                cache_hit = bool(payload.get("cache_hit"))
                server_ttft_ms = int(str(payload.get("ttft_ms", 0)))
            elif event in CONTENT_EVENTS and ttft_ms is None:
                ttft_ms = elapsed_ms
            elif event == "done":
                reason = str(payload.get("finish_reason"))
                return Sample(ttft_ms, elapsed_ms, server_ttft_ms, cache_hit, reason)
    return Sample(ttft_ms, None, server_ttft_ms, cache_hit, None, failure="stream ended without done")


def sample_question(question: str, run_id: str, index: int) -> str:
    """The question plus a suffix unique to this run and sample: a new cache key."""
    return f"{question} (amostra {run_id}-{index})"


def _ttfts(samples: Sequence[Sample]) -> list[float]:
    return [sample.ttft_ms for sample in samples if sample.ttft_ms is not None]


def _failed_gates(
    failures: int, generated: int, min_generated: int, measured: Sequence[tuple[str, float | None, float]]
) -> list[str]:
    failed = [f"failed requests: {failures}"] if failures else []
    if generated < min_generated:
        failed.append(f"generated samples: {generated} < minimum {min_generated}")
    failed.extend(
        f"{name}: {value:.0f} ms > {limit:.0f} ms"
        for name, value, limit in measured
        if value is not None and value > limit
    )
    return failed


def summarize(
    samples: Sequence[Sample],
    *,
    ttft_p95_limit_ms: float,
    total_p95_limit_ms: float,
    min_generated: int,
) -> Report:
    completed = [sample for sample in samples if sample.completed]
    generated = [s for s in completed if s.finish_reason == GENERATED and not s.cache_hit]
    fallbacks = [sample for sample in completed if sample.finish_reason == FALLBACK]
    ttfts = _ttfts(generated)
    totals = [sample.total_ms for sample in generated if sample.total_ms is not None]
    ttft_p95, total_p95 = percentile(ttfts, P95), percentile(totals, P95)
    failures = len(samples) - len(completed)
    hits = sum(sample.cache_hit for sample in completed)
    failed_gates = _failed_gates(
        failures,
        len(generated),
        min_generated,
        [("ttft p95", ttft_p95, ttft_p95_limit_ms), ("total p95", total_p95, total_p95_limit_ms)],
    )
    return Report(
        requests=len(samples),
        completed=len(completed),
        failures=failures,
        cache_hits=hits,
        synthetic_load_cache_hit_ratio=round(hits / len(completed), 4) if completed else 0.0,
        fallbacks=len(fallbacks),
        fallback_ttft_p95_ms=percentile(_ttfts(fallbacks), P95),
        generated=len(generated),
        min_generated=min_generated,
        ttft_p50_ms=percentile(ttfts, P50),
        ttft_p95_ms=ttft_p95,
        total_p50_ms=percentile(totals, P50),
        total_p95_ms=total_p95,
        ttft_p95_limit_ms=ttft_p95_limit_ms,
        total_p95_limit_ms=total_p95_limit_ms,
        failed_gates=failed_gates,
        passed=not failed_gates,
    )


async def run_probe(
    client: httpx.AsyncClient,
    sku: str,
    questions: Sequence[str],
    *,
    run_id: str,
    requests: int,
    concurrency: int,
) -> list[Sample]:
    """`requests` distinct questions with at most `concurrency` SSE streams open at once."""
    gate = asyncio.Semaphore(concurrency)

    async def one(index: int) -> Sample:
        async with gate:
            question = sample_question(questions[index % len(questions)], run_id, index)
            return await probe_once(client, sku, question)

    return list(await asyncio.gather(*(one(index) for index in range(requests))))


def _arguments(argv: Sequence[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Aferição de TTFT e latência p95 (EAP 5.3)")
    parser.add_argument("--base-url", default="http://localhost:8000")
    parser.add_argument("--sku", default="AF-400-220V")
    parser.add_argument("--question", action="append", dest="questions")
    parser.add_argument("--requests", type=int, default=DEFAULT_REQUESTS)
    parser.add_argument("--concurrency", type=int, default=1)
    parser.add_argument("--timeout-seconds", type=float, default=30.0)
    parser.add_argument("--ttft-p95-ms", type=float, default=TTFT_P95_LIMIT_MS)
    parser.add_argument("--total-p95-ms", type=float, default=TOTAL_P95_LIMIT_MS)
    parser.add_argument("--min-generated", type=int, default=MIN_GENERATED_SAMPLES)
    return parser.parse_args(argv)


async def _measure(arguments: argparse.Namespace) -> Report:
    questions = arguments.questions or list(DEFAULT_QUESTIONS)
    async with httpx.AsyncClient(
        base_url=arguments.base_url, timeout=arguments.timeout_seconds
    ) as client:
        samples = await run_probe(
            client,
            arguments.sku,
            questions,
            run_id=uuid.uuid4().hex[:RUN_ID_LENGTH],
            requests=arguments.requests,
            concurrency=arguments.concurrency,
        )
    return summarize(
        samples,
        ttft_p95_limit_ms=arguments.ttft_p95_ms,
        total_p95_limit_ms=arguments.total_p95_ms,
        min_generated=arguments.min_generated,
    )


def main(argv: Sequence[str] | None = None) -> int:
    report = asyncio.run(_measure(_arguments(argv)))
    print(json.dumps(asdict(report), ensure_ascii=False, indent=2))
    return 0 if report.passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
