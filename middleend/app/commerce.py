"""Request and response models for the catalog, feedback and mock checkout."""

from datetime import datetime
from decimal import Decimal
from typing import Annotated, Literal, Self
from uuid import UUID

from pydantic import BaseModel, Field, PlainSerializer, field_validator, model_validator

from app.schemas import CATEGORY_MAX_LENGTH, SKU_MAX_LENGTH

VoltageFilter = Literal["127V", "220V"]
RecommendationType = Literal["PRIMARY", "UPSELL", "CROSS_SELL", "OPTION"]
ConflictStatus = Literal["OUT_OF_STOCK", "PRICE_CHANGED"]
Money = Annotated[Decimal, PlainSerializer(float, return_type=float, when_used="json")]
MAX_POSTGRES_INTEGER = 2_147_483_647


class Product(BaseModel):
    sku: str
    name: str
    price: Money
    stock_quantity: int
    voltage: Literal["127V", "220V", "BIVOLT", "N/A"]
    capacity_liters: float | None
    power_watts: int | None
    image_url: str
    marketplace: Literal["AMAZON", "MERCADO_LIVRE", "SHOPEE", "LOJA_OFICIAL"]
    checkout_url: str
    category: str
    subcategory: str
    brand: str
    specs_json: dict[str, object]
    description: str | None = None
    updated_at: datetime


class CatalogQuery(BaseModel):
    q: str | None = Field(default=None, max_length=200)
    category: str | None = Field(default=None, max_length=CATEGORY_MAX_LENGTH)
    voltage: VoltageFilter | None = None
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=20, ge=1, le=100)


class Catalog(BaseModel):
    items: list[Product]
    page: int
    page_size: int
    total: int


class MessageReference(BaseModel):
    session_id: UUID
    message_id: UUID


class FeedbackCreate(MessageReference):
    rating: Literal["LIKE", "DISLIKE"]
    reason_category: Literal["HALLUCINATION", "WRONG_VOLTAGE", "SLOW", "OTHER"] | None = None
    comment: str | None = Field(default=None, max_length=1000)

    @model_validator(mode="after")
    def require_dislike_reason(self) -> Self:
        if self.rating == "DISLIKE" and self.reason_category is None:
            raise ValueError("Informe o motivo do dislike.")
        return self


class FeedbackRecorded(BaseModel):
    feedback_id: UUID
    status: Literal["RECORDED"] = "RECORDED"
    recorded_at: datetime


class CheckoutCreate(MessageReference):
    sku: str = Field(max_length=SKU_MAX_LENGTH)
    recommendation_type: RecommendationType
    quantity: int = Field(ge=1, le=MAX_POSTGRES_INTEGER)
    displayed_price: Decimal = Field(gt=0, decimal_places=2)

    @field_validator("displayed_price", mode="before")
    @classmethod
    def require_json_number(cls, value: object) -> object:
        if type(value) not in (int, float, Decimal):
            raise ValueError("Informe o preço como número.")
        return value


class Checkout(BaseModel):
    checkout_event_id: UUID
    status: Literal["CONFIRMED"] = "CONFIRMED"
    sku: str
    product_name: str
    voltage: str
    marketplace: str
    redirect_checkout_url: str
    quantity: int
    confirmed_unit_price: Money
    total_amount: Money
    remaining_stock: int
    message: str


class CheckoutConflict(BaseModel):
    checkout_event_id: UUID
    status: ConflictStatus
    sku: str
    current_price: Money
    current_stock: int
    redirect_checkout_url: None = None
    message: str


class MessageNotFound(Exception):
    """The supplied session and assistant message do not match a stored turn."""


class FeedbackAlreadyRecorded(Exception):
    """Only one rating may be recorded for an assistant message."""


class CatalogNotReady(Exception):
    """`products` does not exist yet: the backend ingestion (UC08) has not run."""


class SessionEnded(Exception):
    """The session was closed (DELETE or TTL); its messages can no longer be rated or bought."""


class ProductNotFound(Exception):
    """The product is unknown or inactive."""


def checkout_conflict(product: Product, request: CheckoutCreate) -> ConflictStatus | None:
    if product.stock_quantity < request.quantity:
        return "OUT_OF_STOCK"
    if product.price != request.displayed_price:
        return "PRICE_CHANGED"
    return None
