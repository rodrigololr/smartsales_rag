"""G-OUT: hold each LLM sentence privately and publish it only if every technical
figure it states (voltage, power, capacity, pressure...) appears in the evidence."""

import re
from decimal import Decimal, InvalidOperation

Claim = tuple[str, str]

_UNITS = {
    "v": "V", "volt": "V", "volts": "V",
    "w": "W", "watt": "W", "watts": "W",
    "kw": "kW", "quilowatt": "kW", "quilowatts": "kW",
    "l": "L", "litro": "L", "litros": "L",
    "ml": "mL", "mililitro": "mL", "mililitros": "mL",
    "bar": "bar", "kg": "kg", "g": "g",
    "min": "min", "minuto": "min", "minutos": "min",
    "°c": "°C", "ºc": "°C", "graus": "°C",
    "cm": "cm", "mm": "mm",
}  # fmt: skip
# pt-BR numbers: "1.500" is a thousands separator (1500), "1,5" a decimal comma.
_THOUSANDS = r"[1-9]\d{0,2}(?:\.\d{3})+(?:,\d+)?"
_FIGURE = re.compile(
    rf"({_THOUSANDS}|\d+(?:[.,]\d+)?)\s*("
    + "|".join(sorted(map(re.escape, _UNITS), key=len, reverse=True))
    + r")(?![a-zà-ú])",
    re.IGNORECASE,
)
_BIVOLT = re.compile(r"\bbivolt\b", re.IGNORECASE)
_MONEY = re.compile(
    r"(?:R\$\s*|\b(?:custa|pre[cç]o(?:\s+atual)?(?:\s+é)?(?:\s+de)?)\s*:?\s*)(\d[\d.,]*)"
    r"|(\d[\d.,]*)\s*reais\b", re.IGNORECASE,
)
_SENTENCE_END = ".!?"


def _number(raw: str) -> str:
    if re.fullmatch(_THOUSANDS, raw):
        raw = raw.replace(".", "")
    try:
        return format(Decimal(raw.replace(",", ".")).normalize(), "f")
    except InvalidOperation:
        return raw


def technical_claims(text: str) -> set[Claim]:
    claims: set[Claim] = set()
    for value, raw_unit in _FIGURE.findall(text):
        unit = _UNITS[raw_unit.lower()]
        amount = _number(value)
        if unit in {"mL", "kW"}:
            scaled = Decimal(amount) * (Decimal("0.001") if unit == "mL" else 1000)
            amount = format(scaled.normalize(), "f")
            unit = "L" if unit == "mL" else "W"
        claims.add((amount, unit))
    for prefixed, suffixed in _MONEY.findall(text):
        raw = (prefixed or suffixed).rstrip(".,")
        if "," in raw:
            raw = raw.replace(".", "").replace(",", ".")
        elif raw.count(".") > 1 or ("." in raw and len(raw.rsplit(".", 1)[1]) == 3):
            raw = raw.replace(".", "")
        claims.add((_number(raw), "BRL"))
    if _BIVOLT.search(text):
        claims.add(("bivolt", "V"))
    return claims


def unsupported_claims(sentence: str, evidence: set[Claim]) -> set[Claim]:
    return technical_claims(sentence) - evidence


class SentenceBuffer:
    """Accumulates streamed deltas and releases whole sentences.

    A sentence ends at . ! ? followed by whitespace, or at a newline, except inside
    a [Fonte: ..., p. N] citation. Trailing whitespace stays with the sentence so the
    published text concatenates back exactly.
    """

    def __init__(self) -> None:
        self._pending = ""

    def feed(self, delta: str) -> list[str]:
        self._pending += delta
        sentences: list[str] = []
        depth = 0
        start = 0
        for index, char in enumerate(self._pending):
            if char == "[":
                depth += 1
            elif char == "]":
                depth = max(depth - 1, 0)
            elif depth == 0 and self._is_boundary(index):
                sentences.append(self._pending[start : index + 1])
                start = index + 1
        self._pending = self._pending[start:]
        return sentences

    def _is_boundary(self, index: int) -> bool:
        char = self._pending[index]
        if char == "\n":
            return True
        if index > 0 and self._pending[index - 1] in _SENTENCE_END and char.isspace():
            return True
        return False

    def flush(self) -> str:
        rest, self._pending = self._pending, ""
        return rest
