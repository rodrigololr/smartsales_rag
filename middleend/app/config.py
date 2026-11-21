"""Typed gateway settings (CLAUDE.md 7.2: no magic numbers in code)."""

from functools import lru_cache
from typing import Annotated

from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    backend_internal_url: str = "http://localhost:8001"
    backend_timeout_seconds: float = Field(default=30.0, gt=0)
    backend_first_event_timeout_seconds: float = Field(default=3.0, gt=0)
    cors_allowed_origins: Annotated[list[str], NoDecode] = ["http://localhost:3000"]
    # Unset = sessions in process memory (single replica, lost on restart).
    redis_url: str | None = None
    database_url: str | None = None
    # M05: mock checkout decrements products.stock_quantity on CONFIRMED.
    checkout_decrement_stock: bool = True
    session_db_connect_timeout_seconds: int = Field(default=2, ge=1)
    session_db_query_timeout_ms: int = Field(default=2000, ge=1)
    session_heartbeat_seconds: float = Field(default=10.0, gt=0)
    session_maintenance_seconds: float = Field(default=60.0, gt=0)
    # Bound every Redis call: a black-holed Redis must fail the request, not hang it.
    redis_socket_timeout_seconds: float = Field(default=2.0, gt=0)
    redis_socket_connect_timeout_seconds: float = Field(default=2.0, gt=0)
    # libpq floors connect_timeout at 2 s; smaller values are raised to it.
    database_connect_timeout_seconds: int = Field(default=2, ge=2)
    cache_ttl_seconds: int = Field(default=3600, ge=1)
    cache_policy_version: str = "p1"  # bump when prompts, guardrails, ranking or model change
    session_ttl_seconds: int = Field(default=1800, ge=1)
    # Sliding window kept per session; even, so it never starts with an orphan answer.
    session_history_max_messages: int = Field(default=10, ge=2, multiple_of=2)
    session_lock_ttl_seconds: int = Field(
        default=60, ge=1
    )  # SET NX EX: one turn at a time per session
    turn_retry_after_seconds: int = 1
    # M04: X-Admin-Token for GET /metrics/summary. Unset or blank = endpoint always answers 401.
    admin_token: SecretStr | None = None
    app_version: str = "0.1.0-mvp"

    @model_validator(mode="after")
    def session_storage_configuration(self) -> "Settings":
        if self.database_url and not self.redis_url:
            raise ValueError("DATABASE_URL sessions require REDIS_URL")
        if self.session_heartbeat_seconds >= min(
            self.session_lock_ttl_seconds, self.session_ttl_seconds
        ):
            raise ValueError("session_heartbeat_seconds must be below session and lock TTL")
        return self

    @field_validator("admin_token", mode="before")
    @classmethod
    def blank_admin_token_is_unset(cls, value: object) -> object:
        """docker-compose passes ADMIN_TOKEN=${ADMIN_TOKEN:-} as an empty string."""
        if isinstance(value, str) and not value.strip():
            return None
        return value

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
