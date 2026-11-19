"""Pinned RAGAS cognitive metrics; never substitute a lexical score or a reference answer."""

import asyncio
import math
from typing import Protocol

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class JudgeSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="EVAL_", extra="ignore")
    judge_api_key: SecretStr = Field(min_length=1)
    judge_model: str = Field(min_length=1)
    judge_base_url: str | None = None
    embedding_model: str = "text-embedding-3-small"
    embedding_dimensions: int = 1536
    # Answer Relevance needs an embeddings API. Chat-only judges (e.g. DeepSeek) point
    # these at another OpenAI-compatible provider; unset, the judge endpoint is reused.
    embedding_api_key: SecretStr | None = None
    embedding_base_url: str | None = None
    metric_timeout_seconds: float = Field(default=120.0, gt=0)
    request_timeout_seconds: float = Field(default=30.0, gt=0)

    def embedding_endpoint(self) -> tuple[str, str | None]:
        """(api_key, base_url) for judge embeddings.

        A dedicated key never inherits the judge URL: that would send it to the judge host.
        """
        if self.embedding_api_key is not None:
            return self.embedding_api_key.get_secret_value(), self.embedding_base_url or None
        return (
            self.judge_api_key.get_secret_value(),
            self.embedding_base_url or self.judge_base_url or None,
        )


class CognitiveJudge(Protocol):
    async def score(self, query: str, answer: str, contexts: list[str]) -> tuple[float, float]: ...


class JudgeFailure(ValueError):
    """Missing evidence, empty output, invalid score or evaluator failure cannot pass a gate."""


class SingleTurnScorer(Protocol):
    async def single_turn_ascore(self, sample: object, **kwargs: object) -> float: ...


def checked_score(value: float) -> float:
    if not math.isfinite(value) or not 0 <= value <= 1:
        raise JudgeFailure("Judge returned a nonfinite/out-of-range score")
    return value


class RagasJudge:
    def __init__(
        self,
        faithfulness: SingleTurnScorer,
        relevance: SingleTurnScorer,
        timeout_seconds: float = 120.0,
    ) -> None:
        self.faithfulness, self.relevance, self.timeout = faithfulness, relevance, timeout_seconds

    @classmethod
    def from_settings(cls, settings: JudgeSettings) -> "RagasJudge":
        from langchain_openai import ChatOpenAI, OpenAIEmbeddings
        from ragas.embeddings import LangchainEmbeddingsWrapper
        from ragas.llms import LangchainLLMWrapper
        from ragas.metrics import Faithfulness, ResponseRelevancy
        from ragas.run_config import RunConfig

        client = ChatOpenAI(
            model=settings.judge_model,
            api_key=settings.judge_api_key,
            base_url=settings.judge_base_url or None,
            temperature=0.0,
            timeout=settings.request_timeout_seconds,
            max_retries=1,
        )
        embedding_key, embedding_url = settings.embedding_endpoint()
        embeddings = OpenAIEmbeddings(
            model=settings.embedding_model,
            api_key=SecretStr(embedding_key),
            base_url=embedding_url,
            dimensions=settings.embedding_dimensions,
            timeout=settings.request_timeout_seconds,
            max_retries=1,
            check_embedding_ctx_length=False,
        )
        llm = LangchainLLMWrapper(
            client,
            run_config=RunConfig(
                timeout=int(settings.request_timeout_seconds), max_retries=1, max_wait=1
            ),
        )
        return cls(
            Faithfulness(llm=llm),
            ResponseRelevancy(llm=llm, embeddings=LangchainEmbeddingsWrapper(embeddings)),
            settings.metric_timeout_seconds,
        )

    async def score(self, query: str, answer: str, contexts: list[str]) -> tuple[float, float]:
        from ragas import SingleTurnSample

        if (
            not query.strip()
            or not answer.strip()
            or not contexts
            or not any(c.strip() for c in contexts)
        ):
            raise JudgeFailure(
                "Cognitive metrics require a question, published answer and evidence"
            )
        sample = SingleTurnSample(user_input=query, response=answer, retrieved_contexts=contexts)
        scores = await asyncio.wait_for(
            asyncio.gather(
                self.faithfulness.single_turn_ascore(sample),
                self.relevance.single_turn_ascore(sample),
            ),
            self.timeout,
        )
        return checked_score(float(scores[0])), checked_score(float(scores[1]))
