"""G-IN: block prompt-injection attempts before retrieval or generation."""

import re

_INJECTION = re.compile(
    r"(?:ignor|esque[cç]|desconsider)\w*\s+(?:as\s+|todas\s+as\s+|all\s+|the\s+|o\s+)?"
    r"(?:instru|regras|previous|prior|guardrail|estoque|sistema)"
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
