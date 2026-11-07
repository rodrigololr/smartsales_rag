"""Typed gateway settings (CLAUDE.md 7.2: no magic numbers in code)."""

from functools import lru_cache
from typing import Annotated

from pydantic import field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    backend_internal_url: str = "http://localhost:8001"
    backend_timeout_seconds: float = 30.0
    cors_allowed_origins: Annotated[list[str], NoDecode] = ["http://localhost:3000"]
    session_ttl_seconds: int = 1800
    turn_retry_after_seconds: int = 1
    app_version: str = "0.1.0-mvp"

    @field_validator("cors_allowed_origins", mode="before")
    @classmethod
    def split_origins(cls, value: object) -> object:
        """CORS_ALLOWED_ORIGINS=http://a,http://b"""
        if isinstance(value, str):
            return [origin.strip() for origin in value.split(",") if origin.strip()]
        return value


@lru_cache
def get_settings() -> Settings:
    return Settings()
