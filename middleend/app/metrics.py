"""M04 metrics summary (UC09): response model and window rules for GET /metrics/summary."""

from datetime import datetime, timedelta

from pydantic import BaseModel, ConfigDict, Field

# specs/architecture/03_openapi_and_sse_contracts.md 3.5: default window = last 7 days.
DEFAULT_METRICS_WINDOW = timedelta(days=7)
TOP_QUESTIONS_LIMIT = 5
MEDIAN = 0.5
P95 = 0.95


class InvalidMetricsWindow(Exception):
    """`from` must be strictly before `to`."""


class MetricsWindow(BaseModel):
    """Half-open interval [from, to) applied to every metric."""

    model_config = ConfigDict(populate_by_name=True)

    window_from: datetime = Field(serialization_alias="from")
    window_to: datetime = Field(serialization_alias="to")


class TopQuestion(BaseModel):
    question: str
    count: int


class Metrics(BaseModel):
    window: MetricsWindow
    turns: int
    ttft_p50_ms: float
    ttft_p95_ms: float
    total_latency_p95_ms: float
    cache_hit_ratio: float
    error_5xx_rate: float
    like_ratio: float
    card_ctr: float
    confirmed_checkouts: int
    top_questions: list[TopQuestion]


def resolve_window(
    window_from: datetime | None, window_to: datetime | None, now: datetime
) -> MetricsWindow:
    end = window_to or now
    start = window_from or end - DEFAULT_METRICS_WINDOW
    if start >= end:
        raise InvalidMetricsWindow
    return MetricsWindow(window_from=start, window_to=end)
