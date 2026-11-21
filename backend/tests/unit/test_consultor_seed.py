"""P1: unit validation of data/catalog_consultor.json, relations, manuals and KB files."""

import re
from decimal import Decimal
from pathlib import Path

import pytest
import tiktoken
from app.guardrails.output import technical_claims
from app.guardrails.publication import SentenceVerifier
from app.ingestion.manuals import find_manual, read_manual_pages
from app.ingestion.relations import load_relations
from app.ingestion.run import CHUNK_ENCODING, load_catalog
from app.models.schemas import CatalogProduct
from app.recommendation.engine import RecommendationEngine
from app.recommendation.models import CompatibilityEvidence, RecommendationCandidate
from app.recommendation.service import _engine_product

ROOT = Path(__file__).resolve().parents[3]
DATA_DIR = ROOT / "data"
PUBLIC_DIR = ROOT / "frontend" / "public"
KNOWLEDGE_DIR = DATA_DIR / "knowledge"
ENCODING = tiktoken.get_encoding(CHUNK_ENCODING)
ENGINE = RecommendationEngine()

CHECKOUT_PREFIX = {
    "AMAZON": "https://www.amazon.com.br/s?k=",
    "MERCADO_LIVRE": "https://lista.mercadolivre.com.br/",
    "SHOPEE": "https://shopee.com.br/search?keyword=",
    "LOJA_OFICIAL": "https://smartsales.example.com/produto/",
}

EXPECTED_SKUS = (
    "PC-VX3-BIV",
    "PC-VX5-BIV",
    "PC-VX5P-220V",
    "PC-VX7-220V",
    "NB-NX15-BIV",
    "NB-NX16-BIV",
    "NB-NX17-BIV",
    "MN-LM24-BIV",
    "MN-LM27Q-BIV",
    "MN-LM27U-BIV",
    "WC-1080-60",
    "WC-2K-60",
    "SF-2L-150",
    "SF-3L-180",
    "SF-3L-210R",
)

REQUIRED_SPEC_KEYS: dict[str, set[str]] = {
    "PCs Gamer": {
        "processador",
        "placa_de_video",
        "memoria_ram_gb",
        "armazenamento_gb",
        "armazenamento_tipo",
        "fonte_bivolt_automatica",
        "largura_cm",
        "altura_cm",
        "profundidade_cm",
        "garantia_meses",
        "avaliacao_media",
        "avaliacoes_total",
    },
    "Notebooks Gamer": {
        "processador",
        "placa_de_video",
        "memoria_ram_gb",
        "armazenamento_gb",
        "tela_polegadas",
        "taxa_atualizacao_hz",
        "peso_kg",
        "garantia_meses",
        "avaliacao_media",
        "avaliacoes_total",
    },
    "Monitores Gamer": {
        "tela_polegadas",
        "resolucao",
        "taxa_atualizacao_hz",
        "tempo_resposta_ms",
        "painel",
        "entradas",
        "garantia_meses",
        "avaliacao_media",
        "avaliacoes_total",
    },
    "Webcams": {
        "resolucao",
        "fps",
        "foco",
        "microfone",
        "garantia_meses",
        "avaliacao_media",
        "avaliacoes_total",
    },
    "Sofás": {
        "largura_cm",
        "profundidade_cm",
        "altura_cm",
        "lugares",
        "material",
        "retratil",
        "reclinavel",
        "garantia_meses",
        "avaliacao_media",
        "avaliacoes_total",
    },
}

GAME_ROW_RE = re.compile(
    r"^\|\s*(?P<game>[^|]+?)\s*\|\s*(?P<res>\d{3,4}p)\s*\|\s*(?P<preset>[^|]+?)\s*\|\s*(?P<fps>\d+)\s*fps\s*\|$"
)
EXPECTED_GAMES = ("Roblox", "GTA V", "Fortnite", "Counter-Strike 2")

EXPECTED_KB_TITLES = {
    "KB-GTA6-PLATAFORMAS": "GTA 6 plataformas e versão para PC",
    "KB-GTA-RP": "GTA RP no PC",
    "KB-GTAV-REQUISITOS": "Requisitos do GTA V para PC",
    "KB-ROBLOX-REQUISITOS": "Requisitos do Roblox para PC",
    "KB-TWITCH-TRANSMISSAO": "Twitch qualidade de transmissão",
    "KB-SOFA-ESPACO": "Sofá espaço necessário no ambiente",
}

