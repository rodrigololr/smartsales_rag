"""Public request contracts (openapi.yaml: SessionCreate, ChatStreamRequest, Filters)."""

from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class SessionCreate(BaseModel):
    session_id: UUID | None = None
    current_product_sku: str | None = Field(default=None, max_length=64)


class Filters(BaseModel):
    model_config = ConfigDict(extra="forbid")

    preferred_voltage: Literal["127V", "220V"] | None = None
    category: str | None = None
    current_product_sku: str | None = Field(default=None, max_length=64)
    capacity_min: float | None = None
    budget_max: Decimal | None = Field(default=None, gt=0, decimal_places=2)


class ChatStreamRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    session_id: UUID
    client_request_id: UUID
    message: str = Field(min_length=1, max_length=1000)
    context_filters: Filters | None = None
