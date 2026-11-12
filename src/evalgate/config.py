"""Runtime settings loaded from the environment (and ``.env`` when present)."""

from __future__ import annotations

from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Environment-backed configuration.

    Host ports default to the EvalGate-reserved ports (5434/6381/8001) so parallel local
    stacks do not collide. CI overrides the service URLs to 5432/6379.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    database_url: str = "postgresql+asyncpg://evalgate:evalgate@localhost:5434/evalgate"
    redis_url: str = "redis://localhost:6381/0"

    openai_api_key: str | None = None
    openai_base_url: str = "https://api.openai.com/v1"
    anthropic_api_key: str | None = None
    anthropic_base_url: str = "https://api.anthropic.com"

    evalgate_api_key: str = "dev-key"
    evalgate_api_port: int = 8001

    judge_model: str = "gpt-4.1-mini"
    judge_cache_dir: Path = Field(default=Path(".evalgate-cache"))

    provider_timeout_s: float = 60.0
    provider_max_attempts: int = 4


def get_settings() -> Settings:
    """Load settings; kept as a function so tests can construct their own instance."""

    return Settings()