FROZEN_KB_LINES = (
    (
        "KB-GTA6-PLATAFORMAS",
        "GTA 6 foi lançado em 19/11/2026 para PlayStation 5 e Xbox Series X|S.",
    ),
    (
        "KB-GTA6-PLATAFORMAS",
        "Não há versão de GTA 6 para PC anunciada até a data de atualização desta base.",
    ),
    (
        "KB-GTA-RP",
        "GTA RP é jogado no GTA V para PC por meio de servidores de roleplay.",
    ),
    (
        "KB-TWITCH-TRANSMISSAO",
        "| Altura máxima de vídeo recomendada | 1080 px |",
    ),
    (
        "KB-TWITCH-TRANSMISSAO",
        "| Taxa de quadros máxima recomendada | 60 fps |",
    ),
    (
        "KB-SOFA-ESPACO",
        "| Folga lateral mínima por lado | 10 cm |",
    ),
    (
        "KB-SOFA-ESPACO",
        "| Passagem livre mínima à frente | 76 cm |",
    ),
)

SOFA_CURATION_NOTE = (
    "Curadoria SmartSales: adota-se 10 cm por lado com base na faixa de 8 a 13 cm "
    "de afastamento recomendada por designers; não é norma técnica."
)


def _consultor_catalog() -> list[CatalogProduct]:
    return load_catalog(DATA_DIR / "catalog_consultor.json")


def _combined_catalog() -> dict[str, CatalogProduct]:
    base = load_catalog(DATA_DIR / "catalog.json")
    consultor = _consultor_catalog()
    combined = [*base, *consultor]
    assert len({p.sku for p in combined}) == len(combined)
    return {p.sku: p for p in combined}


def _manual_pages(sku: str) -> list[str]:
    manual = find_manual(DATA_DIR / "manuals", sku)
    assert manual is not None, f"{sku} sem manual"
    return read_manual_pages(manual)


def _upsell(
    base: CatalogProduct,
    catalog: dict[str, CatalogProduct],
    *,
    requested_voltage: str | None = None,
) -> CatalogProduct | None:
    candidates = [
        RecommendationCandidate(_engine_product(p))
        for p in catalog.values()
        if p.sku != base.sku
        and p.is_active
        and p.stock_quantity > 0
        and (p.category, p.subcategory) == (base.category, base.subcategory)
    ]
    selected = ENGINE.select_upsell(
        _engine_product(base),
        candidates,
        requested_voltage=requested_voltage,  # type: ignore[arg-type]
    )
    return None if selected is None else catalog[selected.product.sku]


def test_consultor_catalog_has_15_skus_with_required_specs_and_images() -> None:
    products = _consultor_catalog()
    assert tuple(p.sku for p in products) == EXPECTED_SKUS
    assert {"BIVOLT", "220V", "N/A"} <= {p.voltage for p in products}
    sold_out = [p.sku for p in products if p.stock_quantity == 0]
    assert sold_out == ["NB-NX17-BIV"]

    for product in products:
        assert product.capacity_liters is None
        assert product.image_url == f"/images/{product.sku.lower()}.svg"
        assert (PUBLIC_DIR / product.image_url.lstrip("/")).is_file()
        assert product.checkout_url.startswith(CHECKOUT_PREFIX[product.marketplace])
        assert product.manual_title == f"Manual {product.name}"
        required = REQUIRED_SPEC_KEYS[product.subcategory]
        assert required <= set(product.specs_json), f"{product.sku} missing specs keys"


