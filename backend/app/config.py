"""Typed runtime settings (CLAUDE.md 7.2: no magic numbers in code)."""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql://smartsales:smartsales@localhost:5432/smartsales"
    openai_api_key: str = ""
    embedding_model: str = "text-embedding-3-small"
    embedding_dimensions: int = 1536
    embedding_batch_size: int = 64
    llm_model: str = "gpt-4o-mini"
    llm_temperature: float = 0.2
    llm_max_tokens: int = 600
    llm_timeout_seconds: float = 20.0
    similarity_threshold: float = 0.72
    retrieval_top_k: int = 5
    chunk_size_tokens: int = 500
    chunk_overlap_tokens: int = 50
    history_max_messages: int = 6


@lru_cache
def get_settings() -> Settings:
    return Settings()
