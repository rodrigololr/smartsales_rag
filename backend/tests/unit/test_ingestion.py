"""UT-B01: catalog schema, page extraction and chunking (500/50 tokens)."""

from decimal import Decimal
from pathlib import Path

import pytest
import tiktoken
from app.ingestion.chunking import chunk_page, context_header, spec_sheet
from app.ingestion.manuals import read_manual_pages
from app.models.schemas import CatalogProduct
from pydantic import ValidationError

ENCODING = tiktoken.get_encoding("cl100k_base")


def product(**overrides: object) -> CatalogProduct:
    fields: dict[str, object] = {
        "sku": "AF-400-220V",
        "name": "Airfryer SmartChef 4L",
        "category": "Eletroportáteis",
        "subcategory": "Fritadeiras Elétricas",
        "brand": "SmartChef",
        "price": "499.90",
        "stock_quantity": 15,
        "voltage": "220V",
        "capacity_liters": "4.0",
        "power_watts": 1500,
        "image_url": "/images/airfryer-4l.jpg",
        "checkout_url": "https://example.com/af-400",
        "specs_json": {"temperatura_max_c": 200},
    }
    fields.update(overrides)
    return CatalogProduct.model_validate(fields)


def test_ut_b01_01_catalog_rejects_invalid_voltage_price_and_unknown_fields() -> None:
    assert product().price == Decimal("499.90")
    with pytest.raises(ValidationError):
        product(voltage="110V")
    with pytest.raises(ValidationError):
        product(price="0")
    with pytest.raises(ValidationError):
        product(unexpected="x")


def test_chunks_respect_size_and_overlap_in_tokens() -> None:
    text = " ".join(f"palavra{index}" for index in range(900))
    chunks = chunk_page(text, ENCODING, size=500, overlap=50)
    token_chunks = [ENCODING.encode(chunk) for chunk in chunks]
    assert len(chunks) >= 2
    assert all(len(tokens) <= 500 for tokens in token_chunks)
    assert token_chunks[0][-50:] == token_chunks[1][:50]


def test_blank_page_produces_no_chunks() -> None:
    assert chunk_page("   \n ", ENCODING, size=500, overlap=50) == []


def test_context_header_identifies_product_voltage_capacity_and_page() -> None:
    header = context_header(product(), page_number=14)
    assert header == (
        "[PRODUTO: Airfryer SmartChef 4L | SKU: AF-400-220V | VOLTAGEM: 220V | "
        "CAPACIDADE: 4.0L | MANUAL PÁG: 14]"
    )
    assert "CAPACIDADE: N/A" in context_header(product(capacity_liters=None), page_number=1)


def test_spec_sheet_has_technical_data_but_never_price_or_stock() -> None:
    sheet = spec_sheet(product(description="Cesto antiaderente."))
    assert "Voltagem: 220V" in sheet
    assert "Potência: 1500 W" in sheet
    assert "Capacidade: 4.0 L" in sheet
    assert "temperatura_max_c: 200" in sheet
    assert "Cesto antiaderente." in sheet
    assert "499" not in sheet and "15" not in sheet.replace("1500", "")


def test_text_manual_pages_are_split_by_form_feed(tmp_path: Path) -> None:
    manual = tmp_path / "AF-400-220V.txt"
    manual.write_text("Página um\fPágina dois", encoding="utf-8")
    assert read_manual_pages(manual) == ["Página um", "Página dois"]


def test_unsupported_manual_format_is_rejected(tmp_path: Path) -> None:
    manual = tmp_path / "AF-400-220V.docx"
    manual.write_bytes(b"x")
    with pytest.raises(ValueError, match="docx"):
        read_manual_pages(manual)
