"""OpenAI adapters behind small protocols, so the orchestrator is testable offline."""

import asyncio
from collections.abc import AsyncGenerator, AsyncIterator, Sequence
from typing import cast

import openai
from openai import AsyncOpenAI
from openai.types.chat import ChatCompletionMessageParam

from app.config import Settings
from app.generation.prompt import Message

_TRANSPORT_ERRORS = (
    openai.APIConnectionError,
    openai.APITimeoutError,
    openai.RateLimitError,
    openai.InternalServerError,
)


def make_client(settings: Settings) -> AsyncOpenAI:
    """OpenAI SDK client for the configured provider (OpenAI or an OpenAI-compatible API)."""
    return AsyncOpenAI(
        api_key=settings.llm_api_key,
        base_url=settings.llm_base_url or None,  # empty env var = provider default
        timeout=settings.llm_timeout_seconds,
    )


class LLMUnavailableError(Exception):
    """OpenAI unreachable, timed out or overloaded (maps to SSE LLM_UNAVAILABLE)."""


class OpenAIEmbedder:
    def __init__(self, client: AsyncOpenAI, *, model: str, dimensions: int, batch_size: int) -> None:
        self._client = client
        self._model = model
        self._dimensions = dimensions
        self._batch_size = batch_size

    async def embed(self, texts: Sequence[str]) -> list[list[float]]:
        vectors: list[list[float]] = []
        try:
            for start in range(0, len(texts), self._batch_size):
                response = await self._client.embeddings.create(
                    input=list(texts[start : start + self._batch_size]),
                    model=self._model,
                    dimensions=self._dimensions,
                )
                vectors.extend(item.embedding for item in response.data)
        except _TRANSPORT_ERRORS as error:
            raise LLMUnavailableError from error
        return vectors


class OpenAIChatModel:
    def __init__(
        self,
        client: AsyncOpenAI,
        *,
        model: str,
        temperature: float,
        max_tokens: int,
        first_token_timeout: float | None = None,
        first_token_attempts: int = 1,
    ) -> None:
        self._client = client
        self._model = model
        self._temperature = temperature
        self._max_tokens = max_tokens
        self._first_token_timeout = first_token_timeout
        self._first_token_attempts = first_token_attempts

    async def stream(self, messages: Sequence[Message]) -> AsyncIterator[str]:
        """Streams content deltas. RNF07: if the first token takes longer than
        `first_token_timeout`, the request is abandoned and retried (nothing was published yet)."""
        try:
            deltas = await self._open_with_first_token(messages)
            async for delta in deltas:
                yield delta
        except _TRANSPORT_ERRORS as error:
            raise LLMUnavailableError from error

    async def _open_with_first_token(self, messages: Sequence[Message]) -> AsyncIterator[str]:
        for attempt in range(1, self._first_token_attempts + 1):
            deltas = self._content(messages)
            try:
                first = await asyncio.wait_for(anext(deltas), self._first_token_timeout)
            except TimeoutError:
                await deltas.aclose()
                if attempt == self._first_token_attempts:
                    raise LLMUnavailableError("first token timeout") from None
                continue
            except StopAsyncIteration:
                return _prepend("", deltas)
            return _prepend(first, deltas)
        raise LLMUnavailableError("no attempt configured")

    async def _content(self, messages: Sequence[Message]) -> AsyncGenerator[str, None]:
        stream = await self._client.chat.completions.create(
            model=self._model,
            messages=cast(list[ChatCompletionMessageParam], list(messages)),
            temperature=self._temperature,
            max_tokens=self._max_tokens,
            stream=True,
        )
        async for chunk in stream:
            if chunk.choices and chunk.choices[0].delta.content:
                yield chunk.choices[0].delta.content


async def _prepend(first: str, rest: AsyncIterator[str]) -> AsyncIterator[str]:
    if first:
        yield first
    async for delta in rest:
        yield delta
