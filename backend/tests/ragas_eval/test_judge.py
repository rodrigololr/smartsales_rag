import asyncio

import pytest
from pydantic import SecretStr

from .judge import JudgeFailure, JudgeSettings, RagasJudge


class ConstantScorer:
    def __init__(self, value: float) -> None:
        self.value = value

    async def single_turn_ascore(self, sample: object, **kwargs: object) -> float:
        return self.value


@pytest.mark.parametrize("answer,contexts", [("", ["evidence"]), ("answer", []), ("answer", [""])])
def test_empty_answer_or_evidence_never_gets_perfect_faithfulness(
    answer: str, contexts: list[str]
) -> None:
    judge = RagasJudge(ConstantScorer(1.0), ConstantScorer(1.0))
    with pytest.raises(JudgeFailure):
        asyncio.run(judge.score("question", answer, contexts))


def test_nan_judge_result_is_an_error() -> None:
    judge = RagasJudge(ConstantScorer(float("nan")), ConstantScorer(1.0))
    with pytest.raises(JudgeFailure):
        asyncio.run(judge.score("question", "answer", ["evidence"]))


def test_actual_ragas_faithfulness_uses_statement_judgments() -> None:
    from langchain_core.language_models.fake_chat_models import FakeListChatModel
    from ragas.llms import LangchainLLMWrapper
    from ragas.metrics import Faithfulness

    llm = FakeListChatModel(
        responses=[
            '{"statements": ["A airfryer opera em 127V com potência de 3000W."]}',
            '{"statements": [{"statement": "A airfryer opera em 127V com potência de 3000W.", '
            '"reason": "A evidência diz 220V e 1500W, contradizendo ambos os dados.", "verdict": 0}]}',
        ]
    )
    from ragas.run_config import RunConfig

    metric = Faithfulness(
        llm=LangchainLLMWrapper(llm, run_config=RunConfig(max_retries=1, max_wait=1))
    )
    judge = RagasJudge(metric, ConstantScorer(1.0), timeout_seconds=5)
    score, _ = asyncio.run(
        judge.score(
            "Qual a tensão e potência?",
            "Opera em 127V com potência de 3000W.",
            ["Opera em 220V com potência de 1500W."],
        )
    )
    assert score == 0.0


def test_live_factory_constructs_real_ragas_metrics_without_network() -> None:
    from ragas.metrics import Faithfulness, ResponseRelevancy

    judge = RagasJudge.from_settings(
        JudgeSettings(judge_api_key=SecretStr("test-only"), judge_model="judge-model")
    )
    assert isinstance(judge.faithfulness, Faithfulness)
    assert isinstance(judge.relevance, ResponseRelevancy)
