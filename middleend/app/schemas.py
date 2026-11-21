"""Public contracts (openapi.yaml: SessionCreate, ChatStreamRequest, Filters, Error)."""

from decimal import Decimal
from http import HTTPStatus
from typing import Any, Literal
from uuid import UUID

from pydantic import UUID4, BaseModel, ConfigDict, Field


class ErrorDetail(BaseModel):
    code: str
    message: str
    trace_id: str
    details: object


class ErrorEnvelope(BaseModel):
    error: ErrorDetail


SKU_MAX_LENGTH = 64  # products.sku VARCHAR(64)
CATEGORY_MAX_LENGTH = 64  # filter input bound; catalog categories are far shorter

# Error statuses openapi.yaml documents on every public operation (CT-M01-01).
ERROR_STATUSES = (401, 404, 409, 410, 422, 429, 500, 503)
ERROR_RESPONSES: dict[int | str, dict[str, Any]] = {
    status: {"model": ErrorEnvelope} for status in ERROR_STATUSES
}
# Same envelope for a route whose 200 is not JSON (SSE): with "model", FastAPI would file the
# schema under the route's media type. The component exists via the ERROR_RESPONSES routes.
JSON_ERROR_RESPONSES: dict[int | str, dict[str, Any]] = {
    status: {
        "description": HTTPStatus(status).phrase,
        "content": {"application/json": {"schema": {"$ref": "#/components/schemas/ErrorEnvelope"}}},
    }
    for status in ERROR_STATUSES
}


class SessionCreate(BaseModel):
    session_id: UUID | None = None
    current_product_sku: str | None = Field(default=None, max_length=SKU_MAX_LENGTH)


class Filters(BaseModel):
    model_config = ConfigDict(extra="forbid")

    preferred_voltage: Literal["127V", "220V"] | None = None
    category: str | None = Field(default=None, max_length=CATEGORY_MAX_LENGTH)
    current_product_sku: str | None = Field(
        default=None, max_length=SKU_MAX_LENGTH, description="omitido = modo catálogo"
    )
    capacity_min: float | None = Field(default=None, ge=0, allow_inf_nan=False)
    budget_max: Decimal | None = Field(default=None, gt=0, decimal_places=2)


class ChatStreamRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    session_id: UUID
    client_request_id: UUID4
    message: str = Field(min_length=1, max_length=1000)
    context_filters: Filters | None = None
