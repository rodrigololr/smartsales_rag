"""SLA probe for homologation (EAP 5.3): TTFT and total latency p95 through the gateway.

    python -m app.telemetry.sla_probe --base-url http://localhost:8000 --sku AF-400-220V \
        --requests 40 --concurrency 5

Each sample opens its own session and asks one question on POST /api/v1/chat/stream.
TTFT is measured at the client, from the request to the first `token` or `error` frame,
which is what the browser sees. The TTFT and latency gates look only at cache misses,
so a warm cache cannot hide a slow generation; the hit ratio is reported apart.
Exit code 1 when a gate fails or a request does not reach `done`.
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
P95 = 95.0
CONTENT_EVENTS = {"token", "error"}
MILLISECONDS = 1000.0


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
        return self.failure is None and self.finish_reason is not None


@dataclass(frozen=True)
class Report:
    requests: int
    completed: int
    failures: int
    cache_hits: int
    cache_hit_ratio: float
    fallbacks: int
    ttft_p50_ms: float | None
    ttft_p95_ms: float | None
    total_p50_ms: float | None
    total_p95_ms: float | None
    ttft_p95_limit_ms: float
    total_p95_limit_ms: float
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


def summarize(
    samples: Sequence[Sample], *, ttft_p95_limit_ms: float, total_p95_limit_ms: float
) -> Report:
    completed = [sample for sample in samples if sample.completed]
    generated = [sample for sample in completed if not sample.cache_hit]
    ttfts = [sample.ttft_ms for sample in generated if sample.ttft_ms is not None]
    totals = [sample.total_ms for sample in generated if sample.total_ms is not None]
    ttft_p95, total_p95 = percentile(ttfts, P95), percentile(totals, P95)
    failures = len(samples) - len(completed)
    hits = sum(sample.cache_hit for sample in completed)
    passed = (
        failures == 0
        and ttft_p95 is not None
        and total_p95 is not None
        and ttft_p95 <= ttft_p95_limit_ms
        and total_p95 <= total_p95_limit_ms
    )
    return Report(
        requests=len(samples),
        completed=len(completed),
        failures=failures,
        cache_hits=hits,
        cache_hit_ratio=round(hits / len(completed), 4) if completed else 0.0,
        fallbacks=sum(sample.finish_reason != "stop" for sample in completed),
        ttft_p50_ms=percentile(ttfts, 50.0),
        ttft_p95_ms=ttft_p95,
        total_p50_ms=percentile(totals, 50.0),
        total_p95_ms=total_p95,
        ttft_p95_limit_ms=ttft_p95_limit_ms,
        total_p95_limit_ms=total_p95_limit_ms,
        passed=passed,
    )


async def run_probe(
    client: httpx.AsyncClient,
    sku: str,
    questions: Sequence[str],
    *,
    requests: int,
    concurrency: int,
) -> list[Sample]:
    """`requests` samples with at most `concurrency` SSE streams open at once."""
    gate = asyncio.Semaphore(concurrency)

    async def one(index: int) -> Sample:
        async with gate:
            return await probe_once(client, sku, questions[index % len(questions)])

    return list(await asyncio.gather(*(one(index) for index in range(requests))))


def _arguments(argv: Sequence[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Aferição de TTFT e latência p95 (EAP 5.3)")
    parser.add_argument("--base-url", default="http://localhost:8000")
    parser.add_argument("--sku", default="AF-400-220V")
    parser.add_argument("--question", action="append", dest="questions")
    parser.add_argument("--requests", type=int, default=20)
    parser.add_argument("--concurrency", type=int, default=1)
    parser.add_argument("--timeout-seconds", type=float, default=30.0)
    parser.add_argument("--ttft-p95-ms", type=float, default=TTFT_P95_LIMIT_MS)
    parser.add_argument("--total-p95-ms", type=float, default=TOTAL_P95_LIMIT_MS)
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
            requests=arguments.requests,
            concurrency=arguments.concurrency,
        )
    return summarize(
        samples,
        ttft_p95_limit_ms=arguments.ttft_p95_ms,
        total_p95_limit_ms=arguments.total_p95_ms,
    )


def main(argv: Sequence[str] | None = None) -> int:
    report = asyncio.run(_measure(_arguments(argv)))
    print(json.dumps(asdict(report), ensure_ascii=False, indent=2))
    return 0 if report.passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
