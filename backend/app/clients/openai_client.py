"""OpenAI adapters behind small protocols, so the orchestrator is testable offline."""

import asyncio
from collections.abc import AsyncGenerator, AsyncIterator, Sequence
from typing import cast

import openai
from openai import NOT_GIVEN, AsyncOpenAI, NotGiven
from openai.types.chat import ChatCompletionMessageParam

from app.config import Settings
from app.generation.prompt import Message

# Transport failures (timeouts included) and every HTTP error status: a bad key (401),
# unknown model (404) or quota (429) must end the turn as LLM_UNAVAILABLE, not break it.
_PROVIDER_ERRORS = (openai.APIConnectionError, openai.APIStatusError)
# Worth another attempt (on the fallback model, whose quota is separate): quota, provider
# outage, network. A bad key (401), bad request (400) or unknown model (404) is not.
_RETRYABLE_STATUS = {429, 500, 502, 503, 504}


def _retryable(error: Exception) -> bool:
    if isinstance(error, openai.APIConnectionError):  # includes APITimeoutError
        return True
    return isinstance(error, openai.APIStatusError) and error.status_code in _RETRYABLE_STATUS


def make_client(settings: Settings) -> AsyncOpenAI:
    """OpenAI SDK client for the configured provider (OpenAI or an OpenAI-compatible API)."""
    return AsyncOpenAI(
        api_key=settings.llm_api_key,
        base_url=settings.llm_base_url or None,  # empty env var = provider default
        timeout=settings.llm_timeout_seconds,
        # RNF07 retry (first-token timeout x attempts) is the only retry policy; ingestion
        # has its own backoff. SDK retries would silently multiply the worst-case latency.
        max_retries=0,
    )


class LLMUnavailableError(Exception):
    """Provider unreachable, timed out or answering an HTTP error (maps to SSE LLM_UNAVAILABLE)."""


class OpenAIEmbedder:
    def __init__(
        self,
        client: AsyncOpenAI,
        *,
        model: str,
        dimensions: int,
        batch_size: int,
        timeout: float | None = None,
    ) -> None:
        self._client = client
        self._model = model
        self._dimensions = dimensions
        self._batch_size = batch_size
        # None keeps the client timeout (ingestion batches); the query path passes a short one.
        self._timeout: float | NotGiven = NOT_GIVEN if timeout is None else timeout

    async def embed(self, texts: Sequence[str]) -> list[list[float]]:
        vectors: list[list[float]] = []
        try:
            for start in range(0, len(texts), self._batch_size):
                response = await self._client.embeddings.create(
                    input=list(texts[start : start + self._batch_size]),
                    model=self._model,
                    dimensions=self._dimensions,
                    timeout=self._timeout,
                )
                vectors.extend(item.embedding for item in response.data)
        except _PROVIDER_ERRORS as error:
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
        fallback_model: str | None = None,
    ) -> None:
        self._client = client
        self._model = model
        self._fallback_model = fallback_model or model
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
        except _PROVIDER_ERRORS as error:
            raise LLMUnavailableError from error

    async def _open_with_first_token(self, messages: Sequence[Message]) -> AsyncIterator[str]:
        """The first attempt uses the primary model; retries go to the fallback model."""
        for attempt in range(1, self._first_token_attempts + 1):
            model = self._model if attempt == 1 else self._fallback_model
            deltas = self._content(messages, model)
            last = attempt == self._first_token_attempts
            try:
                first = await asyncio.wait_for(anext(deltas), self._first_token_timeout)
            except TimeoutError:
                await deltas.aclose()
                if last:
                    raise LLMUnavailableError("first token timeout") from None
                continue
            except _PROVIDER_ERRORS as error:
                await deltas.aclose()
                if last or not _retryable(error):
                    raise
                continue
            except StopAsyncIteration:
                return _prepend("", deltas)
            return _prepend(first, deltas)
        raise LLMUnavailableError("no attempt configured")

    async def _content(
        self, messages: Sequence[Message], model: str
    ) -> AsyncGenerator[str, None]:
        stream = await self._client.chat.completions.create(
            model=model,
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
