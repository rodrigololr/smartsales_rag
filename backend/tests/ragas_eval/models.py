"""Versioned inputs, observations and evidence for the B05 evaluation."""

from decimal import Decimal
from typing import Annotated, Literal

from app.models.schemas import CatalogProduct, Voltage
from pydantic import BaseModel, ConfigDict, Field, model_validator

Score = Annotated[float, Field(ge=0, le=1, allow_inf_nan=False)]
Stock = Annotated[int, Field(ge=0, strict=True)]
Action = Literal["ANSWER", "REFUSE", "FALLBACK", "ERROR"]
Role = Literal["PRIMARY", "UPSELL", "CROSS_SELL"]
Category = Literal[
    "Técnica Exata",
    "Voltagem Crítica",
    "Coloquial / Medida",
    "Upsell + Cross-sell",
    "Adversarial / Sem Evidência",
]
Metric = Literal["faithfulness", "answer_relevance", "retrieval"]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)


class EvidenceRef(StrictModel):
    sku: str
    source: str
    source_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    page_number: int = Field(ge=1)
    chunk_index: int = Field(ge=0)
    quote: str = Field(min_length=1)

    @property
    def key(self) -> str:
        return "|".join(
            (
                self.sku,
                self.source,
                self.source_sha256,
                str(self.page_number),
                str(self.chunk_index),
            )
        )


class InputFilters(StrictModel):
    sku: str
    voltage: Literal["127V", "220V"] | None = None


class ExpectedOffer(StrictModel):
    sku: str
    role: Role


class PipelineInput(StrictModel):
    """The system under test never receives a reference answer or evidence label."""

    sku: str
    question: str
    requested_voltage: Literal["127V", "220V"] | None = None
    stock_overrides: dict[str, Stock] = Field(default_factory=dict)


class GoldenSetFixture(StrictModel):
    id: str = Field(pattern=r"^RAGAS-GS-\d{2}$")
    category: Category
    query: str = Field(min_length=1)
    input_filters: InputFilters
    expected_action: Literal["ANSWER", "REFUSE", "FALLBACK"]
    answerable: bool
    expected_answer: str = Field(min_length=1)
    relevant_evidence: list[EvidenceRef]
    audit_evidence: list[EvidenceRef]
    applicable_metrics: list[Metric]
    expected_offers: list[ExpectedOffer] = Field(default_factory=list)
    stock_overrides: dict[str, Stock] = Field(default_factory=dict)
    offer_policy: Literal["required", "exact"] = "required"
    business_rule: str
    audit_status: Literal["seed_verified_pending_po"] = "seed_verified_pending_po"

    @model_validator(mode="after")
    def validate_applicability(self) -> "GoldenSetFixture":
        answering = self.expected_action == "ANSWER"
        if self.answerable != answering:
            raise ValueError("answerable must agree with expected_action")
        if answering and (
            not self.relevant_evidence
            or set(self.applicable_metrics)
            != {
                "faithfulness",
                "answer_relevance",
                "retrieval",
            }
        ):
            raise ValueError("ANSWER requires evidence and all three cognitive/retrieval metrics")
        if not answering and (self.relevant_evidence or self.applicable_metrics):
            raise ValueError(
                "negative cases do not label retrieval/cognitive metrics as applicable"
            )
        if not self.audit_evidence:
            raise ValueError("every case requires a verifiable audit source")
        return self

    def pipeline_input(self) -> PipelineInput:
        return PipelineInput(
            sku=self.input_filters.sku,
            question=self.query,
            requested_voltage=self.input_filters.voltage,
            stock_overrides=self.stock_overrides,
        )


class ObservedEvidence(StrictModel):
    chunk_id: str
    key: str
    sku: str
    manual_title: str
    page_number: int
    content: str


class ObservedOffer(StrictModel):
    sku: str
    role: Role
    price: Decimal = Field(gt=0)
    stock_quantity: int | None = None
    voltage: Voltage | None = None


class ObservedTurn(StrictModel):
    action: Action
    answer: str = ""
    emitted_content: str = ""
    blocked_sentences: int = 0
    citations: list[tuple[str, str, int]] = Field(default_factory=list)
    retrieved: list[ObservedEvidence] = Field(default_factory=list)
    evidence_contexts: list[str] = Field(default_factory=list)
    products: dict[str, CatalogProduct] = Field(default_factory=dict)
    offers: list[ObservedOffer] = Field(default_factory=list)
    generation_calls: int = 0
    citation_chunk_ids: list[str] = Field(default_factory=list)
    events: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)


class EvalCaseResult(StrictModel):
    case_id: str
    expected_action: str
    actual_action: Action
    expected_metrics: list[Metric] = Field(default_factory=list)
    actual_answer: str = ""
    retrieved_chunk_ids: list[str] = Field(default_factory=list)
    faithfulness: Score | None = None
    answer_relevance: Score | None = None
    precision_at_5: Score | None = None
    precision_returned: Score | None = None
    recall: Score | None = None
    technical_violations: list[str] = Field(default_factory=list)
    business_violations: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)
    generation_calls: int = 0
    observation: ObservedTurn | None = None

    @property
    def action_matched(self) -> bool:
        return self.actual_action == self.expected_action


class RunIdentity(StrictModel):
    schema_version: int = 2
    mode: Literal["test", "live", "validate"]
    fingerprint: str = ""
    revision: str = ""
    corpus_sha256: str = ""
    fixture_sha256: str = ""
    policy_version: str = "b05-v2"
    generator_model: str = ""
    judge_model: str = ""
    configuration: dict[str, str | int | float | bool | None] = Field(default_factory=dict)
    expected_cases: int = 50
    corpus_verified: bool = False
    integrated_b04: bool = False
    po_audit_approved: bool = False
    clean_checkout: bool = False


class GateResult(StrictModel):
    metric_name: str
    value: float | None
    threshold: float
    comparator: Literal[">=", "<="] = ">="
    denominator: int
    passed: bool
    reason: str = ""


class EvaluationReport(StrictModel):
    identity: RunIdentity
    total_cases: int
    evaluated_cases: int
    faithfulness_macro: float | None
    precision_macro: float | None
    recall_macro: float | None
    answer_relevance_macro: float | None
    gates: list[GateResult]
    all_gates_passed: bool
    status: Literal["PENDING", "FAILED", "PASSED"]
    case_results: list[EvalCaseResult]
    exclusions: dict[str, list[str]] = Field(default_factory=dict)
    errors: list[str] = Field(default_factory=list)
