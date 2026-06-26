from __future__ import annotations

from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables and optional .env file.

    All fields are validated at startup — the application will refuse to start
    if required values are missing or have the wrong type.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    app_name: str = "AgentOps"
    host: str = "0.0.0.0"  # noqa: S104
    port: int = Field(default=8000, ge=1, le=65535)
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "INFO"

    # Optional integrations — absence is acceptable; presence enables features.
    openai_api_key: str | None = Field(default=None, repr=False)
    redis_url: str | None = None

    # Trace backend: "memory" for tests/local, "redis" for production.
    trace_backend: Literal["memory", "redis"] = "memory"

    # Auth — disabled by default for local dev; always enable in production.
    auth_enabled: bool = False
    api_key: str | None = Field(default=None, repr=False)


_settings: Settings | None = None


def load_settings() -> Settings:
    """Return the singleton Settings instance, creating it on first call."""
    global _settings  # noqa: PLW0603
    if _settings is None:
        _settings = Settings()
    return _settings


def override_settings(settings: Settings) -> None:
    """Replace the singleton — only for use in tests."""
    global _settings  # noqa: PLW0603
    _settings = settings
