"""Deterministic reading of the consultative need (business rules spec, section 2).

The upsell branch opens only when the customer states a need above the consulted
product or asks for a comparison; a plain technical question gets cross-sell only.
Keyword heuristic on purpose: no LLM decides what is offered for sale.
"""

import re
import unicodedata

_UPGRADE_PATTERNS = (
    r"\bpessoas?\b",
    r"\bfamilia\b",
    r"\bmaior(es)?\b",
    r"\bmais (capacidade|potencia|potente|espaco|litros)\b",
    r"\b(atende|suficiente|da conta|comporta)\b",
    r"\bcompar\w+",
    r"\bdiferenca\b",
    r"\b(outro|outra) (modelo|opcao|versao)\b",
    r"\b(modelo|opcao|versao) (superior|melhor)\b",
    r"\bupgrade\b",
)
_UPGRADE = re.compile("|".join(_UPGRADE_PATTERNS))


def _folded(text: str) -> str:
    decomposed = unicodedata.normalize("NFD", text.lower())
    return "".join(char for char in decomposed if not unicodedata.combining(char))


def wants_upgrade(question: str) -> bool:
    return _UPGRADE.search(_folded(question)) is not None
