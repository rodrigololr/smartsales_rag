"""Curated knowledge base (data/knowledge/KB-*.txt) parsing and pgvector ingestion."""

import asyncio
import hashlib
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, replace
from pathlib import Path

import psycopg
import tiktoken

from app.clients.openai_client import LLMUnavailableError
from app.config import Settings
from app.db.repository import (
    ChunkRow,
    current_knowledge_version,
    delete_missing_knowledge,
    replace_knowledge_chunks,
)
from app.ingestion.chunking import chunk_page
from app.rag.orchestrator import Embedder

logger = logging.getLogger(__name__)
CHUNK_ENCODING = "cl100k_base"
RETRYABLE_KNOWLEDGE_ERRORS = (LLMUnavailableError, psycopg.OperationalError)


@dataclass(frozen=True)
class KnowledgeDoc:
    doc_id: str
    title: str
    version: str
    pages: list[str]


def knowledge_docs(knowledge_dir: Path) -> list[KnowledgeDoc]:
    """Load and validate all KB-*.txt files in deterministic doc_id order."""
    docs: list[KnowledgeDoc] = []
    for path in sorted(knowledge_dir.glob("KB-*.txt")):
        raw = path.read_bytes()
        text = raw.decode("utf-8")
        lines = text.splitlines()
        if not lines or not lines[0].strip():
            raise ValueError(f"Documento KB sem título: {path.name}")
        title = lines[0].strip()
        if "," in title:
            raise ValueError(f"Título da KB não pode conter vírgula: {path.name}")
        docs.append(
            KnowledgeDoc(
                doc_id=path.stem,
                title=title,
                version=hashlib.sha256(raw).hexdigest(),
                pages=text.split("\f"),
            )
        )
    return docs


def knowledge_chunk_rows(
    doc: KnowledgeDoc, encoding: tiktoken.Encoding, settings: Settings
) -> list[ChunkRow]:
    rows: list[ChunkRow] = []
    for page_number, page in enumerate(doc.pages, start=1):
        pieces = chunk_page(
            page,
            encoding,
            size=settings.chunk_size_tokens,
            overlap=settings.chunk_overlap_tokens,
        )
        header = f"[BASE DE CONHECIMENTO: {doc.title} | PÁG: {page_number}]"
        rows.extend(
            ChunkRow(
                page_number=page_number,
                chunk_index=index,
                content=f"{header}\n{piece}",
                embedding=[],
                manual_title=doc.title,
            )
            for index, piece in enumerate(pieces)
        )
    return rows


async def ingest_knowledge(
    conn: psycopg.AsyncConnection[object],
    knowledge_dir: Path,
    embedder: Embedder,
    settings: Settings,
    *,
    indexed_sources: list[str],
    skipped_sources: list[str],
    needs_intervention: list[str],
    sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
) -> None:
    """Index changed KB-*.txt documents and remove deleted doc_ids from knowledge_chunks."""
    docs = knowledge_docs(knowledge_dir)
    encoding = tiktoken.get_encoding(CHUNK_ENCODING)
    for doc in docs:
        label = f"knowledge:{doc.doc_id}"
        if await current_knowledge_version(conn, doc.doc_id) == doc.version:
            skipped_sources.append(label)
            continue
        await _index_knowledge_doc(
            conn,
            doc,
            label,
            encoding,
            embedder,
            settings,
            indexed_sources=indexed_sources,
            needs_intervention=needs_intervention,
            sleep=sleep,
        )
    await delete_missing_knowledge(conn, [doc.doc_id for doc in docs])


async def _index_knowledge_doc(
    conn: psycopg.AsyncConnection[object],
    doc: KnowledgeDoc,
    label: str,
    encoding: tiktoken.Encoding,
    embedder: Embedder,
    settings: Settings,
    *,
    indexed_sources: list[str],
    needs_intervention: list[str],
    sleep: Callable[[float], Awaitable[None]],
) -> None:
    for attempt in range(1, settings.ingestion_max_attempts + 1):
        try:
            rows = knowledge_chunk_rows(doc, encoding, settings)
            if not rows:
                raise ValueError(f"Documento KB sem conteúdo extraível: {doc.doc_id}")
            embeddings = await embedder.embed([row.content for row in rows])
            await replace_knowledge_chunks(
                conn,
                doc_id=doc.doc_id,
                title=doc.title,
                doc_version=doc.version,
                rows=[
                    replace(row, embedding=vector)
                    for row, vector in zip(rows, embeddings, strict=True)
                ],
            )
        except RETRYABLE_KNOWLEDGE_ERRORS:
            if attempt >= settings.ingestion_max_attempts:
                logger.exception("knowledge_ingestion_failed", extra={"source": label})
                needs_intervention.append(label)
                return
            await sleep(settings.ingestion_backoff_seconds * 2 ** (attempt - 1))
            continue
        except Exception:
            logger.exception("knowledge_ingestion_failed", extra={"source": label})
            needs_intervention.append(label)
            return
        indexed_sources.append(label)
        return
