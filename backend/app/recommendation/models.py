"""Pure B04 values: adapters supply trusted current SQL and manual facts."""

from dataclasses import dataclass
from decimal import Decimal
from typing import Literal

Voltage = Literal["127V", "220V", "BIVOLT", "N/A"]
RecommendationType = Literal["PRIMARY", "UPSELL", "CROSS_SELL"]
CompatibilitySource = Literal["CROSS_SELL_RELATION", "COMPLEMENTARY_CATEGORY"]
VOLTAGES: tuple[Voltage, ...] = ("127V", "220V", "BIVOLT", "N/A")
MIN_TIER = 1
MAX_TIER = 5
ZERO = Decimal("0")
ONE = Decimal("1")


class DomainInputError(ValueError):
    """Invalid inputs cannot produce a purchase recommendation."""


def finite_decimal(value: object, field_name: str) -> Decimal:
    if not isinstance(value, Decimal) or not value.is_finite():
        raise DomainInputError(f"{field_name} must be a finite Decimal")
    return value


def require_integer(value: object, field_name: str) -> None:
    if type(value) is not int:
        raise DomainInputError(f"{field_name} must be an integer")


def validate_voltage(voltage: str) -> None:
    if voltage not in VOLTAGES:
        raise DomainInputError("voltage must be a canonical catalog value")


@dataclass(frozen=True)
class Product:
    """SQL snapshot; money is never coerced from float or LLM output."""

    sku: str
    category: str
    subcategory: str
    price: Decimal
    stock_quantity: int
    is_active: bool
    voltage: Voltage
    tier_rank: int
    capacity_liters: Decimal | None = None

    def __post_init__(self) -> None:
        if not self.sku.strip() or not self.category.strip() or not self.subcategory.strip():
            raise DomainInputError("sku, category and subcategory must be nonempty")
        if finite_decimal(self.price, "price") <= ZERO:
            raise DomainInputError("price must be positive")
        require_integer(self.stock_quantity, "stock_quantity")
        require_integer(self.tier_rank, "tier_rank")
        if not MIN_TIER <= self.tier_rank <= MAX_TIER:
            raise DomainInputError("tier_rank must be between 1 and 5")
        if type(self.is_active) is not bool:
            raise DomainInputError("is_active must be a boolean")
        validate_voltage(self.voltage)
        if self.capacity_liters is not None:
            if finite_decimal(self.capacity_liters, "capacity_liters") < ZERO:
                raise DomainInputError("capacity_liters cannot be negative")


@dataclass(frozen=True)
class CompatibilityEvidence:
    """Caller-verified compatibility bound to this ordered SQL SKU pair.

    CROSS_SELL_RELATION means a verified CROSS_SELL row, never an arbitrary
    relation. COMPLEMENTARY_CATEGORY means physical compatibility was proved
    by the adapter, not inferred from similar names or a language model.
    """

    base_sku: str
    candidate_sku: str
    source: CompatibilitySource
    affinity_weight: Decimal | None = None

    def __post_init__(self) -> None:
        if not self.base_sku.strip() or not self.candidate_sku.strip():
            raise DomainInputError("compatibility requires both SKUs")
        if self.source not in ("CROSS_SELL_RELATION", "COMPLEMENTARY_CATEGORY"):
            raise DomainInputError("unsupported compatibility source")
        if self.source == "CROSS_SELL_RELATION" and self.affinity_weight is None:
            raise DomainInputError("explicit relations require affinity_weight")
        if self.affinity_weight is not None:
            weight = finite_decimal(self.affinity_weight, "affinity_weight")
            if not ZERO <= weight <= ONE:
                raise DomainInputError("affinity_weight must be between 0 and 1")


@dataclass(frozen=True)
class RecommendationCandidate:
    """Supplied similarities must come from current active manual chunks.

    No chunks means similarity zero. This value neither retrieves chunks nor
    certifies provenance; RN02/RN03 generation guardrails belong to the caller.
    """

    product: Product
    similarities: tuple[Decimal, ...] = ()
    compatibility: CompatibilityEvidence | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.similarities, tuple):
            raise DomainInputError("similarities must be an immutable tuple")
        for similarity in self.similarities:
            finite_decimal(similarity, "similarity")


@dataclass(frozen=True)
class Recommendation:
    product: Product
    recommendation_type: RecommendationType
    score: Decimal
