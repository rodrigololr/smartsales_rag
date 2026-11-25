"""Exercise the evaluation adapter on the production SQL/pgvector path, without LLM calls."""

import asyncio
from collections.abc import AsyncIterator, Sequence
from pathlib import Path

import psycopg
import pytest
from app.config import Settings
from app.db.repository import PostgresCatalog
from app.generation.prompt import Message
from app.ingestion.run import ingest
from ingestion_support import DATA_DIR, DATABASE_URL, HashingEmbedder, reset_backend_tables
from tests.ragas_eval.corpus import Corpus, CorpusMismatch
from tests.ragas_eval.models import PipelineInput
from tests.ragas_eval.pipeline import ProductionPipeline

pytestmark = pytest.mark.skipif(not DATABASE_URL, reason="TEST_DATABASE_URL not set")
ROOT = Path(__file__).resolve().parents[3]


class SqlAnswer:
    async def stream(self, messages: Sequence[Message]) -> AsyncIterator[str]:
        yield "Voltagem: 220V."


async def seed() -> tuple[Corpus, HashingEmbedder, Settings]:
    await reset_backend_tables()
    # Threshold zero deliberately exercises the adapter, not retrieval quality/homologation.
    settings, embedder = Settings(similarity_threshold=0), HashingEmbedder()
    await ingest(
        DATABASE_URL,
        DATA_DIR / "catalog.json",
        DATA_DIR / "manuals",
        embedder,
        settings,
        relations_path=DATA_DIR / "product_relations.json",
    )
    corpus = Corpus.from_seed(ROOT, settings)
    await corpus.verify_database(DATABASE_URL)
    return corpus, embedder, settings


def test_evaluator_observes_sql_recommendations_and_real_retrieval_uuids() -> None:
    async def scenario() -> None:
        corpus, embedder, settings = await seed()
        catalog = PostgresCatalog(DATABASE_URL)
        pipeline = ProductionPipeline(
            catalog, catalog, embedder, SqlAnswer(), settings, corpus, catalog
        )
        turn = await pipeline.run(
            PipelineInput(
                sku="AF-400-220V",
                question="Tem um modelo maior?",
                stock_overrides={"AF-400-220V": 0},
            )
        )
        assert turn.action == "ANSWER", turn.errors
        assert turn.generation_calls == 1 and turn.retrieved
        assert {c.chunk_id for c in turn.retrieved} <= set(corpus.database_ids.values())
        assert [(o.sku, o.role) for o in turn.offers] == [
            ("AF-550-220V", "UPSELL"),
            ("KIT-SIL-01", "CROSS_SELL"),
        ]
        assert (await catalog.get_product("AF-400-220V")).stock_quantity == 15  # type: ignore[union-attr]
        incompatible = await pipeline.run(
            PipelineInput(sku="AF-400-220V", question="Qual a tensão?", requested_voltage="127V")
        )
        assert all(
            incompatible.products[o.sku].voltage in {"127V", "BIVOLT", "N/A"}
            for o in incompatible.offers
        )

    asyncio.run(scenario())


@pytest.mark.parametrize("change", ["fingerprint", "zero_vector", "relations"])
def test_live_verification_rejects_untrusted_index_or_compatibility(change: str) -> None:
    async def scenario() -> None:
        corpus, _, _ = await seed()
        async with await psycopg.AsyncConnection.connect(DATABASE_URL) as conn:
            if change == "fingerprint":
                await conn.execute("UPDATE manual_chunks SET metadata = '{}'::jsonb")
            elif change == "zero_vector":
                await conn.execute(
                    "UPDATE manual_chunks SET embedding = %s::vector",
                    ("[" + ",".join(["0"] * 1536) + "]",),
                )
            else:
                await conn.execute("DELETE FROM product_relations")
        with pytest.raises(CorpusMismatch):
            await corpus.verify_database(DATABASE_URL)
        assert not corpus.verified

    asyncio.run(scenario())


def test_explicit_purchase_of_only_the_consulted_product_has_no_secondary_cards() -> None:
    class CoffeeAnswer:
        async def stream(self, messages: Sequence[Message]) -> AsyncIterator[str]:
            yield "Voltagem: 127V."

    async def scenario() -> None:
        corpus, embedder, settings = await seed()
        catalog = PostgresCatalog(DATABASE_URL)
        pipeline = ProductionPipeline(
            catalog, catalog, embedder, CoffeeAnswer(), settings, corpus, catalog
        )
        turn = await pipeline.run(
            PipelineInput(
                sku="CF-15B-127V",
                requested_voltage="127V",
                question="Quero comprar somente essa cafeteira 127V, sem oferecer modelo superior.",
            )
        )
        assert turn.action == "ANSWER", turn.errors
        assert [(o.sku, o.role) for o in turn.offers] == [("CF-15B-127V", "PRIMARY")]

    asyncio.run(scenario())
