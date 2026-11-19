"""Pydantic v2 contracts shared by ingestion, retrieval and generation."""

from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

Voltage = Literal["127V", "220V", "BIVOLT", "N/A"]
Marketplace = Literal["AMAZON", "MERCADO_LIVRE", "SHOPEE", "LOJA_OFICIAL"]
RelationType = Literal["UPSELL", "CROSS_SELL"]
SpecValue = str | int | float | bool


class CatalogProduct(BaseModel):
    """One row of data/catalog.json (UT-B01-01 schema validation)."""

    model_config = ConfigDict(extra="forbid")

    sku: str = Field(min_length=1, max_length=64)
    name: str = Field(min_length=1, max_length=255)
    category: str = Field(min_length=1, max_length=100)
    subcategory: str = Field(min_length=1, max_length=100)
    brand: str = Field(min_length=1, max_length=100)
    price: Decimal = Field(gt=0, max_digits=10, decimal_places=2)
    stock_quantity: int = Field(ge=0)
    voltage: Voltage
    capacity_liters: Decimal | None = Field(default=None, gt=0)
    power_watts: int | None = Field(default=None, gt=0)
    tier_rank: int = Field(default=1, ge=1, le=5)
    image_url: str
    marketplace: Marketplace = "AMAZON"
    checkout_url: str
    description: str = ""
    specs_json: dict[str, SpecValue] = Field(default_factory=dict)
    manual_title: str | None = None
    is_active: bool = True


class ProductRelation(BaseModel):
    """One row of data/product_relations.json; mirrors the product_relations DDL checks."""

    model_config = ConfigDict(extra="forbid")

    base_sku: str = Field(min_length=1, max_length=64)
    related_sku: str = Field(min_length=1, max_length=64)
    relation_type: RelationType
    affinity_weight: Decimal = Field(
        default=Decimal("0.800"), ge=0, le=1, max_digits=4, decimal_places=3
    )
    justification_template: str = Field(min_length=1)


class RetrievedChunk(BaseModel):
    chunk_id: UUID
    sku: str
    manual_title: str
    page_number: int = Field(ge=1)
    section_title: str | None = None
    content: str
    similarity_score: float = Field(ge=0.0, le=1.0)


class ChatTurn(BaseModel):
    role: Literal["user", "assistant"]
    content: str


class RagRequest(BaseModel):
    """Body of the internal POST /internal/rag/stream called by the middle-end."""

    sku: str = Field(min_length=1, max_length=64)
    question: str = Field(min_length=1, max_length=1000)
    history: list[ChatTurn] = Field(default_factory=list)
