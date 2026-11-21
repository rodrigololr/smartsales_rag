"""Pure deterministic intent routing and comparison set selection (spec §2)."""

import re
from collections.abc import Sequence
from enum import StrEnum

from app.config import CONSULTANT_MAX_OPTIONS
from app.consultant.conversation import ConversationState
from app.consultant.slots import parse_budget, parse_category, parse_game
from app.guardrails.input import is_prompt_injection
from app.guardrails.output import length_measures_cm
from app.models.schemas import CatalogProduct
from app.recommendation.intent import folded

CONSULTANT_CATEGORIES = frozenset({"Computadores", "Monitores", "Móveis"})
_ACCESSORY_PREFIXES = ("KIT-", "MP-", "PT-")

DEICTIC_SET_RE = re.compile(
    r"\b(desses|dessas|destes|destas|esses|essas|estes|estas|eles|elas|todos|todas"
    r"|entre (eles|elas)|cada um|que voce (mandou|mostrou|indicou))\b"
)
VOLTAGE_TOPIC_RE = re.compile(
    r"\b(127|110|220)\s*v?\b|\bbivolt\b|\b(voltagem|tensao|tomada)\b"
)
PRICE_RANK_RE = re.compile(
    r"\bmais (barat[oa]s?|car[oa]s?|em conta|economic[oa]s?)\b|\b(menor|maior) preco\b"
)
BRAND_OPINION_RE = re.compile(
    r"\bmarcas?\b.*\b(confia\w*|melhor|boa|qualidade|durav\w*)\b"
    r"|\b(confia\w*|melhor)\b.*\bmarcas?\b"
)
BEST_RE = re.compile(
    r"\bqua(l|is)\b.*\b(melhor(es)?|recomenda\w*|indica\w*|escolh\w*|compensa)\b"
    r"|\bcompar\w*|\bdiferenca\b"
)
FIT_SPACE_RE = re.compile(r"\b(cabe|caber|cabera|espaco|largura|parede)\b")
PLAY_RE = re.compile(r"\b(jogar|jogo|jogos|roda|rodar|rodaria|aguenta|consigo|da pra)\b")
STREAM_RE = re.compile(r"\b(live|lives|stream\w*|transmi\w*|twitch)\b")
PURCHASE_RE = re.compile(
    r"\b(quero|queria|procuro|procurando|preciso|busco|comprar"
    r"|indica\w*|recomenda\w*|sugere|mostra\w*|opcoes?)\b"
)
GREETING_RE = re.compile(
    r"^\s*(oi|ola|bom dia|boa tarde|boa noite|obrigad[oa]|valeu)\b[\s!.]*$"
)


class Route(StrEnum):
    BLOCKED = "BLOCKED"
    GREETING = "GREETING"
    DIMENSION_FIT = "DIMENSION_FIT"
    STREAM_FIT = "STREAM_FIT"
    GAME_FIT = "GAME_FIT"
    SET_VOLTAGE = "SET_VOLTAGE"
    PRICE_RANK = "PRICE_RANK"
    OPINION_BRAND = "OPINION_BRAND"
    COMPARE = "COMPARE"
    DISCOVERY = "DISCOVERY"
    TECHNICAL = "TECHNICAL"
    KB_QA = "KB_QA"


def route_intent(chosen: Route) -> str:
    if chosen == Route.DISCOVERY:
        return "PURCHASE_INTENT"
    if chosen in {Route.COMPARE, Route.PRICE_RANK, Route.SET_VOLTAGE, Route.OPINION_BRAND}:
        return "PRODUCT_COMPARISON"
    if chosen == Route.GREETING:
        return "OUT_OF_DOMAIN"
    if chosen == Route.BLOCKED:
        return "BLOCKED"
    return "TECHNICAL_QA"


def _filter_shown_products(question: str, shown: Sequence[CatalogProduct]) -> list[CatalogProduct]:
    if not shown:
        return []
    target = parse_category(question)
    if target is not None:
        matched = [
            product
            for product in shown
            if product.category == target.category
            and (not target.subcategories or product.subcategory in target.subcategories)
        ]
        if matched:
            return matched
    first_category = shown[0].category
    return [product for product in shown if product.category == first_category]


def _filter_shown_skus(shown_skus: Sequence[str]) -> tuple[str, ...]:
    if not shown_skus:
        return ()
    if shown_skus[0].startswith(_ACCESSORY_PREFIXES):
        return tuple(shown_skus)
    return tuple(sku for sku in shown_skus if not sku.startswith(_ACCESSORY_PREFIXES))


