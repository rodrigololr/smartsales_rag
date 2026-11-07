"""Print the top chunk similarities for a question, to calibrate SIMILARITY_THRESHOLD.

    python -m app.retrieval.inspect --sku AF-400-220V "Posso usar forma de vidro?"
"""

import argparse
import asyncio

from openai import AsyncOpenAI

from app.clients.openai_client import OpenAIEmbedder
from app.config import get_settings
from app.db.repository import PostgresCatalog

PREVIEW_CHARS = 90


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Inspeciona a recuperação de chunks")
    parser.add_argument("question")
    parser.add_argument("--sku", required=True)
    parser.add_argument("--limit", type=int, default=5)
    args = parser.parse_args(argv)
    settings = get_settings()
    embedder = OpenAIEmbedder(
        AsyncOpenAI(api_key=settings.openai_api_key),
        model=settings.embedding_model,
        dimensions=settings.embedding_dimensions,
        batch_size=settings.embedding_batch_size,
    )
    catalog = PostgresCatalog(settings.database_url)

    async def run() -> None:
        [vector] = await embedder.embed([args.question])
        chunks = await catalog.search(args.sku, vector, args.limit)
        print(f"SIMILARITY_THRESHOLD atual: {settings.similarity_threshold}")
        for chunk in chunks:
            mark = "OK " if chunk.similarity_score >= settings.similarity_threshold else "-- "
            preview = chunk.content.split("\n", 1)[-1].replace("\n", " ")[:PREVIEW_CHARS]
            print(f"{mark}{chunk.similarity_score:.3f}  p.{chunk.page_number}  {preview}")

    asyncio.run(run())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
