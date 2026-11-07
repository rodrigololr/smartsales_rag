"""OpenAI adapters behind small protocols, so the orchestrator is testable offline."""

from collections.abc import AsyncIterator, Sequence
from typing import cast

import openai
from openai import AsyncOpenAI
from openai.types.chat import ChatCompletionMessageParam

from app.generation.prompt import Message

_TRANSPORT_ERRORS = (
    openai.APIConnectionError,
    openai.APITimeoutError,
    openai.RateLimitError,
    openai.InternalServerError,
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
        self, client: AsyncOpenAI, *, model: str, temperature: float, max_tokens: int
    ) -> None:
        self._client = client
        self._model = model
        self._temperature = temperature
        self._max_tokens = max_tokens

    async def stream(self, messages: Sequence[Message]) -> AsyncIterator[str]:
        try:
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
        except _TRANSPORT_ERRORS as error:
            raise LLMUnavailableError from error
