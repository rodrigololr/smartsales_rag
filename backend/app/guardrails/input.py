"""G-IN: block prompt-injection attempts before retrieval or generation."""

import re

_INJECTION = re.compile(
    r"ignor\w*\s+(?:as\s+|todas\s+as\s+|all\s+|the\s+)?"
    r"(?:instru|regras|previous|prior)"
    # Imperative only: "esqueci as instruções" and "ignorando o estoque" are customer questions.
    r"|\b(?:ignore|esque[cç]a|desconsidere|forget|disregard)\s+"
    r"(?:(?:todas|all|as|os|o|the|suas|seus|your)\s+)*"
    r"(?:instru|regras|rules|guardrail|estoque)"
    r"|system\s*(?:prompt|override)"
    r"|prompt\s+do\s+sistema"
    r"|voc[eê]\s+agora\s+[eé]|you\s+are\s+now"
    r"|afirme\s+categoricamente"
    r"|jailbreak",
    re.IGNORECASE,
)


def is_prompt_injection(question: str) -> bool:
    """shortcut: pattern list, not a classifier; extend it with the Golden Set attacks."""
    return _INJECTION.search(question) is not None
