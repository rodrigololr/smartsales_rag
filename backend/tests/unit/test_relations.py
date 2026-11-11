"""B01: product_relations seed validation (RN05 cross-sell source of truth)."""

import json
from decimal import Decimal
from pathlib import Path

import pytest
from app.ingestion.relations import load_relations
from app.models.schemas import ProductRelation
from pydantic import ValidationError

DATA_DIR = Path(__file__).resolve().parents[3] / "data"
CATALOG_SKUS = {"AF-400-220V", "KIT-SIL-01"}


def relation(**overrides: object) -> dict[str, object]:
    fields: dict[str, object] = {
        "base_sku": "AF-400-220V",
        "related_sku": "KIT-SIL-01",
        "relation_type": "CROSS_SELL",
        "affinity_weight": "0.950",
        "justification_template": "Formas de silicone compatíveis com o cesto de 4L.",
    }
    fields.update(overrides)
    return fields


def write_seed(tmp_path: Path, rows: list[dict[str, object]]) -> Path:
    seed = tmp_path / "product_relations.json"
    seed.write_text(json.dumps(rows), encoding="utf-8")
    return seed


def test_relation_keeps_exact_decimal_weight() -> None:
    parsed = ProductRelation.model_validate(relation())
    assert parsed.affinity_weight == Decimal("0.950")


@pytest.mark.parametrize(
    "change",
    [
        {"relation_type": "BUNDLE"},
        {"affinity_weight": "1.001"},
        {"affinity_weight": "-0.1"},
        {"justification_template": ""},
        {"unexpected": "x"},
    ],
)
def test_relation_rejects_values_outside_the_ddl_checks(change: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        ProductRelation.model_validate(relation(**change))


def test_load_relations_reads_the_seed(tmp_path: Path) -> None:
    [loaded] = load_relations(write_seed(tmp_path, [relation()]), CATALOG_SKUS)
    assert (loaded.base_sku, loaded.related_sku) == ("AF-400-220V", "KIT-SIL-01")


def test_load_relations_rejects_sku_missing_from_the_catalog(tmp_path: Path) -> None:
    seed = write_seed(tmp_path, [relation(related_sku="KIT-FANTASMA")])
    with pytest.raises(ValueError, match="KIT-FANTASMA"):
        load_relations(seed, CATALOG_SKUS)


def test_load_relations_rejects_self_relation(tmp_path: Path) -> None:
    seed = write_seed(tmp_path, [relation(related_sku="AF-400-220V")])
    with pytest.raises(ValueError, match="AF-400-220V"):
        load_relations(seed, CATALOG_SKUS)


def test_load_relations_rejects_duplicate_pair_and_type(tmp_path: Path) -> None:
    seed = write_seed(tmp_path, [relation(), relation(affinity_weight="0.500")])
    with pytest.raises(ValueError, match="duplicada"):
        load_relations(seed, CATALOG_SKUS)


def test_missing_seed_file_means_no_relations(tmp_path: Path) -> None:
    assert load_relations(tmp_path / "ausente.json", CATALOG_SKUS) == []


def test_repository_seed_references_only_catalog_skus() -> None:
    catalog = json.loads((DATA_DIR / "catalog.json").read_text(encoding="utf-8"))
    skus = {row["sku"] for row in catalog}
    relations = load_relations(DATA_DIR / "product_relations.json", skus)
    assert ("AF-400-220V", "KIT-SIL-01", "CROSS_SELL") in {
        (r.base_sku, r.related_sku, r.relation_type) for r in relations
    }
