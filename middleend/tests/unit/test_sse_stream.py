"""M02 contracts: a completed backend turn is required for public success."""

from __future__ import annotations

import asyncio
import importlib
import json

import pytest


def api():
    return importlib.import_module("app.sse")


class Request:
    disconnected = False

    async def is_disconnected(self) -> bool:
        return self.disconnected


class Backend:
    def __init__(self, items=(), failure=None):
        self.items = iter(items)
        self.failure = failure
        self.closed = False
        self.reads = 0

    def __aiter__(self):
        return self

    async def __anext__(self):
        self.reads += 1
        try:
            return next(self.items)
        except StopIteration:
            if self.failure:
                raise self.failure
            raise StopAsyncIteration from None

    async def aclose(self):
        self.closed = True


def token(text="Olá"):
    return {"event": "token", "data": {"delta": text}}


def end(tokens=7):
    return {"event": "end", "data": {"tokens_used": tokens, "intent": "TECHNICAL_QA"}}


def unpack(frame):
    event, payload, _ = frame.split("\n", 2)
    return event.removeprefix("event: "), json.loads(payload.removeprefix("data: "))


class Harness:
    def __init__(self, backend, request=None):
        self.backend = backend
        self.request = request or Request()
        self.released = 0
        self.completed = []
        self.fallback_calls = 0
        self.completion_failure = None
        self.fallback_failure = None

    async def release(self):
        self.released += 1

    async def fallback(self):
        self.fallback_calls += 1
        if self.fallback_failure:
            raise self.fallback_failure
        return []

    async def complete(self, turn):
        if self.completion_failure:
            raise self.completion_failure
        self.completed.append(turn)

    def stream(self):
        return api().sse_chat_generator(
            self.request,
            "session",
            "message",
            self.backend,
            False,
            self.release,
            self.fallback,
            self.complete,
            started_at=10.0,
            clock=lambda: 10.125,
        )

    async def collect(self):
        return [unpack(frame) async for frame in self.stream()]


def run(coroutine):
    return asyncio.run(coroutine)


def test_success_has_one_metadata_internal_end_hidden_and_persists_before_done():
    harness = Harness(Backend([token(), {"event": "citations", "data": {"citations": []}}, end()]))

    async def consume():
        events = []
        async for frame in harness.stream():
            event = unpack(frame)
            if event[0] == "done":
                assert len(harness.completed) == 1
                assert harness.backend.closed and harness.released == 1
            events.append(event)
        return events

    events = run(consume())
    assert [name for name, _ in events] == ["metadata", "token", "citations", "done"]
    assert events[0][1] == {
        "session_id": "session",
        "message_id": "message",
        "cache_hit": False,
        "ttft_ms": 125,
    }
    assert events[-1][1] == {"finish_reason": "stop", "total_latency_ms": 125, "tokens_used": 7}
    assert harness.completed[0].content == "Olá"
    assert harness.completed[0].intent == "TECHNICAL_QA"


@pytest.mark.parametrize("items", [[], [token()], [end()], [token(), end(-1)]])
def test_missing_or_invalid_internal_end_is_never_success(items):
    harness = Harness(Backend(items))
    events = run(harness.collect())
    assert events[-1][1]["finish_reason"] == "error"
    assert any(name == "error" for name, _ in events)
    assert not harness.completed
    assert harness.backend.closed and harness.released == 1


@pytest.mark.parametrize("items", [[], [token()]])
def test_timeout_before_or_after_tokens_emits_error_without_retry(items):
    harness = Harness(Backend(items, TimeoutError("timeout")))
    events = run(harness.collect())
    assert [name for name, _ in events].count("metadata") == 1
    assert next(payload for name, payload in events if name == "error")["code"] == "LLM_UNAVAILABLE"
    assert events[-1][1]["finish_reason"] == "error"
    assert not harness.completed
    assert harness.backend.reads == len(items) + 1


@pytest.mark.parametrize(
    "items",
    [
        [{"event": "metadata", "data": {}}],
        [{"event": "citations", "data": {"citations": []}}],
        [{"event": "token", "data": {"delta": 4}}],
        [token(), {"event": "citations", "data": {"citations": []}}, token()],
        [
            token(),
            {"event": "recommendations", "data": {"products": []}},
            {"event": "citations", "data": {"citations": []}},
        ],
        [token(), {"event": "correction", "data": {"violation_code": "OTHER", "content": "safe"}}],
    ],
)
def test_malformed_events_or_order_are_internal_errors(items):
    harness = Harness(Backend(items + [end()]))
    events = run(harness.collect())
    assert next(payload for name, payload in events if name == "error")["code"] == "INTERNAL_ERROR"
    assert events[-1][1]["finish_reason"] == "error"
    assert not harness.completed


