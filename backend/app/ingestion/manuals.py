"""Manual page extraction, preserving the original page numbers."""

from io import BytesIO
from pathlib import Path

from pypdf import PdfReader

MANUAL_SUFFIXES = (".pdf", ".txt", ".md")


def read_manual_pages(path: Path, *, content: bytes | None = None) -> list[str]:
    """Return page texts in order (index 0 = page 1).

    PDFs keep their real pages. Text manuals separate pages with a form feed (\\f).
    """
    suffix = path.suffix.lower()
    snapshot = path.read_bytes() if content is None else content
    if suffix == ".pdf":
        return [page.extract_text() or "" for page in PdfReader(BytesIO(snapshot)).pages]
    if suffix in (".txt", ".md"):
        return snapshot.decode("utf-8").split("\f")
    raise ValueError(f"Formato de manual não suportado: {path.name}")


def find_manual(manuals_dir: Path, sku: str) -> Path | None:
    """Manuals are named after the SKU: data/manuals/<SKU>.pdf|.txt|.md."""
    for suffix in MANUAL_SUFFIXES:
        candidate = manuals_dir / f"{sku}{suffix}"
        if candidate.is_file():
            return candidate
    return None
