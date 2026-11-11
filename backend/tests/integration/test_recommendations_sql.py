"""IT-B04-01: recommendations read from real SQL (products + product_relations)."""

import asyncio
import json
from pathlib import Path

import psycopg
import pytest
from app.config import Settings
from app.db.repository import PostgresCatalog
from app.ingestion.run import ingest
from app.recommendation.service import RecommendationLookupError, RecommendationService
from ingestion_support import DATA_DIR, DATABASE_URL, HashingEmbedder, reset_backend_tables

pytestmark = pytest.mark.skipif(not DATABASE_URL, reason="TEST_DATABASE_URL not set")

SOLD_OUT_6L = {
    "sku": "AF-600-220V",
    "name": "Airfryer SmartChef 6L",
    "category": "Eletroportáteis",
    "subcategory": "Fritadeiras Elétricas",
    "brand": "SmartChef",
    "price": "599.90",
    "stock_quantity": 0,
    "voltage": "220V",
    "capacity_liters": "6.0",
    "power_watts": 1700,
    "tier_rank": 2,
    "image_url": "/images/airfryer-6l.svg",
    "checkout_url": "https://example.com/af-600",
}


def _seed(tmp_path: Path) -> HashingEmbedder:
    """Gherkin scenario 2: 4L base, 5.5L, a pricier 8L, a sold-out 6L and the silicone kit."""
    asyncio.run(reset_backend_tables())
    rows = json.loads((DATA_DIR / "catalog.json").read_text(encoding="utf-8"))
    catalog_path = tmp_path / "catalog.json"
    catalog_path.write_text(json.dumps([*rows, SOLD_OUT_6L]), encoding="utf-8")
    embedder = HashingEmbedder()
    asyncio.run(
        ingest(
            DATABASE_URL,
            catalog_path,
            DATA_DIR / "manuals",
            embedder,
            Settings(),
            relations_path=DATA_DIR / "product_relations.json",
        )
    )
    return embedder


def _cards(embedder: HashingEmbedder, sku: str = "AF-400-220V") -> list[dict[str, object]]:
    async def scenario() -> list[dict[str, object]]:
        catalog = PostgresCatalog(DATABASE_URL)
        base = await catalog.get_product(sku)
        assert base is not None
        [query] = await embedder.embed(["A airfryer de 4L atende uma família de 5 pessoas?"])
        return await RecommendationService(catalog).cards(
            base, query_embedding=query, allow_upsell=True
        )

    return asyncio.run(scenario())


def test_it_b04_01_primary_upsell_and_cross_sell_from_sql(tmp_path: Path) -> None:
    found = _cards(_seed(tmp_path))

    assert [(card["recommendation_type"], card["sku"]) for card in found] == [
        ("PRIMARY", "AF-400-220V"),
        ("UPSELL", "AF-550-220V"),  # AF-800 is above +35%, AF-600 is sold out
        ("CROSS_SELL", "KIT-SIL-01"),
    ]
    assert [card["price"] for card in found] == [499.9, 629.9, 79.9]
    assert all(int(str(card["stock_quantity"])) > 0 for card in found)


def test_cards_follow_the_stock_of_this_instant(tmp_path: Path) -> None:
    embedder = _seed(tmp_path)

    async def sell_out(sku: str) -> None:
        async with await psycopg.AsyncConnection.connect(DATABASE_URL, autocommit=True) as conn:
            await conn.execute("UPDATE products SET stock_quantity = 0 WHERE sku = %s", (sku,))

    asyncio.run(sell_out("AF-550-220V"))
    asyncio.run(sell_out("KIT-SIL-01"))
    assert [card["sku"] for card in _cards(embedder)] == ["AF-400-220V"]


def test_database_failure_is_a_lookup_error_and_the_service_returns_no_cards() -> None:
    unreachable = PostgresCatalog(
        "postgresql://smartsales:smartsales@127.0.0.1:1/none?connect_timeout=2"
    )

    async def scenario() -> list[dict[str, object]]:
        with pytest.raises(RecommendationLookupError):
            await unreachable.cross_sell_relations("AF-400-220V")
        base = await PostgresCatalog(DATABASE_URL).get_product("AF-400-220V")
        assert base is not None
        return await RecommendationService(unreachable).cards(
            base, query_embedding=None, allow_upsell=True
        )

    assert asyncio.run(scenario()) == []