def test_consultor_manuals_follow_structure_and_publishable_claims() -> None:
    for product in _consultor_catalog():
        pages = _manual_pages(product.sku)
        assert len(pages) == 6, f"{product.sku} must have 6 pages"
        assert all(len(ENCODING.encode(page.strip())) <= 400 for page in pages)
        text = "\f".join(pages)
        lines = text.splitlines()
        assert lines[:2] == [product.name, f"Modelo {product.sku}"]
        assert "conteúdo sintético" in lines[2]
        assert "R$" not in text
        if product.voltage in ("127V", "220V"):
            assert f"exclusivamente em {product.voltage}" in text
        if product.voltage == "BIVOLT":
            assert "bivolt" in text.lower()
        if product.power_watts is not None:
            assert re.search(rf"\b{product.power_watts} W\b", text)
        warranty = product.specs_json["garantia_meses"]
        assert f"Garantia de {warranty} meses" in pages[5]

        sql_claims = SentenceVerifier(product, [])._sql_claims
        for sentence in re.split(r"(?<=[.!?])\s+|\n|\f", text):
            if "danifica" in sentence:
                continue
            prose = sentence.replace(product.sku, "")
            critical = {c for c in technical_claims(prose) if c[1] in {"V", "W", "L"}}
            assert critical <= sql_claims, f"{product.sku}: {sentence}"


def test_computadores_manuals_have_p4_games_table_with_fps_rising_by_tier() -> None:
    products = {p.sku: p for p in _consultor_catalog() if p.category == "Computadores"}
    assert len(products) == 7
    fps_by_sku: dict[str, dict[str, int]] = {}

    for sku, product in products.items():
        page_4 = _manual_pages(sku)[3]
        assert "## Desempenho em jogos" in page_4
        assert "| Jogo | Resolução | Predefinição | Desempenho médio |" in page_4
        assert "Valores medidos pelo fabricante em ambiente de teste." in page_4
        rows: dict[str, int] = {}
        for line in page_4.splitlines():
            match = GAME_ROW_RE.match(line.strip())
            if match:
                rows[match.group("game")] = int(match.group("fps"))
        assert tuple(rows) == EXPECTED_GAMES, f"{sku} games rows: {rows}"
        fps_by_sku[sku] = rows
        assert product.tier_rank >= 1

    pc_skus = ("PC-VX3-BIV", "PC-VX5-BIV", "PC-VX5P-220V", "PC-VX7-220V")
    nb_skus = ("NB-NX15-BIV", "NB-NX16-BIV", "NB-NX17-BIV")
    for ladder in (pc_skus, nb_skus):
        for low_sku, high_sku in zip(ladder, ladder[1:], strict=False):
            for game in EXPECTED_GAMES:
                assert fps_by_sku[low_sku][game] < fps_by_sku[high_sku][game], (
                    f"{game} FPS must rise from {low_sku} to {high_sku}"
                )


def test_sofa_manuals_have_dimension_table_matching_specs_json() -> None:
    sofas = [p for p in _consultor_catalog() if p.subcategory == "Sofás"]
    assert len(sofas) == 3
    for sofa in sofas:
        text = "\f".join(_manual_pages(sofa.sku))
        assert f"| Largura | {sofa.specs_json['largura_cm']} cm |" in text
        assert f"| Profundidade | {sofa.specs_json['profundidade_cm']} cm |" in text
        assert f"| Altura | {sofa.specs_json['altura_cm']} cm |" in text


def test_consultor_upsell_ladders_and_cross_sell_relations() -> None:
    catalog = _combined_catalog()
    expected_upsells = {
        "PC-VX3-BIV": "PC-VX5-BIV",
        "PC-VX5P-220V": "PC-VX7-220V",
        "NB-NX15-BIV": "NB-NX16-BIV",
        "NB-NX16-BIV": None,  # NB-NX17-BIV is sold out (R03)
        "MN-LM24-BIV": "MN-LM27Q-BIV",
        "MN-LM27Q-BIV": "MN-LM27U-BIV",
        "WC-1080-01": "WC-1080-60",
        "WC-1080-60": "WC-2K-60",
        "SF-2L-150": "SF-3L-180",
        "SF-3L-180": "SF-3L-210R",
    }
    for base_sku, expected_sku in expected_upsells.items():
        upsell = _upsell(catalog[base_sku], catalog)
        actual_sku = None if upsell is None else upsell.sku
        assert actual_sku == expected_sku, f"{base_sku} -> {actual_sku} != {expected_sku}"
        if upsell is not None:
            base = catalog[base_sku]
            assert base.price < upsell.price <= base.price * Decimal("1.35")

    # PC-VX5-BIV -> PC-VX5P-220V is blocked by default voltage, unlocked when 220V is requested
    assert _upsell(catalog["PC-VX5-BIV"], catalog) is None
    assert _upsell(catalog["PC-VX5-BIV"], catalog, requested_voltage="220V") == catalog["PC-VX5P-220V"]

    relations = load_relations(DATA_DIR / "product_relations_consultor.json", set(catalog))
    expected_pairs = {
        ("PC-VX3-BIV", "MN-LM24-BIV"),
        ("PC-VX5-BIV", "MN-LM27Q-BIV"),
        ("PC-VX5P-220V", "MN-LM27Q-BIV"),
        ("PC-VX7-220V", "MN-LM27U-BIV"),
        ("NB-NX15-BIV", "MN-LM24-BIV"),
        ("NB-NX16-BIV", "MN-LM27Q-BIV"),
    }
    assert {(r.base_sku, r.related_sku) for r in relations} == expected_pairs
    for relation in relations:
        assert relation.relation_type == "CROSS_SELL"
        assert relation.affinity_weight == Decimal("0.900")
        assert "R$" not in relation.justification_template
        base, related = catalog[relation.base_sku], catalog[relation.related_sku]
        candidate = RecommendationCandidate(
            _engine_product(related),
            compatibility=CompatibilityEvidence(
                base_sku=base.sku,
                candidate_sku=related.sku,
                source="CROSS_SELL_RELATION",
                affinity_weight=relation.affinity_weight,
            ),
        )
        assert ENGINE.select_cross_sell(_engine_product(base), [candidate]) is not None


