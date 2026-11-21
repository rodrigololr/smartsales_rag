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
