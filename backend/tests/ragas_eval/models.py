"""Pydantic models for Golden Set fixtures and RAGAS evaluation (B05 / EAP 5.1)."""

from typing import Any, Literal
from pydantic import BaseModel, Field

CategoryType = Literal[
    "Técnica Exata",
    "Voltagem Crítica",
    "Coloquial / Medida",
    "Upsell + Cross-sell",
    "Adversarial / Sem Evidência",
]

ActionType = Literal["ANSWER", "REFUSE", "FALLBACK"]


class GoldenSetFixture(BaseModel):
    """Audited fixture defining one test case in the Golden Set."""

    id: str = Field(description="Unique fixture identifier (RAGAS-GS-01..50)")
    category: CategoryType = Field(description="One of the 5 official stress categories")
    query: str = Field(description="User prompt in colloquial or technical form")
    input_filters: dict[str, Any] = Field(default_factory=dict, description="Pre-filters like sku or voltage")
    expected_action: ActionType = Field(description="ANSWER, REFUSE (G-IN) or FALLBACK (low similarity)")
    answerable: bool = Field(description="True if facts are present in manual; False for off-topic/injection")
    expected_answer: str = Field(description="Ground truth expectation")
    expected_citations: list[str] = Field(default_factory=list, description="Expected manual citation references")
    relevant_chunk_ids: list[str] = Field(default_factory=list, description="Target chunk IDs in vector corpus")
    applicable_metrics: list[str] = Field(
        default_factory=list,
        description="Metrics that apply (faithfulness, answer_relevance, precision_at_5, technical_hallucination, business_rule_adherence, action_accuracy)",
    )
    business_rule: str = Field(description="Associated business rules (e.g. RN01, RN02, RNF09)")


class EvalCaseResult(BaseModel):
    """Evaluation result for a single Golden Set case."""

    case_id: str
    category: str
    expected_action: str
    actual_action: str
    answerable: bool
    actual_answer: str = ""
    actual_citations: list[str] = Field(default_factory=list)
    retrieved_chunks: list[str] = Field(default_factory=list)
    faithfulness: float | None = None
    answer_relevance: float | None = None
    precision_at_5: float | None = None
    precision_returned: float | None = None
    recall: float | None = None
    technical_hallucination: bool = False
    business_rule_adherence: bool = True
    action_matched: bool = True
    details: dict[str, Any] = Field(default_factory=dict)


class GateResult(BaseModel):
    """Status of a quality gate against CI blocking threshold."""

    metric_name: str
    value: float
    threshold: float
    comparator: Literal[">=", "<="]
    passed: bool
    description: str


class EvaluationReport(BaseModel):
    """Consolidated report across all evaluated Golden Set cases."""

    total_cases: int
    evaluated_cases: int
    faithfulness_macro: float
    precision_at_5_macro: float
    technical_hallucination_rate: float
    answer_relevance_macro: float
    business_rule_adherence_rate: float
    action_accuracy: float
    gates: list[GateResult]
    all_gates_passed: bool
    case_results: list[EvalCaseResult]
