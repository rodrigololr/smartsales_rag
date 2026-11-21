"""Pure slot extraction from customer messages (spec §1 and §2)."""

import re
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Literal

from app.guardrails.output import length_measures_cm
from app.recommendation.intent import folded


@dataclass(frozen=True)
class CategoryTarget:
    category: str
    subcategories: tuple[str, ...]


@dataclass(frozen=True)
class Slots:
    category: CategoryTarget | None = None
    budget_max: Decimal | None = None
    voltage: Literal["127V", "220V"] | None = None
    game: str | None = None
    seats: int | None = None
    room_width_cm: Decimal | None = None


CATEGORY_KEYWORDS: tuple[tuple[str, CategoryTarget], ...] = (
    (r"\b(notebooks?|laptops?)\b", CategoryTarget("Computadores", ("Notebooks Gamer",))),
    (
        r"\b(pcs?|desktops?|gabinete|computador de mesa)\b",
        CategoryTarget("Computadores", ("PCs Gamer",)),
    ),
    (
        r"\bcomputador(es)?\b",
        CategoryTarget("Computadores", ("PCs Gamer", "Notebooks Gamer")),
    ),
    (r"\bmonitor(es)?\b", CategoryTarget("Monitores", ("Monitores Gamer",))),
    (r"\b(webcams?|cameras?)\b", CategoryTarget("Periféricos", ("Webcams",))),
    (r"\bsofas?\b", CategoryTarget("Móveis", ("Sofás",))),
    (
        r"\b(airfryer|fritadeira)s?\b",
        CategoryTarget("Eletroportáteis", ("Fritadeiras Elétricas",)),
    ),
    (r"\bcafeteiras?\b", CategoryTarget("Eletroportáteis", ("Cafeteiras",))),
    (r"\bliquidificador(es)?\b", CategoryTarget("Eletroportáteis", ("Liquidificadores",))),
    (r"\bchaleiras?\b", CategoryTarget("Eletroportáteis", ("Chaleiras Elétricas",))),
    (r"\bpanelas?\b", CategoryTarget("Eletroportáteis", ("Panelas Elétricas",))),
    (r"\baspirador(es)?\b", CategoryTarget("Eletroportáteis", ("Aspiradores Robô",))),
    (r"\bfones?\b", CategoryTarget("Eletrônicos", ("Fones de Ouvido",))),
    (r"\bcaixas? de som\b", CategoryTarget("Eletrônicos", ("Caixas de Som",))),
    (r"\bmouses?\b", CategoryTarget("Periféricos", ("Mouses",))),
    (r"\bteclados?\b", CategoryTarget("Periféricos", ("Teclados",))),
    (r"\bheadsets?\b", CategoryTarget("Periféricos", ("Headsets",))),
    (
        r"\bescovas?(?:\s+(?:secadoras?|rotativas?))?\b",
        CategoryTarget("Beleza e Cuidados Pessoais", ("Escovas Secadoras",)),
    ),
    (r"\bsecador(es)?\b", CategoryTarget("Beleza e Cuidados Pessoais", ("Secadores de Cabelo",))),
    (
        r"\b(pranchas?|chapinhas?)\b",
        CategoryTarget("Beleza e Cuidados Pessoais", ("Pranchas Alisadoras",)),
    ),
)

GAME_ALIASES: dict[str, str] = {
    r"\bgta\s*(6|vi)\b": "GTA 6",
    r"\bgta\s*rp\b|\bgta\s+roleplay\b": "GTA RP",
    r"\bgta\s*(5|v)\b": "GTA V",
    r"\broblox\b": "Roblox",
    r"\bfortnite\b": "Fortnite",
    r"\b(cs\s*2|counter[\s.-]*strike(?:\s*2)?)\b": "Counter-Strike 2",
}

_COMPILED_CATEGORIES = tuple(
    (re.compile(pattern), target) for pattern, target in CATEGORY_KEYWORDS
)
_COMPILED_GAMES = tuple(
    (re.compile(pattern), canonical) for pattern, canonical in GAME_ALIASES.items()
)
_BUDGET_RE = re.compile(
    r"\b(?:ate|no maximo|maximo de|orcamento(?: de)?|gastar(?: ate)?)\s*"
    r"(?:r\$\s*)?(\d[\d.]*(?:,\d{1,2})?)\s*(mil|k)?\b"
    r"|\b(\d+(?:,\d{1,2})?)\s*mil reais\b"
)
_VOLTAGE_127_RE = re.compile(
    r"\b(127|110)\s*(?:v|volts?)\b|\btomada\s+(?:(?:de|e)\s+)?(127|110)\b"
)
_VOLTAGE_220_RE = re.compile(
    r"\b220\s*(?:v|volts?)\b|\btomada\s+(?:(?:de|e)\s+)?220\b"
)
_SEATS_RE = re.compile(r"\b(\d)\s*lugares\b")
_SKU_TOKEN_RE = re.compile(r"\b[A-Za-z]{2,4}-[A-Za-z0-9]+(?:-[A-Za-z0-9]+)*\b")
MAX_MENTIONED_SKUS = 3


def parse_category(text: str) -> CategoryTarget | None:
    normalized = folded(text)
    for pattern, target in _COMPILED_CATEGORIES:
        if pattern.search(normalized):
            return target
    return None


def parse_budget(text: str) -> Decimal | None:
    normalized = folded(text)
    match = _BUDGET_RE.search(normalized)
    if match is None:
        return None
    raw_primary, raw_kilo, raw_mil_reais = match.groups()
    if raw_mil_reais is not None:
        raw_number = raw_mil_reais.replace(",", ".")
        multiplier = Decimal("1000")
    else:
        raw_number = raw_primary.replace(".", "").replace(",", ".")
        multiplier = Decimal("1000") if raw_kilo else Decimal("1")
    try:
        amount = Decimal(raw_number) * multiplier
    except InvalidOperation:
        return None
    if amount <= 0:
        return None
    return Decimal(format(amount.normalize(), "f"))


def parse_voltage(text: str) -> Literal["127V", "220V"] | None:
    normalized = folded(text)
    if _VOLTAGE_127_RE.search(normalized):
        return "127V"
    if _VOLTAGE_220_RE.search(normalized):
        return "220V"
    return None


def parse_game(text: str) -> str | None:
    normalized = folded(text)
    for pattern, canonical in _COMPILED_GAMES:
        if pattern.search(normalized):
            return canonical
    return None


def parse_seats(text: str) -> int | None:
    match = _SEATS_RE.search(folded(text))
    return int(match.group(1)) if match else None


def parse_skus(text: str) -> tuple[str, ...]:
    seen: list[str] = []
    for token in _SKU_TOKEN_RE.findall(text):
        upper = token.upper()
        if upper.startswith("KB-") or not any(char.isdigit() for char in upper):
            continue
        if upper not in seen:
            seen.append(upper)
            if len(seen) >= MAX_MENTIONED_SKUS:
                break
    return tuple(seen)


def parse_slots(text: str, *, include_room_width: bool = True) -> Slots:
    lengths = length_measures_cm(text) if include_room_width else []
    return Slots(
        category=parse_category(text),
        budget_max=parse_budget(text),
        voltage=parse_voltage(text),
        game=parse_game(text),
        seats=parse_seats(text),
        room_width_cm=lengths[0] if lengths else None,
    )