def test_guardrail_fallback_is_completed_with_safe_message():
    fallback = {
        "code": "LOW_SIMILARITY_FALLBACK",
        "recoverable": True,
        "fallback_message": "Não encontrei essa especificação.",
    }
    harness = Harness(
        Backend(
            [
                {"event": "error", "data": fallback},
                {"event": "recommendations", "data": {"products": []}},
                end(0),
            ]
        )
    )
    events = run(harness.collect())
    assert [name for name, _ in events] == ["metadata", "error", "recommendations", "done"]
    assert events[-1][1]["finish_reason"] == "fallback"
    assert harness.completed[0].content == fallback["fallback_message"]
    assert harness.completed[0].finish_reason == "fallback"


def test_completed_fallback_keeps_error_code_for_replay():
    def turn_for(code):
        fallback = {"code": code, "recoverable": False, "fallback_message": "Mensagem segura."}
        harness = Harness(Backend([{"event": "error", "data": fallback}, end(0)]))
        run(harness.collect())
        return harness.completed[0]

    blocked = turn_for("GUARDRAIL_BLOCKED")
    low_similarity = turn_for("LOW_SIMILARITY_FALLBACK")
    assert (blocked.error_code, blocked.recoverable) == ("GUARDRAIL_BLOCKED", False)
    assert low_similarity.error_code == "LOW_SIMILARITY_FALLBACK"


def test_successful_turn_has_no_error_code():
    harness = Harness(Backend([token(), end()]))
    run(harness.collect())
    assert harness.completed[0].error_code is None
    assert harness.completed[0].recoverable is None


def test_model_error_after_partial_tokens_discards_partial_and_is_not_persisted():
    failure = {
        "code": "LLM_UNAVAILABLE",
        "recoverable": True,
        "fallback_message": "Tente novamente.",
    }
    harness = Harness(Backend([token(), {"event": "error", "data": failure}, end()]))
    events = run(harness.collect())
    assert [name for name, _ in events] == ["metadata", "token", "error", "done"]
    assert events[-1][1]["finish_reason"] == "error"
    assert not harness.completed


def test_disconnect_before_first_token_closes_and_releases_without_events():
    request = Request()
    request.disconnected = True
    harness = Harness(Backend([token(), end()]), request)
    assert run(harness.collect()) == []
    assert harness.backend.closed and harness.released == 1
    assert not harness.completed


def test_late_disconnect_after_persist_suppresses_done():
    harness = Harness(Backend([token(), end()]))
    original = harness.complete

    async def complete(turn):
        await original(turn)
        harness.request.disconnected = True

    harness.complete = complete
    events = run(harness.collect())
    assert "done" not in [name for name, _ in events]
    assert harness.backend.closed and harness.released == 1


def test_explicit_generator_close_always_cleans_resources():
    harness = Harness(Backend([token(), end()]))

    async def consume():
        stream = harness.stream()
        await anext(stream)
        await stream.aclose()

    run(consume())
    assert harness.backend.closed and harness.released == 1
    assert not harness.completed


def test_cancellation_is_not_swallowed_and_always_cleans_resources():
    class BlockingBackend(Backend):
        async def __anext__(self):
            ready.set()
            await asyncio.Event().wait()

    async def consume():
        api()
        nonlocal ready
        ready = asyncio.Event()
        harness = Harness(BlockingBackend())
        task = asyncio.create_task(harness.collect())
        await ready.wait()
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert harness.backend.closed and harness.released == 1
        assert not harness.completed

    ready = None
    run(consume())


def test_completion_failure_emits_error_and_never_stop():
    harness = Harness(Backend([token(), end()]))
    harness.completion_failure = RuntimeError("database failed")
    events = run(harness.collect())
    assert events[-1][1]["finish_reason"] == "error"
    assert not harness.completed


def test_fallback_lookup_failure_keeps_terminal_error_and_cleanup():
    harness = Harness(Backend([], ConnectionError("offline")))
    harness.fallback_failure = RuntimeError("database failed")
    events = run(harness.collect())
    assert [name for name, _ in events] == ["metadata", "error", "done"]
    assert events[-1][1]["finish_reason"] == "error"
    assert harness.backend.closed and harness.released == 1


def test_sse_encoding_escapes_newlines_and_preserves_portuguese():
    frame = api().format_sse("token", {"delta": "Olá\nmanual"})
    assert frame.endswith("\n\n") and "Olá" in frame
    assert unpack(frame) == ("token", {"delta": "Olá\nmanual"})


def card(**overrides):
    payload = {
        "sku": "AF-400-220V",
        "name": "Airfryer 4L",
        "price": 499.90,
        "stock_quantity": 2,
        "voltage": "220V",
        "image_url": "/airfryer.webp",
        "marketplace": "AMAZON",
        "checkout_url": "https://example.com/product",
        "recommendation_type": "PRIMARY",
        "badge_label": "Produto consultado",
        "justification": "Catálogo verificado.",
    }
    payload.update(overrides)
    return payload


