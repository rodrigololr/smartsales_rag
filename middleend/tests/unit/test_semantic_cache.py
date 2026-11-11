"""UT-M03-02 and the cache-hit revalidation of stock and price (RN01, RN09)."""

import asyncio
from collections.abc import Sequence
from decimal import Decimal
from typing import cast

import pytest
from app.cache.service import (
    CachedAnswer,
    CacheUnavailableError,
    ProductSnapshot,
    SemanticCacheService,
)
from app.sse.models import CompletedTurn, ProductCard

QUESTION = "A airfryer 4L é 220V?"
FILTERS = {"current_product_sku": "AF-400-220V"}
UPSELL_CARD = cast(
    ProductCard,
    {
        "sku": "AF-550-220V",
        "name": "Airfryer SmartChef 5.5L Family",
        "price": 629.9,
        "stock_quantity": 8,
        "voltage": "220V",
        "capacity_liters": 5.5,
        "power_watts": 1900,
        "image_url": "/images/airfryer-55l.svg",
        "marketplace": "AMAZON",
        "checkout_url": "https://example.com/af-550",
        "recommendation_type": "UPSELL",
        "badge_label": "Upgrade Recomendado",
        "justification": "Capacidade de 5,5 L.",
    },
)
IN_STOCK = ProductSnapshot(Decimal("629.90"), 3, True)


class FakeStorage:
    def __init__(self) -> None:
        self.version = 10
        self.entries: dict[str, str] = {}
        self.ttls: dict[str, int] = {}
        self.failure: Exception | None = None

    async def catalog_version(self) -> int:
        self._raise()
        return self.version

    async def get(self, key: str) -> str | None:
        self._raise()
        return self.entries.get(key)

    async def set(self, key: str, value: str, ttl_seconds: int) -> None:
        self._raise()
        self.entries[key] = value
        self.ttls[key] = ttl_seconds

    async def delete(self, key: str) -> None:
        self.entries.pop(key, None)

    def _raise(self) -> None:
        if self.failure:
            raise self.failure


class FakeProducts:
    def __init__(self, snapshots: dict[str, ProductSnapshot] | None = None) -> None:
        self.snapshots = snapshots if snapshots is not None else {"AF-550-220V": IN_STOCK}
        self.asked: list[list[str]] = []
        self.failure: Exception | None = None

    async def current(self, skus: Sequence[str]) -> dict[str, ProductSnapshot]:
        if self.failure:
            raise self.failure
        self.asked.append(list(skus))
        return {sku: self.snapshots[sku] for sku in skus if sku in self.snapshots}


def answered(
    products: tuple[ProductCard, ...] = (UPSELL_CARD,),
    *,
    finish_reason: str = "stop",
    cache_hit: bool = False,
) -> CompletedTurn:
    return CompletedTurn(
        session_id="s",
        message_id="m",
        content="Opera em 220V.",
        citations=(),
        products=products,
        finish_reason=finish_reason,  # type: ignore[arg-type]
        tokens_used=12,
        intent="TECHNICAL_QA",
        cache_hit=cache_hit,
        ttft_ms=900,
        total_latency_ms=2000,
    )


def service(storage: FakeStorage, products: FakeProducts) -> SemanticCacheService:
    return SemanticCacheService(storage, products, ttl_seconds=3600, policy_version="p1")


def key(cache: SemanticCacheService, question: str = QUESTION) -> str:
    found = asyncio.run(cache.key_for(question, FILTERS, []))
    assert found is not None
    return found


def stored(storage: FakeStorage, products: FakeProducts, turn: CompletedTurn | None = None) -> str:
    cache = service(storage, products)
    cache_key = key(cache)
    asyncio.run(cache.store(cache_key, turn or answered()))
    return cache_key


def lookup(storage: FakeStorage, products: FakeProducts, cache_key: str) -> CachedAnswer | None:
    return asyncio.run(service(storage, products).lookup(cache_key))


def test_equivalent_questions_hit_the_same_entry_with_the_spec_ttl() -> None:
    storage, products = FakeStorage(), FakeProducts()
    cache_key = stored(storage, products)

    assert cache_key.startswith("cache:sem:v10:") and storage.ttls[cache_key] == 3600
    assert key(service(storage, products), "  A airfryer 4L  é 220V? ") == cache_key
    hit = lookup(storage, products, cache_key)
    assert hit is not None and hit.answer_text == "Opera em 220V." and hit.tokens_used == 12


def test_ut_m03_02_new_catalog_version_is_an_immediate_miss() -> None:
    storage, products = FakeStorage(), FakeProducts()
    old_key = stored(storage, products)

    storage.version = 11
    new_key = key(service(storage, products))
    assert new_key.startswith("cache:sem:v11:") and new_key != old_key
    assert lookup(storage, products, new_key) is None


def test_hit_serves_the_stock_of_this_instant() -> None:
    storage, products = FakeStorage(), FakeProducts()
    hit = lookup(storage, products, stored(storage, products))
    assert hit is not None and products.asked == [["AF-550-220V"]]
    assert hit.recommendations[0]["stock_quantity"] == 3  # cached card said 8
    assert hit.recommendations[0]["price"] == 629.9


@pytest.mark.parametrize(
    "snapshot",
    [
        ProductSnapshot(Decimal("629.90"), 0, True),  # sold out
        ProductSnapshot(Decimal("629.90"), 3, False),  # removed from the catalog
        ProductSnapshot(Decimal("649.90"), 3, True),  # repriced
        None,  # row gone
    ],
)
def test_card_that_may_no_longer_be_offered_turns_the_hit_into_a_miss(
    snapshot: ProductSnapshot | None,
) -> None:
    storage = FakeStorage()
    cache_key = stored(storage, FakeProducts())
    stale = FakeProducts({"AF-550-220V": snapshot} if snapshot else {})

    assert lookup(storage, stale, cache_key) is None
    assert cache_key not in storage.entries  # dropped: the next turn regenerates it


def test_answer_without_cards_needs_no_sql_revalidation() -> None:
    storage, products = FakeStorage(), FakeProducts()
    cache_key = stored(storage, products, answered(products=()))
    hit = lookup(storage, products, cache_key)
    assert hit is not None and hit.recommendations == () and products.asked == []


def test_fallbacks_and_cache_hits_are_never_stored() -> None:
    storage, products = FakeStorage(), FakeProducts()
    stored(storage, products, answered(finish_reason="fallback"))
    stored(storage, products, answered(cache_hit=True))
    assert storage.entries == {}


def test_redis_outage_is_a_miss_and_never_an_exception() -> None:
    storage, products = FakeStorage(), FakeProducts()
    cache = service(storage, products)
    cache_key = stored(storage, products)

    storage.failure = CacheUnavailableError("redis down")
    assert asyncio.run(cache.key_for(QUESTION, FILTERS, [])) is None
    assert asyncio.run(cache.lookup(cache_key)) is None
    asyncio.run(cache.store(cache_key, answered()))


def test_database_outage_during_revalidation_is_a_miss() -> None:
    storage, products = FakeStorage(), FakeProducts()
    cache_key = stored(storage, products)
    products.failure = CacheUnavailableError("postgres down")
    assert lookup(storage, products, cache_key) is None
    assert cache_key in storage.entries  # not proven stale: kept for the next lookup