def test_knowledge_base_files_and_frozen_strings() -> None:
    kb_files = {path.stem: path for path in sorted(KNOWLEDGE_DIR.glob("KB-*.txt"))}
    assert set(kb_files) == set(EXPECTED_KB_TITLES)

    for doc_id, expected_title in EXPECTED_KB_TITLES.items():
        text = kb_files[doc_id].read_text(encoding="utf-8")
        lines = text.splitlines()
        assert lines[0] == expected_title
        assert "," not in lines[0]
        assert re.fullmatch(
            r"Fonte de referência: https://\S+; consultado em 21/11/2026 \(curadoria SmartSales\)\.",
            lines[1],
        ), f"{doc_id} invalid source line: {lines[1]}"
        pages = text.split("\f")
        assert len(pages) >= 2
        assert pages[-1].lstrip().startswith("## Fontes\n")
        assert all(len(ENCODING.encode(page.strip())) <= 400 for page in pages)

    for doc_id, frozen_line in FROZEN_KB_LINES:
        lines = [line.strip() for line in kb_files[doc_id].read_text(encoding="utf-8").splitlines()]
        assert frozen_line in lines, f"Missing frozen line in {doc_id}: {frozen_line}"

    sofa_pages = kb_files["KB-SOFA-ESPACO"].read_text(encoding="utf-8").split("\f")
    clearance_pages = [
        page for page in sofa_pages if "| Folga lateral mínima por lado | 10 cm |" in page
    ]
    assert len(clearance_pages) == 1
    assert SOFA_CURATION_NOTE in clearance_pages[0].splitlines()


def test_knowledge_docs_parses_files_and_rejects_comma_in_title(tmp_path: Path) -> None:
    from app.ingestion.knowledge import knowledge_docs

    docs = {doc.doc_id: doc for doc in knowledge_docs(KNOWLEDGE_DIR)}
    assert set(docs) == set(EXPECTED_KB_TITLES)
    for doc_id, doc in docs.items():
        assert doc.title == EXPECTED_KB_TITLES[doc_id]
        assert len(doc.version) == 64
        assert len(doc.pages) >= 2

    bad = tmp_path / "KB-INVALID.txt"
    bad.write_text("Título inválido, com vírgula\nConteúdo\f## Fontes\nhttps://example.com\n", encoding="utf-8")
    with pytest.raises(ValueError, match="vírgula"):
        knowledge_docs(tmp_path)


def test_load_catalog_accepts_multiple_files_and_rejects_duplicate_skus(
    tmp_path: Path,
) -> None:
    combined = load_catalog(
        [DATA_DIR / "catalog.json", DATA_DIR / "catalog_consultor.json"]
    )
    assert len(combined) == 47
    with pytest.raises(ValueError, match="duplicado"):
        load_catalog([DATA_DIR / "catalog_consultor.json", DATA_DIR / "catalog_consultor.json"])

