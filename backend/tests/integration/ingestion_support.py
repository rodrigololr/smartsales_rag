"""Shared fixtures of the ingestion integration tests (real pgvector, fake embeddings)."""

import hashlib
import math
import os
import re
from collections.abc import Sequence
from pathlib import Path

import psycopg

DATABASE_URL = os.environ.get("TEST_DATABASE_URL", "")
DATA_DIR = Path(__file__).resolve().parents[3] / "data"
DIMENSIONS = 1536


class HashingEmbedder:
    """Deterministic bag-of-words vectors: shared words => higher cosine similarity."""

    def __init__(self) -> None:
        self.calls = 0

    async def embed(self, texts: Sequence[str]) -> list[list[float]]:
        self.calls += 1
        return [self._vector(text) for text in texts]

    @staticmethod
    def _vector(text: str) -> list[float]:
        vector = [0.0] * DIMENSIONS
        for word in re.findall(r"\w+", text.lower()):
            vector[int(hashlib.md5(word.encode()).hexdigest(), 16) % DIMENSIONS] += 1.0
        norm = math.sqrt(sum(value * value for value in vector)) or 1.0
        return [value / norm for value in vector]


async def reset_backend_tables() -> None:
    async with await psycopg.AsyncConnection.connect(DATABASE_URL, autocommit=True) as conn:
        await conn.execute(
            "DROP TABLE IF EXISTS ingestion_jobs, product_relations, manual_chunks, products CASCADE"
        )
