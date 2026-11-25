"""Audit fixture references and bind them to the UUIDs of the actual ingested corpus."""

import hashlib
import json
import math
from dataclasses import dataclass, field
from pathlib import Path
from uuid import UUID

import psycopg
import tiktoken
from app.config import Settings
from app.ingestion.chunking import context_header
from app.ingestion.relations import load_relations
from app.ingestion.run import CHUNK_ENCODING, _chunk_rows, load_catalog, sources_for
from app.models.schemas import CatalogProduct, ProductRelation, RetrievedChunk
from psycopg.rows import dict_row
from pydantic import BaseModel

from .models import EvidenceRef, GoldenSetFixture, ObservedEvidence


def digest(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def stable_json(value: object) -> bytes:
    return json.dumps(
        value, sort_keys=True, ensure_ascii=False, allow_nan=False, separators=(",", ":")
    ).encode()


class CorpusMismatch(ValueError):
    """Fixture/SQL evidence is missing, stale, or belongs to another corpus."""


class IndexedChunk(BaseModel):
    chunk_id: UUID
    sku: str
    manual_source: str
    manual_version: str
    manual_title: str
    page_number: int
    chunk_index: int
    content: str
    ingestion_fingerprint: str | None = None

    @property
    def key(self) -> str:
        return "|".join(
            (
                self.sku,
                self.manual_source,
                self.manual_version,
                str(self.page_number),
                str(self.chunk_index),
            )
        )


@dataclass(frozen=True)
class CorpusEntry:
    reference: EvidenceRef
    content: str
    title: str
    ingestion_fingerprint: str


@dataclass
class Corpus:
    products: dict[str, CatalogProduct]
    entries: dict[str, CorpusEntry]
    sha256: str
    database_ids: dict[str, str] = field(default_factory=dict)
    verified: bool = False
    relations: list[ProductRelation] = field(default_factory=list)
    embeddings_sha256: str = ""

    @classmethod
    def from_seed(cls, root: Path, settings: Settings | None = None) -> "Corpus":
        settings = settings or Settings.model_construct()
        encoding = tiktoken.get_encoding(CHUNK_ENCODING)
        products = {p.sku: p for p in load_catalog(root / "data/catalog.json")}
        entries: dict[str, CorpusEntry] = {}
        for product in products.values():
            for source in sources_for(product, root / "data/manuals"):
                for row in _chunk_rows(product, source, encoding, settings):
                    reference = EvidenceRef(
                        sku=product.sku,
                        source=source.source,
                        source_sha256=source.version,
                        page_number=row.page_number,
                        chunk_index=row.chunk_index,
                        quote=row.content.split("\n", 1)[-1],
                    )
                    fingerprint = digest(
                        json.dumps(
                            {
                                "version": source.version,
                                "title": source.title,
                                "context": context_header(product, page_number=1),
                                "embedding_model": settings.embedding_model,
                                "embedding_base_url": settings.llm_base_url,
                                "dimensions": settings.embedding_dimensions,
                                "chunk_size": settings.chunk_size_tokens,
                                "chunk_overlap": settings.chunk_overlap_tokens,
                                "policy": "ingestion-v2",
                            },
                            sort_keys=True,
                        ).encode()
                    )
                    entries[reference.key] = CorpusEntry(
                        reference, row.content, row.manual_title, fingerprint
                    )
        relations = load_relations(root / "data/product_relations.json", set(products))
        payload = {
            "catalog": [p.model_dump(mode="json") for p in products.values()],
            "chunks": {key: [e.content, e.ingestion_fingerprint] for key, e in entries.items()},
            "relations": [r.model_dump(mode="json") for r in relations],
            "chunking": [CHUNK_ENCODING, settings.chunk_size_tokens, settings.chunk_overlap_tokens],
        }
        return cls(products, entries, digest(stable_json(payload)), relations=relations)

    def validate_reference(self, reference: EvidenceRef) -> None:
        entry = self.entries.get(reference.key)
        if entry is None:
            raise CorpusMismatch(f"Unknown source/version/page/chunk: {reference.key}")
        if " ".join(reference.quote.split()) not in " ".join(entry.content.split()):
            raise CorpusMismatch(f"Audit quote absent from evidence: {reference.key}")

    def validate_fixture(self, fixture: GoldenSetFixture) -> None:
        for sku in [
            fixture.input_filters.sku,
            *fixture.stock_overrides,
            *(offer.sku for offer in fixture.expected_offers),
        ]:
            if sku not in self.products:
                raise CorpusMismatch(f"{fixture.id}: unknown SKU {sku}")
        for reference in [*fixture.relevant_evidence, *fixture.audit_evidence]:
            self.validate_reference(reference)
        keys = [e.key for e in fixture.relevant_evidence]
        if len(keys) != len(set(keys)):
            raise CorpusMismatch(f"{fixture.id}: repeated relevant evidence")

    def bind_index(self, rows: list[IndexedChunk]) -> None:
        ids: dict[str, str] = {}
        for row in rows:
            entry = self.entries.get(row.key)
            if (
                entry is None
                or row.content != entry.content
                or row.manual_title != entry.title
                or row.ingestion_fingerprint != entry.ingestion_fingerprint
            ):
                raise CorpusMismatch(f"SQL chunk does not match the versioned seed: {row.chunk_id}")
            if row.key in ids or str(row.chunk_id) in ids.values():
                raise CorpusMismatch("Duplicate SQL chunk identity")
            ids[row.key] = str(row.chunk_id)
        if set(ids) != set(self.entries):
            raise CorpusMismatch("SQL corpus is incomplete; ingest the declared seed first")
        self.database_ids = ids

    def verify_products(self, products: list[CatalogProduct]) -> None:
        # These are the columns actually persisted by ingestion, not display-only defaults.
        ignored = {"description", "manual_title"}
        actual = {p.sku: p.model_dump(mode="python", exclude=ignored) for p in products}
        expected = {
            s: p.model_dump(mode="python", exclude=ignored) for s, p in self.products.items()
        }
        if actual != expected:
            raise CorpusMismatch("SQL catalog differs from the declared evaluation snapshot")

    async def verify_database(self, conninfo: str) -> None:
        from app.db.repository import _PRODUCT_COLUMNS

        self.verified = False
        async with await psycopg.AsyncConnection.connect(conninfo) as conn:
            cursor = conn.cursor(row_factory=dict_row)
            await cursor.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY")
            await cursor.execute(
                "SELECT id AS chunk_id, sku, manual_source, manual_version, manual_title, "
                "page_number, chunk_index, content, embedding::text AS embedding, "
                "metadata->>'ingestion_fingerprint' AS ingestion_fingerprint FROM manual_chunks ORDER BY id"
            )
            rows = await cursor.fetchall()
            self.bind_index([IndexedChunk.model_validate(row) for row in rows])
            for row in rows:
                vector = json.loads(row["embedding"])
                if (
                    len(vector) != 1536
                    or not any(vector)
                    or not all(math.isfinite(x) for x in vector)
                ):
                    raise CorpusMismatch("Missing, nonfinite, zero or incompatible embedding")
            self.embeddings_sha256 = digest(
                stable_json({str(r["chunk_id"]): r["embedding"] for r in rows})
            )
            await cursor.execute(f"SELECT {_PRODUCT_COLUMNS} FROM products".encode())
            self.verify_products(
                [CatalogProduct.model_validate(row) for row in await cursor.fetchall()]
            )
            await cursor.execute(
                "SELECT base.sku AS base_sku, related.sku AS related_sku, relation_type, "
                "affinity_weight, justification_template FROM product_relations relation "
                "JOIN products base ON base.id = base_product_id "
                "JOIN products related ON related.id = related_product_id"
            )
            actual = [ProductRelation.model_validate(row) for row in await cursor.fetchall()]

            def canonical(relations: list[ProductRelation]) -> list[bytes]:
                return sorted(stable_json(r.model_dump(mode="json")) for r in relations)

            if canonical(actual) != canonical(self.relations):
                raise CorpusMismatch("SQL compatibility relations differ from the seed")
        self.verified = True

    def relevant_ids(self, fixture: GoldenSetFixture) -> list[str]:
        try:
            return [self.database_ids[reference.key] for reference in fixture.relevant_evidence]
        except KeyError as error:
            raise CorpusMismatch(
                "Relevant evidence has not been bound to ingested UUIDs"
            ) from error

    def observed(self, chunk: RetrievedChunk) -> ObservedEvidence:
        key = next((k for k, uid in self.database_ids.items() if uid == str(chunk.chunk_id)), None)
        if key is None:
            raise CorpusMismatch(f"Retrieved UUID absent from verified corpus: {chunk.chunk_id}")
        entry = self.entries[key]
        if (
            chunk.content != entry.content
            or chunk.sku != entry.reference.sku
            or chunk.manual_title != entry.title
            or chunk.page_number != entry.reference.page_number
        ):
            raise CorpusMismatch(f"Retrieved evidence changed since verification: {chunk.chunk_id}")
        return ObservedEvidence(
            chunk_id=str(chunk.chunk_id),
            key=key,
            sku=chunk.sku,
            manual_title=chunk.manual_title,
            page_number=chunk.page_number,
            content=chunk.content,
        )
