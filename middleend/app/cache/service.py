"""Semantic cache of approved answers (M03, RN09) with stock/price revalidation (RN01).

The key is the exact hash of build_cache_key under the current catalog:version, so a
catalog change makes every older entry unreachable. A hit is served only after the
consulted product (whose price and availability are in the answer text) and the cards
are checked against PostgreSQL at this instant: any of them sold out, inactive or
repriced turns the hit into a miss and the entry is dropped.
Storage failures never break a chat turn: they are logged and count as a miss.
"""

import json
import logging
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from decimal import Decimal
from typing import Protocol, cast

from app.cache.identity import build_cache_key
from app.sse.models import Citation, CompletedTurn, ProductCard

logger = logging.getLogger(__name__)
CATALOG_VERSION_PREFIX = "v"


class CacheUnavailableError(Exception):
    """Redis or PostgreSQL could not be reached for a cache operation."""


@dataclass(frozen=True)
class ProductSnapshot:
    """Current SQL facts of a product, read when a cached card is about to be served."""

    price: Decimal
    stock_quantity: int
    is_active: bool


@dataclass(frozen=True)
class CachedAnswer:
    answer_text: str
    citations: tuple[Citation, ...]
    recommendations: tuple[ProductCard, ...]
    tokens_used: int
    intent: str | None


class CacheStorage(Protocol):
    async def catalog_version(self) -> int: ...

    async def get(self, key: str) -> str | None: ...

    async def set(self, key: str, value: str, ttl_seconds: int) -> None: ...

    async def delete(self, key: str) -> None: ...


class ProductSnapshotReader(Protocol):
    async def current(self, skus: Sequence[str]) -> dict[str, ProductSnapshot]: ...


@dataclass(frozen=True)
class ConsultedProduct:
    """SQL facts of the consulted product the cached text was generated from."""

    sku: str
    price: Decimal
    in_stock: bool

    def unchanged(self, snapshot: ProductSnapshot | None) -> bool:
        return (
            snapshot is not None
            and snapshot.is_active
            and snapshot.price == self.price
            and (snapshot.stock_quantity > 0) == self.in_stock
        )


def _serialize(turn: CompletedTurn, consulted: ConsultedProduct) -> str:
    return json.dumps(
        {
            "answer_text": turn.content,
            "citations": list(turn.citations),
            "recommendations": list(turn.products),
            "tokens_used": turn.tokens_used,
            "intent": turn.intent,
            "consulted": {
                "sku": consulted.sku,
                "price": str(consulted.price),
                "in_stock": consulted.in_stock,
            },
        },
        ensure_ascii=False,
    )


def _deserialize(raw: str) -> tuple[CachedAnswer, ConsultedProduct]:
    entry = json.loads(raw)
    consulted = entry["consulted"]
    return (
        CachedAnswer(
            answer_text=entry["answer_text"],
            citations=tuple(entry["citations"]),
            recommendations=tuple(entry["recommendations"]),
            tokens_used=entry["tokens_used"],
            intent=entry["intent"],
        ),
        ConsultedProduct(consulted["sku"], Decimal(consulted["price"]), consulted["in_stock"]),
    )


def _still_valid(card: ProductCard, snapshot: ProductSnapshot | None) -> bool:
    return (
        snapshot is not None
        and snapshot.is_active
        and snapshot.stock_quantity > 0
        and snapshot.price == Decimal(str(card["price"]))
    )


class SemanticCacheService:
    def __init__(
        self,
        storage: CacheStorage,
        products: ProductSnapshotReader,
        *,
        ttl_seconds: int,
        policy_version: str,
    ) -> None:
        self._storage = storage
        self._products = products
        self._ttl_seconds = ttl_seconds
        self._policy_version = policy_version

    async def key_for(
        self,
        query: str,
        resolved_filters: Mapping[str, object],
        history: Sequence[Mapping[str, str]],
    ) -> str | None:
        """Key of this turn under the current catalog:version; None when Redis is down."""
        try:
            version = await self._storage.catalog_version()
        except CacheUnavailableError:
            logger.exception("cache_version_unavailable")
            return None
        return build_cache_key(
            f"{CATALOG_VERSION_PREFIX}{version}",
            query,
            resolved_filters,
            history,
            self._policy_version,
        )

    async def lookup(self, key: str) -> CachedAnswer | None:
        """A cached answer whose consulted product and cards still match SQL, or None."""
        try:
            raw = await self._storage.get(key)
            if raw is None:
                return None
            try:
                cached, consulted = _deserialize(raw)
            except (ValueError, KeyError, TypeError, ArithmeticError):
                # Written in another format (older deploy) or corrupted: never a 500.
                logger.exception("cache_entry_unreadable", extra={"cache_key": key})
                await self._storage.delete(key)
                return None
            revalidated = await self._revalidated_cards(consulted, cached.recommendations)
            if revalidated is None:
                await self._storage.delete(key)
                return None
        except CacheUnavailableError:
            logger.exception("cache_lookup_failed", extra={"cache_key": key})
            return None
        return CachedAnswer(
            cached.answer_text, cached.citations, revalidated, cached.tokens_used, cached.intent
        )

    async def store(self, key: str, turn: CompletedTurn, consulted_sku: str) -> None:
        """Cache an answered turn; fallbacks and cache hits are never (re)stored."""
        if turn.finish_reason != "stop" or turn.cache_hit:
            return
        try:
            snapshot = (await self._products.current([consulted_sku])).get(consulted_sku)
            if snapshot is None or not snapshot.is_active:
                return  # nothing to revalidate the text against later
            consulted = ConsultedProduct(
                consulted_sku, snapshot.price, snapshot.stock_quantity > 0
            )
            await self._storage.set(key, _serialize(turn, consulted), self._ttl_seconds)
        except CacheUnavailableError:
            logger.exception("cache_store_failed", extra={"cache_key": key})

    async def _revalidated_cards(
        self, consulted: ConsultedProduct, cards: Sequence[ProductCard]
    ) -> tuple[ProductCard, ...] | None:
        """Cards with the stock of this instant; None if the consulted product changed
        or any card may no longer be offered. One SQL read covers both."""
        current = await self._products.current([consulted.sku, *(c["sku"] for c in cards)])
        if not consulted.unchanged(current.get(consulted.sku)):
            return None
        if not all(_still_valid(card, current.get(card["sku"])) for card in cards):
            return None
        return tuple(
            cast(ProductCard, {**card, "stock_quantity": current[card["sku"]].stock_quantity})
            for card in cards
        )
