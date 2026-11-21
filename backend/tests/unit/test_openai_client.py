"""OpenAI adapters: batching, streamed deltas and outage mapping (no network)."""

import asyncio
from collections.abc import AsyncIterator
from types import SimpleNamespace
from typing import Any, cast

import httpx
import openai
import pytest
from app.clients.openai_client import (
    LLMUnavailableError,
    OpenAIChatModel,
    OpenAIEmbedder,
    make_client,
)
from app.config import Settings


class FakeEmbeddings:
    def __init__(self) -> None:
        self.batches: list[list[str]] = []
        self.kwargs: dict[str, Any] = {}

    async def create(
        self, *, input: list[str], model: str, dimensions: int, **kwargs: Any
    ) -> SimpleNamespace:
        self.batches.append(input)
        self.kwargs = kwargs
        return SimpleNamespace(data=[SimpleNamespace(embedding=[float(len(text))]) for text in input])


class FakeCompletions:
    def __init__(self, deltas: list[str | None], failure: Exception | None = None) -> None:
        self.deltas = deltas
        self.failure = failure
        self.kwargs: dict[str, Any] = {}

    async def create(self, **kwargs: Any) -> AsyncIterator[SimpleNamespace]:
        self.kwargs = kwargs
        if self.failure:
            raise self.failure

        async def chunks() -> AsyncIterator[SimpleNamespace]:
            for delta in self.deltas:
                yield SimpleNamespace(choices=[SimpleNamespace(delta=SimpleNamespace(content=delta))])
            yield SimpleNamespace(choices=[])

        return chunks()


def fake_client(**parts: object) -> openai.AsyncOpenAI:
    return cast(openai.AsyncOpenAI, SimpleNamespace(**parts))


def test_embedder_batches_requests_and_keeps_order() -> None:
    embeddings = FakeEmbeddings()
    embedder = OpenAIEmbedder(
        fake_client(embeddings=embeddings), model="m", dimensions=1536, batch_size=2
    )
    vectors = asyncio.run(embedder.embed(["a", "bb", "ccc"]))
    assert vectors == [[1.0], [2.0], [3.0]]
    assert embeddings.batches == [["a", "bb"], ["ccc"]]


def test_chat_model_streams_non_empty_deltas_with_spec_parameters() -> None:
    completions = FakeCompletions(["Olá", None, " mundo"])
    model = OpenAIChatModel(
        fake_client(chat=SimpleNamespace(completions=completions)),
        model="gpt-4o-mini",
        temperature=0.2,
        max_tokens=600,
    )

    async def collect() -> list[str]:
        return [delta async for delta in model.stream([{"role": "user", "content": "Oi"}])]

    assert asyncio.run(collect()) == ["Olá", " mundo"]
    assert completions.kwargs["stream"] is True
    assert completions.kwargs["temperature"] == 0.2 and completions.kwargs["max_tokens"] == 600


class SlowThenFastCompletions:
    """First call stalls before its first token; the retry answers immediately."""

    def __init__(self, stalls: int) -> None:
        self.stalls = stalls
        self.calls = 0

    async def create(self, **kwargs: Any) -> AsyncIterator[SimpleNamespace]:
        self.calls += 1
        stall = self.calls <= self.stalls

        async def chunks() -> AsyncIterator[SimpleNamespace]:
            if stall:
                await asyncio.sleep(1)
            yield SimpleNamespace(choices=[SimpleNamespace(delta=SimpleNamespace(content="ok"))])

        return chunks()


def _slow_model(completions: SlowThenFastCompletions) -> OpenAIChatModel:
    return OpenAIChatModel(
        fake_client(chat=SimpleNamespace(completions=completions)),
        model="m",
        temperature=0.2,
        max_tokens=10,
        first_token_timeout=0.05,
        first_token_attempts=2,
    )


def test_first_token_timeout_retries_once() -> None:
    completions = SlowThenFastCompletions(stalls=1)

    async def collect() -> list[str]:
        return [delta async for delta in _slow_model(completions).stream([])]

    assert asyncio.run(collect()) == ["ok"]
    assert completions.calls == 2


def test_first_token_timeout_on_every_attempt_is_llm_unavailable() -> None:
    completions = SlowThenFastCompletions(stalls=2)

    async def collect() -> list[str]:
        return [delta async for delta in _slow_model(completions).stream([])]

    with pytest.raises(LLMUnavailableError):
        asyncio.run(collect())
    assert completions.calls == 2


def test_openai_outage_becomes_llm_unavailable() -> None:
    outage = openai.APIConnectionError(request=httpx.Request("POST", "https://api.openai.com"))
    model = OpenAIChatModel(
        fake_client(chat=SimpleNamespace(completions=FakeCompletions([], failure=outage))),
        model="m",
        temperature=0.2,
        max_tokens=10,
    )

    async def collect() -> list[str]:
        return [delta async for delta in model.stream([])]

    with pytest.raises(LLMUnavailableError):
        asyncio.run(collect())

    class FailingEmbeddings:
        async def create(self, **kwargs: object) -> None:
            raise outage

    embedder = OpenAIEmbedder(
        fake_client(embeddings=FailingEmbeddings()), model="m", dimensions=1, batch_size=1
    )
    with pytest.raises(LLMUnavailableError):
        asyncio.run(embedder.embed(["x"]))


