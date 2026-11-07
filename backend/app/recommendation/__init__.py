"""Deterministic B04 domain rules independent of SQL, HTTP and LLMs."""

from .engine import RecommendationEngine
from .models import (
    CompatibilityEvidence,
    DomainInputError,
    Product,
    Recommendation,
    RecommendationCandidate,
)

__all__ = [
    "CompatibilityEvidence",
    "DomainInputError",
    "Product",
    "Recommendation",
    "RecommendationCandidate",
    "RecommendationEngine",
]
