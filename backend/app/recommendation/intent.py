"""Deterministic reading of the consultative need (business rules spec, section 2).

The upsell branch opens only when the customer states a need above the consulted
product or asks for a comparison; a plain technical question gets cross-sell only.
Keyword heuristic on purpose: no LLM decides what is offered for sale.
"""

import re
import unicodedata

_UPGRADE_PATTERNS = (
    r"\b(?:para|atende|serve|comporta|conta)(?: uma?)? (?:familia|\d+ pessoas?)\b",
    r"\b(?:\d+|duas|tres|quatro|cinco|seis|sete|oito|nove|dez) pessoas\b",
    r"\b(modelo|versao|opcao|tamanho|capacidade|cesto|reservatorio) maior(es)?\b",
    r"\b(?:um|uma|outro|outra) \w+ maior(es)?\b",  # "uma Airfryer maior"
    r"\bmaior (modelo|versao|opcao|tamanho|capacidade|cesto)\b",
    r"\b(tem|existe|ha) (um|uma|algum|alguma) maior\b",
    r"\bmais (capacidade|potencia|potente|espaco|litros)\b",
    r"\b(atende|da conta)\b",
    r"\bcomporta \d",
    r"\bcompar\w+",
    r"\bdiferenca\b",
    r"\b(outro|outra) (modelo|opcao|versao)\b",
    r"\b(modelo|opcao|versao) (superior|melhor)\b",
    r"\bupgrade\b",
)
_UPGRADE = re.compile("|".join(_UPGRADE_PATTERNS))


def folded(text: str) -> str:
    decomposed = unicodedata.normalize("NFD", text.lower())
    return "".join(char for char in decomposed if not unicodedata.combining(char))


_folded = folded


def wants_upgrade(question: str) -> bool:
    for clause in re.split(r"[.!?;,]|\bmas\b", _folded(question)):
        # Negated requests are different from "não atende 5 pessoas" (a need).
        if re.search(r"\b(?:nao (?:quero|preciso|desejo|busco|procuro)|sem upgrade)\b", clause):
            continue
        if _UPGRADE.search(clause):
            return True
    return False


def only_consulted_product(question: str) -> bool:
    """Explicit purchase/display restriction; a technical mention of 'only' is not enough."""
    return re.search(
        r"\b(?:comprar|mostrar|mostre|ver|ofereca|oferecer)\s+(?:somente|apenas|so)\s+"
        r"(?:o|a|este|esta|esse|essa)\b", _folded(question),
    ) is not None