def comparison_set(
    question: str,
    shown: Sequence[CatalogProduct],
    referent: CatalogProduct | None = None,
    peers: Sequence[CatalogProduct] = (),
) -> list[CatalogProduct]:
    """Filter shown products to a comparable set, falling back to in-stock subcategory peers."""
    filtered = _filter_shown_products(question, shown)
    if len(filtered) >= 2:
        return filtered
    if referent is not None:
        in_stock_peers = sorted(
            (
                peer
                for peer in peers
                if peer.is_active
                and peer.stock_quantity > 0
                and peer.subcategory == referent.subcategory
                and peer.sku != referent.sku
            ),
            key=lambda product: (product.price, product.sku),
        )[:CONSULTANT_MAX_OPTIONS]
        if in_stock_peers:
            combined = [referent, *in_stock_peers][:CONSULTANT_MAX_OPTIONS]
            return sorted(combined, key=lambda product: (product.price, product.sku))
        return [referent]
    return filtered


def _comparison_route(
    normalized: str, shown_count: int, *, allow_referent_price_rank: bool
) -> Route | None:
    if VOLTAGE_TOPIC_RE.search(normalized) and DEICTIC_SET_RE.search(normalized) and shown_count >= 2:
        return Route.SET_VOLTAGE
    if PRICE_RANK_RE.search(normalized) and (shown_count >= 2 or allow_referent_price_rank):
        return Route.PRICE_RANK
    if BRAND_OPINION_RE.search(normalized) and shown_count >= 2:
        return Route.OPINION_BRAND
    if BEST_RE.search(normalized) and (DEICTIC_SET_RE.search(normalized) or shown_count > 0):
        return Route.COMPARE
    return None


def _computers_in_context(
    state: ConversationState,
    current: CatalogProduct | None,
    shown_products: Sequence[CatalogProduct],
) -> bool:
    if current is not None and current.category == "Computadores":
        return True
    if state.slots.category is not None and state.slots.category.category == "Computadores":
        return True
    if any(product.category == "Computadores" for product in shown_products):
        return True
    return any(sku.startswith(("PC-", "NB-")) for sku in state.shown_skus)


def _sofas_target(question: str, state: ConversationState, current: CatalogProduct | None) -> bool:
    if current is not None and current.subcategory == "Sofás":
        return True
    if state.slots.category is not None and "Sofás" in state.slots.category.subcategories:
        return True
    question_cat = parse_category(question)
    return question_cat is not None and "Sofás" in question_cat.subcategories


def route(
    question: str,
    state: ConversationState,
    current: CatalogProduct | None = None,
    *,
    shown_products: Sequence[CatalogProduct] = (),
) -> Route:
    if is_prompt_injection(question):
        return Route.BLOCKED
    normalized = folded(question)
    if GREETING_RE.match(normalized):
        return Route.GREETING

    filtered_shown_count = (
        len(_filter_shown_products(question, shown_products))
        if shown_products
        else len(_filter_shown_skus(state.shown_skus))
    )

    # D3 Legacy guard: product-page turns on legacy categories only allow Webcams STREAM_FIT
    # or comparison routes when the filtered shown set already has >= 2 products.
    if current is not None and current.category not in CONSULTANT_CATEGORIES:
        if current.subcategory == "Webcams" and STREAM_RE.search(normalized):
            return Route.STREAM_FIT
        if filtered_shown_count >= 2:
            comp_route = _comparison_route(
                normalized, filtered_shown_count, allow_referent_price_rank=False
            )
            if comp_route is not None:
                return comp_route
        return Route.TECHNICAL

    has_room_measure = state.slots.room_width_cm is not None or bool(length_measures_cm(question))
    if FIT_SPACE_RE.search(normalized) and (
        has_room_measure or _sofas_target(question, state, current)
    ):
        return Route.DIMENSION_FIT

    if STREAM_RE.search(normalized):
        return Route.STREAM_FIT

    current_game = parse_game(question)
    question_category = parse_category(question)
    if current_game is not None and (
        PLAY_RE.search(normalized)
        or (question_category is not None and question_category.category == "Computadores")
        or _computers_in_context(state, current, shown_products)
    ):
        return Route.GAME_FIT

    has_referent = bool(
        state.mentioned_skus or state.current_sku or current is not None or len(state.shown_skus) == 1
    )
    comp_size = max(filtered_shown_count, 2 if has_referent else 0)
    if VOLTAGE_TOPIC_RE.search(normalized) and DEICTIC_SET_RE.search(normalized) and comp_size >= 2:
        return Route.SET_VOLTAGE
    if PRICE_RANK_RE.search(normalized):
        return Route.PRICE_RANK
    if BRAND_OPINION_RE.search(normalized):
        return Route.OPINION_BRAND
    if BEST_RE.search(normalized) and (DEICTIC_SET_RE.search(normalized) or filtered_shown_count > 0):
        return Route.COMPARE

    if (
        question_category is not None
        or parse_budget(question) is not None
        or (PURCHASE_RE.search(normalized) and state.slots.category is not None)
    ):
        return Route.DISCOVERY

    if has_referent:
        return Route.TECHNICAL

    return Route.KB_QA
