"""Seed of product_relations (RN05): validated against the catalog before any write."""

from collections.abc import Collection
from pathlib import Path

from pydantic import TypeAdapter

from app.models.schemas import ProductRelation


def load_relations(path: Path, catalog_skus: Collection[str]) -> list[ProductRelation]:
    """Relations from the seed file; a missing file means the catalog has none."""
    if not path.is_file():
        return []
    relations = TypeAdapter(list[ProductRelation]).validate_json(path.read_bytes())
    seen: set[tuple[str, str, str]] = set()
    for relation in relations:
        _require_catalog_pair(relation, catalog_skus)
        identity = (relation.base_sku, relation.related_sku, relation.relation_type)
        if identity in seen:
            raise ValueError(f"Relação duplicada no seed: {identity}")
        seen.add(identity)
    return relations


def _require_catalog_pair(relation: ProductRelation, catalog_skus: Collection[str]) -> None:
    for sku in (relation.base_sku, relation.related_sku):
        if sku not in catalog_skus:
            raise ValueError(f"Relação cita SKU ausente do catálogo: {sku}")
    if relation.base_sku == relation.related_sku:
        raise ValueError(f"Relação de um produto com ele mesmo: {relation.base_sku}")
