"""Semantic cache of approved answers (M03, RN09) with stock/price revalidation (RN01).

The key is the exact hash of build_cache_key under the current catalog:version, so a
catalog change makes every older entry unreachable. A hit is served only after its
cards are checked against PostgreSQL at this instant: a card that is sold out,
inactive or repriced turns the hit into a miss and the entry is dropped.
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


def _serialize(turn: CompletedTurn) -> str:
    return json.dumps(
        {
            "answer_text": turn.content,
            "citations": list(turn.citations),
            "recommendations": list(turn.products),
            "tokens_used": turn.tokens_used,
            "intent": turn.intent,
        },
        ensure_ascii=False,
    )


def _deserialize(raw: str) -> CachedAnswer:
    entry = json.loads(raw)
    return CachedAnswer(
        answer_text=entry["answer_text"],
        citations=tuple(entry["citations"]),
        recommendations=tuple(entry["recommendations"]),
        tokens_used=entry["tokens_used"],
        intent=entry["intent"],
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
        """A cached answer whose cards are still in stock at the cached price, or None."""
        try:
            raw = await self._storage.get(key)
            if raw is None:
                return None
            cached = _deserialize(raw)
            revalidated = await self._revalidated_cards(cached.recommendations)
            if revalidated is None:
                await self._storage.delete(key)
                return None
        except CacheUnavailableError:
            logger.exception("cache_lookup_failed", extra={"cache_key": key})
            return None
        return CachedAnswer(
            cached.answer_text, cached.citations, revalidated, cached.tokens_used, cached.intent
        )

    async def store(self, key: str, turn: CompletedTurn) -> None:
        """Cache an answered turn; fallbacks and cache hits are never (re)stored."""
        if turn.finish_reason != "stop" or turn.cache_hit:
            return
        try:
            await self._storage.set(key, _serialize(turn), self._ttl_seconds)
        except CacheUnavailableError:
            logger.exception("cache_store_failed", extra={"cache_key": key})

    async def _revalidated_cards(
        self, cards: Sequence[ProductCard]
    ) -> tuple[ProductCard, ...] | None:
        """Cards with the stock of this instant; None if any card may no longer be offered."""
        if not cards:
            return ()
        current = await self._products.current([card["sku"] for card in cards])
        if not all(_still_valid(card, current.get(card["sku"])) for card in cards):
            return None
        return tuple(
            cast(ProductCard, {**card, "stock_quantity": current[card["sku"]].stock_quantity})
            for card in cards
        )
