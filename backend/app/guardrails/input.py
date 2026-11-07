"""G-IN: block prompt-injection attempts before retrieval or generation."""

import re

_INJECTION = re.compile(
    r"ignor\w*\s+(?:as\s+|todas\s+as\s+|all\s+|the\s+)?"
    r"(?:instru|regras|previous|prior)"
    r"|system\s*prompt|prompt\s+do\s+sistema"
    r"|voc[eê]\s+agora\s+[eé]|you\s+are\s+now"
    r"|jailbreak",
    re.IGNORECASE,
)


def is_prompt_injection(question: str) -> bool:
    """shortcut: pattern list, not a classifier; extend it with the Golden Set attacks."""
    return _INJECTION.search(question) is not None
