from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime settings loaded from environment variables.

    Defaults are intentionally safe for local development: publishing is disabled,
    the model provider is deterministic, and credentials have no fallback key.
    """

    model_config = SettingsConfigDict(
        env_file=("../.env", ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    app_name: str = "FirstComment Agent"
    app_env: Literal["development", "test", "staging", "production"] = "development"
    app_secret_key: SecretStr = SecretStr("local-development-only-change-me")
    api_v1_prefix: str = "/api/v1"
    frontend_origin: str = "http://localhost:3000"

    database_url: str = "postgresql+asyncpg://app:app@localhost:5432/firstcomment"
    database_echo: bool = False
    database_pool_size: int = Field(default=10, ge=1, le=100)
    database_max_overflow: int = Field(default=20, ge=0, le=200)
    redis_url: str = "redis://localhost:6379/0"

    token_encryption_key: SecretStr | None = None
    token_encryption_key_version: int = Field(default=1, ge=1)
    access_token_ttl_minutes: int = Field(default=60, ge=5, le=1440)
    jwt_algorithm: Literal["HS256", "HS384", "HS512"] = "HS256"

    llm_provider: str = "mock"
    llm_api_key: SecretStr | None = None
    llm_api_base: str = "https://api.openai.com/v1"
    llm_model_fast: str = "mock-fast-v1"
    llm_model_normal: str = "mock-normal-v1"
    llm_timeout_seconds: float = Field(default=5.0, gt=0, le=60)

    auto_publish_default: bool = False
    comment_mode: Literal["REVIEW", "AUTO"] = "REVIEW"
    risk_allow_threshold: float = Field(default=0.30, ge=0, le=1)
    risk_block_threshold: float = Field(default=0.65, ge=0, le=1)
    quality_allow_threshold: float = Field(default=0.80, ge=0, le=1)
    quality_review_threshold: float = Field(default=0.65, ge=0, le=1)
    duplicate_block_threshold: float = Field(default=0.90, ge=0, le=1)
    duplicate_review_threshold: float = Field(default=0.82, ge=0, le=1)

    sse_heartbeat_seconds: int = Field(default=15, ge=5, le=120)
    log_level: str = "INFO"
    log_json: bool = True

    @model_validator(mode="after")
    def require_deployment_secret(self) -> Settings:
        if self.app_env in {"staging", "production"}:
            secret = self.app_secret_key.get_secret_value()
            if (
                len(secret.encode("utf-8")) < 32
                or len(set(secret)) < 8
                or secret.lower() in {
                    "local-development-only-change-me",
                    "development-only-change-me",
                }
            ):
                raise ValueError(
                    "APP_SECRET_KEY must be a randomly generated secret of at least "
                    "32 bytes in staging and production; development defaults are forbidden"
                )
        return self

    @field_validator("api_v1_prefix")
    @classmethod
    def validate_api_prefix(cls, value: str) -> str:
        normalized = "/" + value.strip("/")
        return normalized.rstrip("/")

    @property
    def cors_origins(self) -> list[str]:
        return [item.strip() for item in self.frontend_origin.split(",") if item.strip()]

    @field_validator("database_url")
    @classmethod
    def require_async_database_driver(cls, value: str) -> str:
        if value.startswith("postgresql://"):
            return value.replace("postgresql://", "postgresql+asyncpg://", 1)
        return value


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