def test_sdk_retries_are_disabled_so_the_backend_policy_is_the_only_one() -> None:
    # RNF07: 3 s first-token timeout x 2 attempts; SDK retries would stack on top of it.
    assert make_client(Settings(llm_api_key="test")).max_retries == 0


def test_query_embedding_uses_its_own_short_timeout() -> None:
    embeddings = FakeEmbeddings()
    embedder = OpenAIEmbedder(
        fake_client(embeddings=embeddings), model="m", dimensions=1, batch_size=1, timeout=3.0
    )
    asyncio.run(embedder.embed(["x"]))
    assert embeddings.kwargs["timeout"] == 3.0


def test_embedding_timeout_setting_defaults_to_three_seconds() -> None:
    assert Settings().embedding_timeout_seconds == 3.0


def _status_error(status: int) -> openai.APIStatusError:
    request = httpx.Request("POST", "https://api.openai.com/v1/chat/completions")
    return openai.APIStatusError(
        f"HTTP {status}", response=httpx.Response(status, request=request), body=None
    )


@pytest.mark.parametrize("status", [400, 401, 404, 429, 503])
def test_provider_status_errors_become_llm_unavailable(status: int) -> None:
    failure = _status_error(status)
    model = OpenAIChatModel(
        fake_client(chat=SimpleNamespace(completions=FakeCompletions([], failure=failure))),
        model="m",
        temperature=0.2,
        max_tokens=10,
    )

    async def collect() -> list[str]:
        return [delta async for delta in model.stream([])]

    with pytest.raises(LLMUnavailableError):
        asyncio.run(collect())

    class FailingEmbeddings:
        async def create(self, **kwargs: object) -> None:
            raise failure

    embedder = OpenAIEmbedder(
        fake_client(embeddings=FailingEmbeddings()), model="m", dimensions=1, batch_size=1
    )
    with pytest.raises(LLMUnavailableError):
        asyncio.run(embedder.embed(["x"]))


class PerModelCompletions:
    """Fails or stalls per model name, recording the order of models tried."""

    def __init__(self, behaviour: dict[str, Exception | str]) -> None:
        self.behaviour = behaviour
        self.models: list[str] = []

    async def create(self, **kwargs: Any) -> AsyncIterator[SimpleNamespace]:
        model = kwargs["model"]
        self.models.append(model)
        outcome = self.behaviour.get(model, "ok")
        if isinstance(outcome, Exception):
            raise outcome

        async def chunks() -> AsyncIterator[SimpleNamespace]:
            if outcome == "stall":
                await asyncio.sleep(1)
            yield SimpleNamespace(choices=[SimpleNamespace(delta=SimpleNamespace(content=model))])

        return chunks()


def _fallback_model(completions: PerModelCompletions) -> OpenAIChatModel:
    return OpenAIChatModel(
        fake_client(chat=SimpleNamespace(completions=completions)),
        model="primary",
        fallback_model="fallback",
        temperature=0.2,
        max_tokens=10,
        first_token_timeout=0.05,
        first_token_attempts=2,
    )


def _collect(model: OpenAIChatModel) -> list[str]:
    async def run() -> list[str]:
        return [delta async for delta in model.stream([])]

    return asyncio.run(run())


@pytest.mark.parametrize("status", [429, 503])
def test_quota_or_outage_on_the_primary_model_answers_with_the_fallback(status: int) -> None:
    # Separate per-model quotas (e.g. Gemini free tier RPM): a 429 on one model is not final.
    completions = PerModelCompletions({"primary": _status_error(status)})
    assert _collect(_fallback_model(completions)) == ["fallback"]
    assert completions.models == ["primary", "fallback"]


def test_slow_first_token_on_the_primary_model_moves_to_the_fallback() -> None:
    completions = PerModelCompletions({"primary": "stall"})
    assert _collect(_fallback_model(completions)) == ["fallback"]
    assert completions.models == ["primary", "fallback"]


def test_bad_key_does_not_waste_a_call_on_the_fallback() -> None:
    completions = PerModelCompletions({"primary": _status_error(401)})
    with pytest.raises(LLMUnavailableError):
        _collect(_fallback_model(completions))
    assert completions.models == ["primary"]


def test_both_models_rate_limited_is_llm_unavailable() -> None:
    completions = PerModelCompletions({"primary": _status_error(429), "fallback": _status_error(429)})
    with pytest.raises(LLMUnavailableError):
        _collect(_fallback_model(completions))
    assert completions.models == ["primary", "fallback"]


def test_fallback_model_setting_is_optional() -> None:
    assert Settings().llm_fallback_model == ""
    assert Settings(llm_fallback_model="gemini-3.1-flash-lite").llm_fallback_model == "gemini-3.1-flash-lite"
