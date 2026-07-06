from __future__ import annotations

from typing import Literal

from pydantic import Field, field_validator
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

    # Rate limiting backend: "memory" is correct for a single process; use
    # "redis" the moment more than one replica sits behind the same host,
    # otherwise each replica enforces its own independent limit.
    rate_limit_backend: Literal["memory", "redis"] = "memory"

    # Auth — disabled by default for local dev; always enable in production.
    # API_KEYS accepts a comma-separated list so multiple callers (or a key
    # rotation in progress) can each hold a distinct, individually revocable
    # credential. API_KEY is kept as a single-key fallback for callers who
    # haven't migrated yet — both are folded into one set at validation time.
    auth_enabled: bool = False
    api_key: str | None = Field(default=None, repr=False)
    api_keys: str = Field(default="", repr=False)

    # OpenTelemetry — disabled by default; opt-in for production observability.
    # When enabled, traces are exported to the configured OTLP gRPC endpoint.
    otel_enabled: bool = False
    otel_endpoint: str = "http://localhost:4317"
    otel_service_name: str = "agentops"

    @field_validator("api_keys", mode="before")
    @classmethod
    def _normalise_api_keys(cls, v: object) -> str:
        return "" if v is None else str(v)

    def valid_api_keys(self) -> frozenset[str]:
        """Return every configured API key as a single set.

        Merges the legacy single ``api_key`` with the comma-separated
        ``api_keys`` list, stripping whitespace and dropping empties so a
        trailing comma or blank env var doesn't produce a key that matches
        an empty ``X-Api-Key`` header.
        """
        keys = {k.strip() for k in self.api_keys.split(",") if k.strip()}
        if self.api_key:
            keys.add(self.api_key)
        return frozenset(keys)


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
