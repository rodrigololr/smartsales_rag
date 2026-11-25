"""Pure multi-turn conversation state derivation (spec §1)."""

from collections.abc import Sequence
from dataclasses import dataclass
from decimal import Decimal
from typing import Literal

from app.consultant.slots import (
    CategoryTarget,
    Slots,
    parse_category,
    parse_skus,
    parse_slots,
)
from app.models.schemas import ConsultantRequest

__all__ = [
    "CategoryTarget",
    "ConversationState",
    "Slots",
    "conversation_state",
    "merge_slots",
]

MAX_SHOWN_SKUS = 6


@dataclass(frozen=True)
class ConversationState:
    current_sku: str | None
    shown_skus: tuple[str, ...]
    mentioned_skus: tuple[str, ...]
    slots: Slots


def merge_slots(
    user_messages: Sequence[str | Slots],
    *,
    preferred_voltage: Literal["127V", "220V"] | None = None,
    budget_max: Decimal | None = None,
    category: str | None = None,
) -> Slots:
    """Merge slots newest-first; stop at the first older message naming a different category."""
    merged_category: CategoryTarget | None = None
    merged_budget: Decimal | None = None
    merged_voltage: Literal["127V", "220V"] | None = None
    merged_game: str | None = None
    merged_seats: int | None = None
    room_width_cm: Decimal | None = None

    for index, item in enumerate(reversed(user_messages)):
        is_current = index == 0
        current = (
            item
            if isinstance(item, Slots)
            else parse_slots(item, include_room_width=is_current)
        )
        if is_current:
            room_width_cm = current.room_width_cm
        if (
            merged_category is not None
            and current.category is not None
            and current.category.category != merged_category.category
        ):
            break
        if merged_category is None and current.category is not None:
            merged_category = current.category
        if merged_budget is None and current.budget_max is not None:
            merged_budget = current.budget_max
        if merged_voltage is None and current.voltage is not None:
            merged_voltage = current.voltage
        if merged_game is None and current.game is not None:
            merged_game = current.game
        if merged_seats is None and current.seats is not None:
            merged_seats = current.seats

    if category is not None:
        parsed_cat = parse_category(category)
        if parsed_cat is not None:
            if merged_category is None or merged_category.category != parsed_cat.category:
                merged_category = parsed_cat
        elif merged_category is None or merged_category.category != category:
            merged_category = CategoryTarget(category, ())
    if budget_max is not None:
        merged_budget = budget_max
    if preferred_voltage is not None:
        merged_voltage = preferred_voltage

    return Slots(
        category=merged_category,
        budget_max=merged_budget,
        voltage=merged_voltage,
        game=merged_game,
        seats=merged_seats,
        room_width_cm=room_width_cm,
    )


def _last_shown_skus(request: ConsultantRequest) -> tuple[str, ...]:
    for turn in reversed(request.history):
        if turn.role == "assistant" and turn.recommended_skus:
            unique = list(dict.fromkeys(turn.recommended_skus))
            return tuple(unique[:MAX_SHOWN_SKUS])
    return ()


def conversation_state(request: ConsultantRequest) -> ConversationState:
    user_messages = [
        *(turn.content for turn in request.history if turn.role == "user"),
        request.question,
    ]
    slots = merge_slots(
        user_messages,
        preferred_voltage=request.preferred_voltage,
        budget_max=request.budget_max,
        category=request.category,
    )
    return ConversationState(
        current_sku=request.sku,
        shown_skus=_last_shown_skus(request),
        mentioned_skus=parse_skus(request.question),
        slots=slots,
    )
