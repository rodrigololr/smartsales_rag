"""B01/B04: the demo seed (data/) loads through the real models and feeds the real engine."""

import re
from decimal import Decimal
from pathlib import Path

import pytest
from app.guardrails.output import technical_claims
from app.guardrails.publication import SentenceVerifier
from app.ingestion.manuals import find_manual, read_manual_pages
from app.ingestion.relations import load_relations
from app.ingestion.run import load_catalog
from app.models.schemas import CatalogProduct
from app.recommendation.engine import RecommendationEngine
from app.recommendation.models import CompatibilityEvidence, RecommendationCandidate
from app.recommendation.service import _engine_product

ROOT = Path(__file__).resolve().parents[3]
DATA_DIR = ROOT / "data"
PUBLIC_DIR = ROOT / "frontend" / "public"
# Original seed products shipped without a manual on purpose: the golden set has
# fallback fixtures that depend on it (e.g. KIT manuals never cited).
LEGACY_WITHOUT_MANUAL = {"AF-800-220V", "KIT-SIL-01", "CF-20B-127V", "KIT-CAF-01"}
MIN_PRODUCTS = 30
MIN_UPSELL_BASES = 8
CHECKOUT_PREFIX = {
    "AMAZON": "https://www.amazon.com.br/s?k=",
    "MERCADO_LIVRE": "https://lista.mercadolivre.com.br/",
    "SHOPEE": "https://shopee.com.br/search?keyword=",
    "LOJA_OFICIAL": "https://smartsales.example.com/produto/",
}
ENGINE = RecommendationEngine()

CATALOG = load_catalog(DATA_DIR / "catalog.json")
BY_SKU = {product.sku: product for product in CATALOG}
RELATIONS = load_relations(DATA_DIR / "product_relations.json", set(BY_SKU))
WITH_MANUAL = [p for p in CATALOG if p.sku not in LEGACY_WITHOUT_MANUAL]


def _manual_text(product: CatalogProduct) -> str:
    manual = find_manual(DATA_DIR / "manuals", product.sku)
    assert manual is not None, f"{product.sku} sem manual"
    return "\f".join(read_manual_pages(manual))


def _pt_br(number: Decimal) -> str:
    return format(number.normalize(), "f").replace(".", ",")


def _upsell(base: CatalogProduct) -> CatalogProduct | None:
    # Mirrors PostgresCatalog.upsell_candidates: active, in stock, same category/subcategory.
    candidates = [
        RecommendationCandidate(_engine_product(p))
        for p in CATALOG
        if p.sku != base.sku and p.is_active and p.stock_quantity > 0
        and (p.category, p.subcategory) == (base.category, base.subcategory)
    ]
    selected = ENGINE.select_upsell(_engine_product(base), candidates)
    return None if selected is None else BY_SKU[selected.product.sku]


def test_catalog_is_large_and_covers_the_product_scope() -> None:
    assert len(CATALOG) >= MIN_PRODUCTS
    categories = {p.category for p in CATALOG}
    assert {"Eletroportáteis", "Eletrônicos", "Periféricos", "Beleza e Cuidados Pessoais"} <= categories
    assert {"127V", "220V", "BIVOLT", "N/A"} <= {p.voltage for p in CATALOG}
    assert len([p for p in CATALOG if p.stock_quantity == 0]) >= 2
    assert set(CHECKOUT_PREFIX) == {p.marketplace for p in CATALOG}


@pytest.mark.parametrize("product", CATALOG, ids=lambda p: p.sku)
def test_product_has_image_and_marketplace_checkout(product: CatalogProduct) -> None:
    assert product.image_url.startswith("/images/")
    assert (PUBLIC_DIR / product.image_url.lstrip("/")).is_file()
    assert product.checkout_url.startswith(CHECKOUT_PREFIX[product.marketplace])
    assert product.manual_title == f"Manual {product.name}"


def test_only_legacy_products_lack_a_manual() -> None:
    missing = {p.sku for p in CATALOG if find_manual(DATA_DIR / "manuals", p.sku) is None}
    assert missing == LEGACY_WITHOUT_MANUAL


@pytest.mark.parametrize("product", WITH_MANUAL, ids=lambda p: p.sku)
def test_manual_facts_match_the_catalog(product: CatalogProduct) -> None:
    text = _manual_text(product)
    lines = text.splitlines()
    assert lines[:2] == [product.name, f"Modelo {product.sku}"]
    assert "conteúdo sintético" in lines[2]
    assert len(text.split("\f")) >= 6
    assert "R$" not in text  # price and stock are read from SQL only (R09)
    if product.voltage in ("127V", "220V"):
        assert f"exclusivamente em {product.voltage}" in text
    if product.voltage == "BIVOLT":
        assert "bivolt" in text.lower()
    if product.power_watts is not None:
        assert re.search(rf"\b{product.power_watts} W\b", text)
    if product.capacity_liters is not None:
        assert re.search(rf"\b{_pt_br(product.capacity_liters)} (L\b|litro)", text)


@pytest.mark.parametrize("product", WITH_MANUAL, ids=lambda p: p.sku)
def test_manual_volt_watt_liter_figures_are_publishable(product: CatalogProduct) -> None:
    """R01: any V/W/L figure outside SQL would make its sentence unpublishable."""
    sql_claims = SentenceVerifier(product, [])._sql_claims
    for sentence in re.split(r"(?<=[.!?])\s+|\n|\f", _manual_text(product)):
        if "danifica" in sentence:  # warning about the wrong outlet, e.g. "em 220V danifica"
            continue
        critical = {claim for claim in technical_claims(sentence) if claim[1] in {"V", "W", "L"}}
        assert critical <= sql_claims, sentence


def test_relations_are_usable_cross_sells() -> None:
    assert len(RELATIONS) >= 15
    for relation in RELATIONS:
        assert relation.relation_type == "CROSS_SELL"
        base, related = BY_SKU[relation.base_sku], BY_SKU[relation.related_sku]
        candidate = RecommendationCandidate(
            _engine_product(related),
            compatibility=CompatibilityEvidence(
                base_sku=base.sku,
                candidate_sku=related.sku,
                source="CROSS_SELL_RELATION",
                affinity_weight=relation.affinity_weight,
            ),
        )
        selected = ENGINE.select_cross_sell(_engine_product(base), [candidate])
        assert selected is not None, f"{relation.base_sku} -> {relation.related_sku}"
        assert "R$" not in relation.justification_template


def test_upsell_lines_follow_rn04() -> None:
    upsells = {p.sku: u.sku for p in CATALOG if (u := _upsell(p)) is not None}
    assert len(upsells) >= MIN_UPSELL_BASES
    for base_sku, upsell_sku in upsells.items():
        base, upsell = BY_SKU[base_sku], BY_SKU[upsell_sku]
        assert upsell.stock_quantity > 0
        assert base.price < upsell.price <= base.price * Decimal("1.35")
    # New lines must not change the original answers.
    assert upsells["AF-400-220V"] == "AF-550-220V"
    assert upsells["CF-15B-127V"] == "CF-20B-127V"


def test_sold_out_products_are_never_upsold() -> None:
    sold_out = {p.sku for p in CATALOG if p.stock_quantity == 0}
    assert sold_out
    assert all((u := _upsell(p)) is None or u.sku not in sold_out for p in CATALOG)