def test_real_card_can_omit_nullable_optional_fields():
    product = card()
    harness = Harness(
        Backend([token(), {"event": "recommendations", "data": {"products": [product]}}, end()])
    )
    events = run(harness.collect())
    assert events[-1][1]["finish_reason"] == "stop"
    assert harness.completed[0].products == (product,)
    assert next(payload for name, payload in events if name == "recommendations")["products"] == [
        product
    ]


@pytest.mark.parametrize("overrides", [{"voltage": "110V"}, {"price": 1.001}])
def test_public_card_enum_and_cent_precision_checked_before_publication(overrides):
    product = card(capacity_liters=None, power_watts=None, **overrides)
    harness = Harness(
        Backend([token(), {"event": "recommendations", "data": {"products": [product]}}, end()])
    )
    events = run(harness.collect())
    assert events[-1][1]["finish_reason"] == "error"
    assert not harness.completed
    assert not any(name == "recommendations" and payload["products"] for name, payload in events)


def test_correction_replaces_persisted_text_and_real_citations_are_preserved():
    citation = {
        "chunk_id": "c1a2b3d4-0001-4000-8000-000000000014",
        "sku": "AF-400-220V",
        "manual_title": "Manual",
        "page_number": 14,
        "similarity_score": 0.89,
        "excerpt": "Texto aprovado.",
    }
    harness = Harness(
        Backend(
            [
                token("Parcial"),
                {
                    "event": "correction",
                    "data": {"violation_code": "STREAM_INTERRUPTED", "content": "Texto seguro."},
                },
                {"event": "citations", "data": {"citations": [citation]}},
                end(),
            ]
        )
    )
    events = run(harness.collect())
    assert events[-1][1]["finish_reason"] == "stop"
    assert harness.completed[0].content == "Texto seguro."
    assert harness.completed[0].citations == (citation,)


def test_cleanup_failure_after_persist_still_releases_and_emits_done():
    # Turn is already persisted; withholding done would make the client re-send it.
    class FailingClose(Backend):
        async def aclose(self):
            self.closed = True
            raise RuntimeError("close failed")

    harness = Harness(FailingClose([token(), end()]))
    events = run(harness.collect())
    assert [name for name, _ in events] == ["metadata", "token", "done"]
    assert events[-1][1]["finish_reason"] == "stop"
    assert harness.backend.closed and harness.released == 1 and harness.completed


def test_release_failure_is_logged_and_done_still_emitted():
    harness = Harness(Backend([token(), end()]))

    async def release():
        harness.released += 1
        raise RuntimeError("redis down")

    harness.release = release
    events = run(harness.collect())
    assert events[-1][0] == "done" and harness.released == 1


def test_close_before_first_read_still_releases_resources():
    harness = Harness(Backend([token(), end()]))

    async def consume():
        await harness.stream().aclose()

    run(consume())
    assert harness.backend.closed and harness.released == 1
    assert harness.backend.reads == 0


def test_fallback_then_eof_emits_a_single_error():
    fallback = {
        "code": "LOW_SIMILARITY_FALLBACK",
        "recoverable": True,
        "fallback_message": "Não encontrei essa especificação.",
    }
    harness = Harness(Backend([{"event": "error", "data": fallback}]))
    events = run(harness.collect())
    assert [name for name, _ in events] == ["metadata", "error", "recommendations", "done"]
    assert events[1][1]["code"] == "LOW_SIMILARITY_FALLBACK"
    assert events[-1][1]["finish_reason"] == "error"


def test_fallback_completion_failure_does_not_repeat_error_or_cards():
    fallback = {
        "code": "LOW_SIMILARITY_FALLBACK",
        "recoverable": True,
        "fallback_message": "Não encontrei essa especificação.",
    }
    harness = Harness(
        Backend(
            [
                {"event": "error", "data": fallback},
                {"event": "recommendations", "data": {"products": []}},
                end(0),
            ]
        )
    )
    harness.completion_failure = RuntimeError("db down")
    events = run(harness.collect())
    assert [name for name, _ in events] == ["metadata", "error", "recommendations", "done"]
    assert events[-1][1]["finish_reason"] == "error"
    assert harness.fallback_calls == 0


def test_disconnect_between_metadata_and_token_suppresses_content_and_done():
    harness = Harness(Backend([token(), end()]))

    async def consume():
        stream = harness.stream()
        assert unpack(await anext(stream))[0] == "metadata"
        harness.request.disconnected = True
        assert [frame async for frame in stream] == []

    run(consume())
    assert harness.backend.closed and harness.released == 1
    assert not harness.completed


def test_cancellation_during_release_waits_for_resource_cleanup():
    async def consume():
        release_started = asyncio.Event()
        release_allowed = asyncio.Event()
        harness = Harness(Backend([token(), end()]))

        async def release():
            release_started.set()
            await release_allowed.wait()
            harness.released += 1

        harness.release = release
        task = asyncio.create_task(harness.collect())
        await release_started.wait()
        task.cancel()
        release_allowed.set()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert harness.backend.closed and harness.released == 1

    run(consume())
