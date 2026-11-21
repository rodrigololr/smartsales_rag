"""IT-M04-01: GET /api/v1/metrics/summary against a real PostgreSQL and Redis."""

import asyncio
from datetime import UTC, datetime, timedelta

import httpx
import psycopg
import pytest
from test_commerce_contract import (  # noqa: F401 - database_url is a fixture
    assert_contract,
    client_for,
    database_url,
    new_turn,
)

ADMIN_TOKEN = "segredo-do-operador"
ADMIN = {"X-Admin-Token": ADMIN_TOKEN}
PATH = "/metrics/summary"


def test_it_m04_01_metrics_summary_aggregates_the_window(database_url: str) -> None:  # noqa: F811
    async def scenario() -> None:
        async with client_for(
            database_url, decrement_stock=False, admin_token=ADMIN_TOKEN
        ) as client:
            requests: list[httpx.Request] = []

            async def count(request: httpx.Request) -> None:
                requests.append(request)

            client.event_hooks = {"request": [count], "response": []}
            turns = [await new_turn(client) for _ in range(10)]
            with psycopg.connect(database_url) as connection:
                for position, turn in enumerate(turns, start=1):
                    connection.execute(
                        """
                        UPDATE chat_messages SET ttft_ms = %s, total_latency_ms = %s,
                            cache_hit = %s, recommended_skus = %s::jsonb
                        WHERE id = %s
                        """,
                        (
                            100 * position,
                            1000 * position,
                            position <= 3,
                            '["KIT"]' if position <= 4 else "[]",
                            turn["message_id"],
                        ),
                    )
            for turn in turns[:3]:
                await client.post("feedback", json={**turn, "rating": "LIKE"})
            await client.post(
                "feedback", json={**turns[3], "rating": "DISLIKE", "reason_category": "SLOW"}
            )
            checkout = {"sku": "KIT", "quantity": 1, "recommendation_type": "CROSS_SELL"}
            for turn in turns[:2]:
                confirmed = await client.post(
                    "checkout/mock", json={**turn, **checkout, "displayed_price": 50}
                )
                assert confirmed.status_code == 200
            stale = await client.post(
                "checkout/mock", json={**turns[2], **checkout, "displayed_price": 40}
            )
            assert stale.status_code == 409
            with psycopg.connect(database_url, autocommit=True) as connection:
                connection.execute("ALTER TABLE products RENAME TO products_offline")
                assert (await client.get("products")).status_code == 503
                connection.execute("ALTER TABLE products_offline RENAME TO products")

            assert_contract(await client.get(PATH), PATH, 401)
            assert_contract(await client.get(PATH, headers={"X-Admin-Token": "x"}), PATH, 401)
            requests_before_summary = len(requests)
            metrics = assert_contract(await client.get(PATH, headers=ADMIN), PATH, 200)

        assert metrics["turns"] == 10
        assert metrics["like_ratio"] == 0.75
        assert metrics["confirmed_checkouts"] == 2
        assert metrics["ttft_p50_ms"] == 550
        assert metrics["ttft_p95_ms"] == pytest.approx(955)
        assert metrics["total_latency_p95_ms"] == pytest.approx(9550)
        assert metrics["cache_hit_ratio"] == pytest.approx(0.3)
        # 3 of the 4 answers with cards got a checkout click (2 confirmed + 1 price changed).
        assert metrics["card_ctr"] == 0.75
        assert metrics["error_5xx_rate"] == pytest.approx(1 / requests_before_summary)
        assert metrics["top_questions"] == [{"question": "qual a voltagem?", "count": 10}]
        window_from = datetime.fromisoformat(metrics["window"]["from"])
        window_to = datetime.fromisoformat(metrics["window"]["to"])
        assert window_to - window_from == timedelta(days=7)
        assert abs(datetime.now(UTC) - window_to) < timedelta(minutes=1)

    asyncio.run(scenario())


def test_metrics_summary_on_empty_database_returns_zeros(database_url: str) -> None:  # noqa: F811
    async def scenario() -> None:
        async with client_for(database_url, admin_token=ADMIN_TOKEN) as client:
            metrics = assert_contract(await client.get(PATH, headers=ADMIN), PATH, 200)
        assert {key: value for key, value in metrics.items() if key != "window"} == {
            "turns": 0,
            "ttft_p50_ms": 0,
            "ttft_p95_ms": 0,
            "total_latency_p95_ms": 0,
            "cache_hit_ratio": 0,
            "error_5xx_rate": 0,
            "like_ratio": 0,
            "card_ctr": 0,
            "confirmed_checkouts": 0,
            "top_questions": [],
        }

    asyncio.run(scenario())


def test_metrics_summary_honours_and_validates_the_requested_window(
    database_url: str,  # noqa: F811
) -> None:
    async def scenario() -> None:
        async with client_for(database_url, admin_token=ADMIN_TOKEN) as client:
            await new_turn(client)
            past = {"from": "2000-01-01T00:00:00Z", "to": "2000-01-02T00:00:00Z"}
            metrics = assert_contract(await client.get(PATH, headers=ADMIN, params=past), PATH, 200)
            assert metrics["turns"] == 0
            assert datetime.fromisoformat(metrics["window"]["from"]) == datetime(
                2000, 1, 1, tzinfo=UTC
            )
            current = assert_contract(
                await client.get(PATH, headers=ADMIN, params={"from": "2000-01-01T00:00:00Z"}),
                PATH,
                200,
            )
            assert current["turns"] == 1
            for invalid in (
                {"from": past["to"], "to": past["from"]},
                {"from": "2000-01-01T00:00:00"},  # no offset
                {"to": "ontem"},
            ):
                assert_contract(await client.get(PATH, headers=ADMIN, params=invalid), PATH, 422)

    asyncio.run(scenario())


def test_metrics_summary_is_closed_when_admin_token_is_not_configured(
    database_url: str,  # noqa: F811
) -> None:
    async def scenario() -> None:
        async with client_for(database_url, admin_token="") as client:
            for headers in ({}, {"X-Admin-Token": ""}, ADMIN):
                assert_contract(await client.get(PATH, headers=headers), PATH, 401)

    asyncio.run(scenario())
