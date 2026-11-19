import json
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from app.models.schemas import RetrievedChunk

from .corpus import Corpus, CorpusMismatch, IndexedChunk
from .models import GoldenSetFixture, PipelineInput


def test_committed_manifest_matches_production_chunking(corpus: Corpus) -> None:
    manifest = json.loads(Path(__file__).with_name("corpus_manifest.json").read_text())
    assert manifest["corpus_sha256"] == corpus.sha256
    assert {r["sku"] for r in manifest["entries"]} == set(corpus.products)
    assert len(manifest["entries"]) == len(corpus.entries)


def test_reference_answer_is_absent_from_pipeline_input(fixtures: list[GoldenSetFixture]) -> None:
    request = fixtures[0].pipeline_input()
    assert set(request.model_dump()) == {"sku", "question", "requested_voltage", "stock_overrides"}
    with pytest.raises(ValueError):
        PipelineInput.model_validate({**request.model_dump(), "expected_answer": "secret"})


def test_seed_hash_and_quote_tampering_are_rejected(
    corpus: Corpus, fixtures: list[GoldenSetFixture]
) -> None:
    reference = fixtures[0].relevant_evidence[0]
    for update in (
        {"source_sha256": "0" * 64},
        {"page_number": 999},
        {"quote": "fabricated 3000W"},
    ):
        with pytest.raises(CorpusMismatch):
            corpus.validate_reference(reference.model_copy(update=update))


def test_incomplete_or_changed_sql_corpus_is_rejected(corpus: Corpus) -> None:
    with pytest.raises(CorpusMismatch):
        corpus.bind_index([])
    entry = next(iter(corpus.entries.values()))
    row = IndexedChunk(
        chunk_id=uuid4(),
        sku=entry.reference.sku,
        manual_source=entry.reference.source,
        manual_version=entry.reference.source_sha256,
        manual_title=entry.title,
        page_number=entry.reference.page_number,
        chunk_index=entry.reference.chunk_index,
        content="tampered",
    )
    with pytest.raises(CorpusMismatch):
        corpus.bind_index([row])


def test_current_sql_catalog_must_match_declared_snapshot(corpus: Corpus) -> None:
    products = list(corpus.products.values())
    products[0] = products[0].model_copy(update={"stock_quantity": 0})
    with pytest.raises(CorpusMismatch):
        corpus.verify_products(products)


def test_only_bound_uuid_and_exact_content_are_observed(bound_corpus: Corpus) -> None:
    key, entry = next(iter(bound_corpus.entries.items()))
    chunk = RetrievedChunk(
        chunk_id=UUID(bound_corpus.database_ids[key]),
        sku=entry.reference.sku,
        manual_title=entry.title,
        page_number=entry.reference.page_number,
        content=entry.content,
        similarity_score=0.9,
    )
    assert bound_corpus.observed(chunk).chunk_id == str(chunk.chunk_id)
    for update in ({"chunk_id": uuid4()}, {"content": "different"}, {"page_number": 999}):
        with pytest.raises(CorpusMismatch):
            bound_corpus.observed(chunk.model_copy(update=update))


def test_corrected_capacity_and_missing_manual_claims(fixtures: list[GoldenSetFixture]) -> None:
    assert "1,2 kg" in fixtures[22].expected_answer
    assert "600g" not in fixtures[22].expected_answer
    assert fixtures[22].relevant_evidence[0].page_number == 14
    assert fixtures[45].expected_action == "FALLBACK"
    assert all(
        not ref.source.startswith("manual:KIT")
        for fixture in fixtures
        for ref in fixture.relevant_evidence
    )
