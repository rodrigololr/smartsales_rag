"""Local, controlled evidence used only in tests; never a live homologation result."""

import os
from copy import deepcopy
from pathlib import Path
from uuid import NAMESPACE_URL, uuid5

import pytest

from .corpus import Corpus, IndexedChunk
from .eval_runner import DEFAULT_FIXTURE_PATH, load_fixtures
from .models import GoldenSetFixture

os.environ.setdefault("RAGAS_DO_NOT_TRACK", "true")

ROOT = Path(__file__).resolve().parents[3]


@pytest.fixture(scope="session")
def seed_corpus() -> Corpus:
    return Corpus.from_seed(ROOT)


@pytest.fixture
def corpus(seed_corpus: Corpus) -> Corpus:
    return deepcopy(seed_corpus)


@pytest.fixture
def bound_corpus(corpus: Corpus) -> Corpus:
    rows = [
        IndexedChunk(
            chunk_id=uuid5(NAMESPACE_URL, key),
            sku=entry.reference.sku,
            manual_source=entry.reference.source,
            manual_version=entry.reference.source_sha256,
            manual_title=entry.title,
            page_number=entry.reference.page_number,
            chunk_index=entry.reference.chunk_index,
            content=entry.content,
            ingestion_fingerprint=entry.ingestion_fingerprint,
        )
        for key, entry in corpus.entries.items()
    ]
    corpus.bind_index(rows)
    return corpus


@pytest.fixture
def fixtures(corpus: Corpus) -> list[GoldenSetFixture]:
    return load_fixtures(DEFAULT_FIXTURE_PATH, corpus)
