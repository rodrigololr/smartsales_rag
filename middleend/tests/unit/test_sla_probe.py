"""EAP 5.3: the SLA probe measures TTFT/latency p95 through the real gateway app."""

import asyncio
import json
from collections.abc import AsyncIterator, Mapping

import httpx
import pytest
from app.config import Settings
from app.main import create_app
from app.telemetry.sla_probe import (
    Sample,
    main,
    percentile,
    probe_once,
    run_probe,
    sse_events,
    summarize,
)
from test_chat_routes import CITATIONS, END, FALLBACK, TOKEN, FakeBackend

LIMITS = {"ttft_p95_limit_ms": 2000.0, "total_p95_limit_ms": 8000.0}


def sample(ttft: float, total: float, *, cache_hit: bool = False, reason: str = "stop") -> Sample:
    return Sample(ttft, total, int(ttft), cache_hit, reason)


@pytest.mark.parametrize(
    ("rank", "expected"),
    [(50.0, 50.0), (95.0, 95.0), (100.0, 100.0), (1.0, 1.0)],
)
def test_percentile_uses_the_nearest_rank(rank: float, expected: float) -> None:
    assert percentile([float(value) for value in range(100, 0, -1)], rank) == expected


def test_percentile_of_small_and_empty_samples() -> None:
    assert percentile([900.0, 100.0], 95.0) == 900.0
    assert percentile([], 95.0) is None


def test_sse_events_parses_frames_and_ignores_a_trailing_partial_frame() -> None:
    async def lines() -> AsyncIterator[str]:
        for line in ('event: token', 'data: {"delta": "Olá"}', "", "event: done", "data: {}", "", "event: x"):
            yield line

    async def collect() -> list[tuple[str, dict[str, object]]]:
        return [frame async for frame in sse_events(lines())]

    assert asyncio.run(collect()) == [("token", {"delta": "Olá"}), ("done", {})]


def test_report_gates_on_generated_answers_and_reports_the_hit_ratio() -> None:
    samples = [sample(900, 3000), sample(1500, 5000), sample(40, 60, cache_hit=True)]
    report = summarize(samples, **LIMITS)
    assert report.passed and report.failures == 0
    assert (report.ttft_p95_ms, report.total_p95_ms) == (1500, 5000)  # the cache hit is left out
    assert report.cache_hits == 1 and report.cache_hit_ratio == 0.3333


def test_report_fails_above_the_ttft_or_latency_ceiling() -> None:
    assert not summarize([sample(2001, 3000)], **LIMITS).passed
    assert not summarize([sample(900, 8001)], **LIMITS).passed
    assert summarize([sample(2000, 8000)], **LIMITS).passed  # ceilings are inclusive


def test_report_fails_on_incomplete_requests_or_without_generated_samples() -> None:
    broken = Sample(None, None, None, False, None, failure="ConnectError: down")
    report = summarize([sample(900, 3000), broken], **LIMITS)
    assert not report.passed and report.failures == 1 and report.completed == 1
    assert not summarize([sample(40, 60, cache_hit=True)], **LIMITS).passed
    assert summarize([], **LIMITS).cache_hit_ratio == 0.0


def test_fallback_turns_are_counted() -> None:
    report = summarize([sample(100, 200, reason="fallback"), sample(900, 3000)], **LIMITS)
    assert report.fallbacks == 1


def gateway_client(events: list[Mapping[str, object]]) -> tuple[httpx.AsyncClient, FakeBackend]:
    backend = FakeBackend(events)
    app = create_app(Settings(backend_internal_url="http://127.0.0.1:9"), backend)
    transport = httpx.ASGITransport(app=app)
    return httpx.AsyncClient(transport=transport, base_url="http://gateway"), backend


def probe(events: list[Mapping[str, object]], requests: int = 1) -> tuple[list[Sample], FakeBackend]:
    async def scenario() -> tuple[list[Sample], FakeBackend]:
        client, backend = gateway_client(events)
        async with client, client._transport.app.router.lifespan_context(  # type: ignore[attr-defined]
            client._transport.app  # type: ignore[attr-defined]
        ):
            samples = await run_probe(
                client, "AF-400-220V", ["Qual a voltagem?", "E a potência?"],
                requests=requests, concurrency=3,
            )
        return samples, backend

    return asyncio.run(scenario())


def test_probe_measures_an_answered_turn_through_the_gateway() -> None:
    [measured], backend = probe([TOKEN, CITATIONS, END])
    assert measured.completed and measured.finish_reason == "stop" and not measured.cache_hit
    assert measured.ttft_ms is not None and measured.total_ms is not None
    assert 0 <= measured.ttft_ms <= measured.total_ms
    assert backend.calls[0][:2] == ("AF-400-220V", "Qual a voltagem?")


def test_probe_counts_the_error_frame_as_first_content_on_fallbacks() -> None:
    [measured], _ = probe([FALLBACK, END])
    assert measured.finish_reason == "fallback" and measured.ttft_ms is not None


def test_probe_runs_every_request_and_cycles_the_questions() -> None:
    samples, backend = probe([TOKEN, END], requests=5)
    assert len(samples) == 5 and all(item.completed for item in samples)
    assert sorted(call[1] for call in backend.calls).count("Qual a voltagem?") == 3


def test_unreachable_gateway_is_a_failed_sample_not_an_exception() -> None:
    def refuse(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("down")

    async def scenario() -> Sample:
        transport = httpx.MockTransport(refuse)
        async with httpx.AsyncClient(transport=transport, base_url="http://gateway") as client:
            return await probe_once(client, "AF-400-220V", "Oi")

    measured = asyncio.run(scenario())
    assert not measured.completed and "ConnectError" in str(measured.failure)


def test_stream_that_ends_without_done_is_a_failure() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/sessions"):
            return httpx.Response(201, json={"session_id": "s"})
        return httpx.Response(200, text='event: token\ndata: {"delta": "x"}\n\n')

    async def scenario() -> Sample:
        transport = httpx.MockTransport(handler)
        async with httpx.AsyncClient(transport=transport, base_url="http://gateway") as client:
            return await probe_once(client, "AF-400-220V", "Oi")

    measured = asyncio.run(scenario())
    assert measured.failure == "stream ended without done" and measured.ttft_ms is not None


def test_cli_prints_the_report_and_fails_when_the_gateway_is_down(
    capsys: pytest.CaptureFixture[str],
) -> None:
    code = main(["--base-url", "http://127.0.0.1:9", "--requests", "2", "--timeout-seconds", "2"])
    report = json.loads(capsys.readouterr().out)
    assert code == 1 and report["failures"] == 2 and report["passed"] is False
