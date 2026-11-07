"""Typed runtime settings (CLAUDE.md 7.2: no magic numbers in code)."""

from functools import lru_cache

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql://smartsales:smartsales@localhost:5432/smartsales"
    # Any OpenAI-compatible provider. Google Gemini: LLM_BASE_URL=
    # https://generativelanguage.googleapis.com/v1beta/openai/ with a Google API key.
    llm_api_key: str = Field(default="", validation_alias=AliasChoices("LLM_API_KEY", "OPENAI_API_KEY"))
    llm_base_url: str | None = None
    embedding_model: str = "text-embedding-3-small"
    embedding_dimensions: int = 1536
    embedding_batch_size: int = 64
    llm_model: str = "gpt-4o-mini"
    llm_temperature: float = 0.2
    llm_max_tokens: int = 600
    llm_timeout_seconds: float = 20.0
    llm_first_token_timeout_seconds: float = 3.0  # RNF07
    llm_first_token_attempts: int = 2  # RNF07: one retry before LLM_UNAVAILABLE
    similarity_threshold: float = 0.72
    retrieval_top_k: int = 5
    chunk_size_tokens: int = 500
    chunk_overlap_tokens: int = 50
    history_max_messages: int = 6


@lru_cache
def get_settings() -> Settings:
    return Settings()
