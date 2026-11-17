"""B01: complete relation seeds must replace each other under concurrent writers."""

import asyncio
from decimal import Decimal

import psycopg
import pytest
from app.db.repository import apply_schema, replace_product_relations, upsert_product
from app.ingestion.relations import load_relations
from app.ingestion.run import load_catalog
from app.models.schemas import ProductRelation
from test_pgvector_ingestion import DATA_DIR, DATABASE_URL, _relation_rows, _reset

pytestmark = pytest.mark.skipif(not DATABASE_URL, reason="TEST_DATABASE_URL not set")


async def _prepare() -> list[ProductRelation]:
    await _reset()
    products = load_catalog(DATA_DIR / "catalog.json")
    async with await psycopg.AsyncConnection.connect(DATABASE_URL, autocommit=True) as conn:
        await apply_schema(conn)
        for product in products:
            await upsert_product(conn, product)
    return load_relations(DATA_DIR / "product_relations.json", {product.sku for product in products})


async def _wait_for_writer_to_block_or_finish(writer: asyncio.Task[int], pid: int) -> None:
    """Observe a real DB lock; the unfixed empty-table race can also finish immediately."""
    async with await psycopg.AsyncConnection.connect(DATABASE_URL, autocommit=True) as observer:
        async with asyncio.timeout(5):
            while not writer.done():
                cursor = await observer.execute(
                    "SELECT wait_event_type FROM pg_stat_activity WHERE pid = %s", (pid,)
                )
                row = await cursor.fetchone()
                if row and row[0] == "Lock":
                    return
                await asyncio.sleep(0.01)


def _expected(relations: list[ProductRelation]) -> list[tuple[str, str, str, Decimal]]:
    return sorted(
        (relation.base_sku, relation.related_sku, relation.relation_type, relation.affinity_weight)
        for relation in relations
    )


@pytest.mark.parametrize("initially_empty", [False, True], ids=["existing-seed", "empty-table"])
@pytest.mark.parametrize("clear_seed", [False, True], ids=["replace-seed", "clear-seed"])
def test_concurrent_relation_replacement_publishes_only_the_last_complete_seed(
    initially_empty: bool, clear_seed: bool,
) -> None:
    async def scenario() -> None:
        seeds = await _prepare()
        initial = [] if initially_empty else seeds[:1]
        replacement = [] if clear_seed else seeds[2:3]
        async with await psycopg.AsyncConnection.connect(DATABASE_URL, autocommit=True) as first:
            await replace_product_relations(first, initial)
            async with await psycopg.AsyncConnection.connect(DATABASE_URL, autocommit=True) as second:
                async with first.transaction():
                    await replace_product_relations(first, seeds[1:2])
                    # SELECTs still see the committed seed while a writer prepares its replacement.
                    assert await asyncio.wait_for(_relation_rows(), 2) == _expected(initial)
                    writer = asyncio.create_task(replace_product_relations(second, replacement))
                    try:
                        await _wait_for_writer_to_block_or_finish(writer, second.info.backend_pid)
                    except BaseException:
                        writer.cancel()
                        await asyncio.gather(writer, return_exceptions=True)
                        raise
                assert await asyncio.wait_for(writer, 5) == len(replacement)
                assert await _relation_rows() == _expected(replacement)

    asyncio.run(scenario())


def test_relation_replacement_releases_its_lock_on_rollback() -> None:
    async def scenario() -> None:
        seeds = await _prepare()
        async with await psycopg.AsyncConnection.connect(DATABASE_URL, autocommit=True) as first:
            await replace_product_relations(first, seeds[:1])
            with pytest.raises(RuntimeError, match="abort publication"):
                async with first.transaction():
                    await replace_product_relations(first, seeds[1:2])
                    raise RuntimeError("abort publication")
            assert await _relation_rows() == _expected(seeds[:1])
            # Keep the first connection open: this must be a transaction-scoped lock.
            async with await psycopg.AsyncConnection.connect(DATABASE_URL, autocommit=True) as second:
                await asyncio.wait_for(replace_product_relations(second, seeds[2:3]), 5)
                assert await _relation_rows() == _expected(seeds[2:3])

    asyncio.run(scenario())
