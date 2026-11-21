"""Product Cards built only from SQL rows (RN06): no LLM text reaches a card."""

from decimal import ROUND_HALF_UP, Decimal

from app.models.schemas import CatalogProduct, ProductRecommendation
from app.recommendation.models import RecommendationType

PRIMARY_BADGE = "Produto Consultado"
UPSELL_BADGE = "Upgrade Recomendado"
CROSS_SELL_BADGE = "Compre Junto Compatível"
OPTION_BADGE = "Opção"
_BADGES: dict[RecommendationType, str] = {
    "PRIMARY": PRIMARY_BADGE,
    "UPSELL": UPSELL_BADGE,
    "CROSS_SELL": CROSS_SELL_BADGE,
    "OPTION": OPTION_BADGE,
}
_CENT = Decimal("0.01")
_PERCENT = Decimal("100")
UNPOWERED_VOLTAGE = "N/A"
_BRAZILIAN_SEPARATORS = str.maketrans(",.", ".,")  # 1,300.00 -> 1.300,00

ProductCard = dict[str, object]


def brl(amount: Decimal) -> str:
    return f"R$ {amount.quantize(_CENT):,.2f}".translate(_BRAZILIAN_SEPARATORS)


_brl = brl


def _liters(capacity: Decimal) -> str:
    return format(capacity.normalize(), "f").replace(".", ",")


def _voltage_note(product: CatalogProduct) -> str:
    return "" if product.voltage == UNPOWERED_VOLTAGE else f" Voltagem: {product.voltage}."


def primary_justification(product: CatalogProduct) -> str:
    return f"Produto consultado, disponível em estoque.{_voltage_note(product)}"


def upsell_justification(base: CatalogProduct, upsell: CatalogProduct) -> str:
    difference = upsell.price - base.price
    percent = (difference / base.price * _PERCENT).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
    cost = f"por {_brl(difference)} a mais (+{percent}%)."
    if base.capacity_liters is not None and upsell.capacity_liters is not None:
        gain = (
            f"Capacidade de {_liters(upsell.capacity_liters)} L, contra "
            f"{_liters(base.capacity_liters)} L do modelo consultado, "
        )
    else:
        gain = "Linha superior ao modelo consultado, "
    return f"{gain}{cost}{_voltage_note(upsell)}"


def build_card(
    product: CatalogProduct, role: RecommendationType, justification: str
) -> ProductCard:
    """JSON-ready card; PRIMARY ignores the given justification (always the stock template)."""
    return {
        "sku": product.sku,
        "name": product.name,
        "price": float(product.price),
        "stock_quantity": product.stock_quantity,
        "voltage": product.voltage,
        "capacity_liters": (
            float(product.capacity_liters) if product.capacity_liters is not None else None
        ),
        "power_watts": product.power_watts,
        "image_url": product.image_url,
        "marketplace": product.marketplace,
        "checkout_url": product.checkout_url,
        "recommendation_type": role,
        "badge_label": _BADGES[role],
        "justification": primary_justification(product) if role == "PRIMARY" else justification,
    }


def option_facts(option: CatalogProduct | ProductRecommendation) -> list[str]:
    """SQL facts of one product, one attribute per "SKU <code>:" sentence (the G-OUT format)."""
    facts = []
    if option.capacity_liters is not None:
        facts.append(f"Possui capacidade de {_liters(option.capacity_liters)} L.")
    if option.power_watts is not None:
        facts.append(f"A potência é {option.power_watts} W.")
    if option.voltage != UNPOWERED_VOLTAGE:
        facts.append(f"Voltagem: {option.voltage}.")
    facts.append(f"Preço atual: {_brl(option.price)}.")
    return [f"SKU {option.sku}: {fact}" for fact in facts]
