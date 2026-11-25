"""Pure chunking helpers: token windows, context header and catalog spec sheet."""

from tiktoken import Encoding

from app.models.schemas import CatalogProduct


def chunk_page(text: str, encoding: Encoding, *, size: int, overlap: int) -> list[str]:
    """Split one page into windows of `size` tokens sharing `overlap` tokens.

    shortcut: fixed token windows instead of the spec's hierarchical separators
    (## / paragraphs / sentences); upgrade if retrieval quality on real manuals drops.
    """
    tokens = encoding.encode(text.strip())
    if not tokens:
        return []
    step = size - overlap
    last_start = max(len(tokens) - overlap, 1)
    return [encoding.decode(tokens[start : start + size]) for start in range(0, last_start, step)]


def context_header(product: CatalogProduct, *, page_number: int) -> str:
    """Canonical prefix so 127V and 220V chunks never look alike (R01)."""
    capacity = f"{product.capacity_liters}L" if product.capacity_liters is not None else "N/A"
    return (
        f"[PRODUTO: {product.name} | SKU: {product.sku} | VOLTAGEM: {product.voltage} | "
        f"CAPACIDADE: {capacity} | MANUAL PÁG: {page_number}]"
    )


def spec_sheet(product: CatalogProduct) -> str:
    """Catalog technical data indexed as a searchable page.

    Price and stock are left out on purpose: they change often and must always be
    read from SQL at answer time (R09), never from a stale vector.
    """
    lines = [
        f"Ficha técnica oficial do catálogo: {product.name}",
        f"Marca: {product.brand}",
        f"Categoria: {product.category} / {product.subcategory}",
        f"Voltagem: {product.voltage}",
    ]
    if product.power_watts is not None:
        lines.append(f"Potência: {product.power_watts} W")
    if product.capacity_liters is not None:
        lines.append(f"Capacidade: {product.capacity_liters} L")
    lines.extend(f"{name}: {value}" for name, value in product.specs_json.items())
    if product.description:
        lines.append(product.description)
    return "\n".join(lines)
