"""Idempotent replay revalidates stored cards against the current catalog (R09)."""

import asyncio
from decimal import Decimal
from typing import Any, cast

import pytest
from app.sessions.replay import STALE_MESSAGE, validated_replay
from app.sse.models import CompletedTurn, ProductCard

CARD: ProductCard = {
    "sku": "AF-400-220V",
    "name": "Airfryer SmartChef 4L",
    "price": 649.9,
    "stock_quantity": 12,
    "voltage": "220V",
    "capacity_liters": 4.0,
    "power_watts": 1500,
    "image_url": "https://img.test/af.png",
    "marketplace": "AMAZON",
    "checkout_url": "https://amazon.test/af",
    "recommendation_type": "PRIMARY",
    "badge_label": "Consultado",
    "justification": "Produto consultado.",
}


def _row(**changes: object) -> dict[str, object]:
    row: dict[str, object] = {
        **CARD,
        "price": Decimal("649.90"),
        "capacity_liters": Decimal("4.0"),
        "is_active": True,
    }
    return {**row, **changes}


class _Connection:
    def __init__(self, row: dict[str, object]) -> None:
        self._row = row

    async def execute(self, sql: str, params: object) -> "_Connection":
        return self

    async def fetchall(self) -> list[dict[str, object]]:
        return [self._row]


def _replay(row: dict[str, object]) -> CompletedTurn:
    turn = CompletedTurn(
        "session", "message", "Opera em 220V.", (), (CARD,), "stop", 7, "TECHNICAL_QA",
        False, 5, 10,
    )
    return asyncio.run(validated_replay(cast(Any, _Connection(row)), turn))


def test_replay_survives_a_purchase_and_shows_the_current_stock() -> None:
    replayed = _replay(_row(stock_quantity=11))
    assert replayed.finish_reason == "stop" and replayed.content == "Opera em 220V."
    assert replayed.products[0]["stock_quantity"] == 11


@pytest.mark.parametrize(
    "changes",
    [{"stock_quantity": 0}, {"price": Decimal("699.90")}, {"is_active": False}],
)
def test_replay_is_stale_when_the_offer_can_no_longer_be_made(changes: dict[str, object]) -> None:
    replayed = _replay(_row(**changes))
    assert replayed.finish_reason == "error" and replayed.content == STALE_MESSAGE
    assert replayed.products == ()
