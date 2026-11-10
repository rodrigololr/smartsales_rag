"""G-OUT: hold each LLM sentence privately and publish it only if every technical
figure it states (voltage, power, capacity, pressure...) appears in the evidence."""

import re
from decimal import Decimal, InvalidOperation

Claim = tuple[str, str]

_UNITS = {
    "v": "V", "volt": "V", "volts": "V",
    "w": "W", "watt": "W", "watts": "W",
    "l": "L", "litro": "L", "litros": "L",
    "ml": "mL", "bar": "bar", "kg": "kg", "g": "g",
    "min": "min", "minuto": "min", "minutos": "min",
    "°c": "°C", "ºc": "°C", "graus": "°C",
    "cm": "cm", "mm": "mm",
}  # fmt: skip
_FIGURE = re.compile(
    r"(\d+(?:[.,]\d+)?)\s*("
    + "|".join(sorted(map(re.escape, _UNITS), key=len, reverse=True))
    + r")(?![a-zà-ú])",
    re.IGNORECASE,
)
_BIVOLT = re.compile(r"\bbivolt\b", re.IGNORECASE)
_SENTENCE_END = ".!?"


def _number(raw: str) -> str:
    try:
        return format(Decimal(raw.replace(",", ".")).normalize(), "f")
    except InvalidOperation:
        return raw


def technical_claims(text: str) -> set[Claim]:
    claims = {(_number(value), _UNITS[unit.lower()]) for value, unit in _FIGURE.findall(text)}
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
