import asyncio
from collections.abc import AsyncIterator, Sequence

import httpx2 as httpx
import openai
import pytest
from app.clients.openai_client import LLMUnavailableError
from app.generation.prompt import Message

from .judge import RagasJudge
from .pipeline import ObservedChat, ObservedEmbedder
from .retry import ProviderRetry, RetrySettings

REQUEST = httpx.Request("POST", "https://provider.example/v1/chat/completions")


def rate_limited(retry_after: str | None = None) -> openai.RateLimitError:
    headers = {"retry-after": retry_after} if retry_after else {}
    return openai.RateLimitError(
        "quota", response=httpx.Response(429, headers=headers, request=REQUEST), body=None
    )


def unauthorized() -> openai.AuthenticationError:
    return openai.AuthenticationError(
        "bad key", response=httpx.Response(401, request=REQUEST), body=None
    )


class Clock:
    def __init__(self) -> None:
        self.now, self.sleeps = 0.0, list[float]()

    async def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)
        self.now += seconds

    def __call__(self) -> float:
        return self.now


def retry(max_retries: int = 6, min_interval: float = 0.0) -> tuple[ProviderRetry, Clock]:
    clock = Clock()
    settings = RetrySettings(max_retries=max_retries, min_interval_seconds=min_interval)
    return ProviderRetry(settings, sleep=clock.sleep, clock=clock), clock


def flaky(errors: list[Exception]) -> tuple[list[int], object]:
    calls: list[int] = []

    async def call() -> str:
        calls.append(1)
        if errors:
            raise errors.pop(0)
        return "ok"

    return calls, call


def test_settings_come_from_eval_env(monkeypatch: pytest.MonkeyPatch) -> None:
    assert RetrySettings().max_retries == 6 and RetrySettings().min_interval_seconds == 0
    monkeypatch.setenv("EVAL_MAX_RETRIES", "2")
    monkeypatch.setenv("EVAL_MIN_INTERVAL_SECONDS", "7.5")
    assert (RetrySettings().max_retries, RetrySettings().min_interval_seconds) == (2, 7.5)


def test_rate_limit_honors_retry_after_then_succeeds() -> None:
    policy, clock = retry()
    calls, call = flaky([rate_limited("7")])
    assert asyncio.run(policy.run(call)) == "ok"  # type: ignore[arg-type]
    assert len(calls) == 2 and clock.sleeps == [7.0]


def test_without_retry_after_backoff_is_exponential() -> None:
    policy, clock = retry()
    _, call = flaky([rate_limited(), openai.APITimeoutError(REQUEST), TimeoutError()])
    assert asyncio.run(policy.run(call)) == "ok"  # type: ignore[arg-type]
    assert clock.sleeps == [2.0, 4.0, 8.0]


def test_wrapped_provider_quota_is_retried() -> None:
    policy, clock = retry()
    wrapped = LLMUnavailableError()
    wrapped.__cause__ = rate_limited()
    _, call = flaky([wrapped])
    assert asyncio.run(policy.run(call)) == "ok"  # type: ignore[arg-type]
    assert clock.sleeps == [2.0]


@pytest.mark.parametrize("error", [unauthorized(), ValueError("bad sample"), LLMUnavailableError()])
def test_non_transient_errors_are_not_retried(error: Exception) -> None:
    policy, clock = retry()
    calls, call = flaky([error])
    with pytest.raises(type(error)):
        asyncio.run(policy.run(call))  # type: ignore[arg-type]
    assert len(calls) == 1 and clock.sleeps == []


def test_retries_are_bounded() -> None:
    policy, clock = retry(max_retries=2)
    calls, call = flaky([rate_limited() for _ in range(5)])
    with pytest.raises(openai.RateLimitError):
        asyncio.run(policy.run(call))  # type: ignore[arg-type]
    assert len(calls) == 3 and clock.sleeps == [2.0, 4.0]


def test_min_interval_spaces_consecutive_calls() -> None:
    policy, clock = retry(min_interval=7.0)
    _, call = flaky([])
    asyncio.run(policy.run(call))  # type: ignore[arg-type]
    clock.now += 2.0
    asyncio.run(policy.run(call))  # type: ignore[arg-type]
    assert clock.sleeps == [5.0]


class QuotaThenAnswer:
    def __init__(self, failures: int, *, partial: bool = False) -> None:
        self.failures, self.partial, self.calls = failures, partial, 0

    async def stream(self, messages: Sequence[Message]) -> AsyncIterator[str]:
        self.calls += 1
        if self.partial:
            yield "parcial "
        if self.calls <= self.failures:
            raise LLMUnavailableError from rate_limited()
        yield "resposta"


async def _collect(chat: ObservedChat) -> str:
    return "".join([delta async for delta in chat.stream([{"role": "user", "content": "?"}])])


def test_generator_quota_before_the_first_token_is_retried_once_per_turn() -> None:
    policy, clock = retry()
    model = QuotaThenAnswer(failures=2)
    chat = ObservedChat(model, policy)
    assert asyncio.run(_collect(chat)) == "resposta"
    assert model.calls == 3 and chat.calls == 1 and clock.sleeps == [2.0, 4.0]


def test_generator_failure_after_a_published_token_is_not_retried() -> None:
    policy, _ = retry()
    model = QuotaThenAnswer(failures=1, partial=True)
    with pytest.raises(LLMUnavailableError):
        asyncio.run(_collect(ObservedChat(model, policy)))
    assert model.calls == 1


def test_query_embedding_quota_is_retried() -> None:
    class Embedder:
        calls = 0

        async def embed(self, texts: Sequence[str]) -> list[list[float]]:
            Embedder.calls += 1
            if Embedder.calls == 1:
                raise LLMUnavailableError from rate_limited("1")
            return [[0.1] for _ in texts]

    policy, clock = retry()
    assert asyncio.run(ObservedEmbedder(Embedder(), policy).embed(["q"])) == [[0.1]]
    assert clock.sleeps == [1.0]


class QuotaScorer:
    def __init__(self, failures: int) -> None:
        self.failures, self.calls = failures, 0

    async def single_turn_ascore(self, sample: object, **kwargs: object) -> float:
        self.calls += 1
        if self.calls <= self.failures:
            raise rate_limited()
        return 0.9


def test_judge_rate_limit_is_retried_without_changing_the_score() -> None:
    pytest.importorskip("ragas")
    policy, clock = retry()
    judge = RagasJudge(QuotaScorer(failures=1), QuotaScorer(failures=0), retry=policy)
    assert asyncio.run(judge.score("q", "a", ["evidence"])) == (0.9, 0.9)
    assert clock.sleeps == [2.0]
