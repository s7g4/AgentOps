"""API key authentication middleware.

Design
──────
API keys are compared using ``hmac.compare_digest`` (constant-time comparison)
to prevent timing attacks.  A naive ``==`` comparison leaks key length via
timing differences — compare_digest eliminates this.

The middleware is opt-in (``AUTH_ENABLED=false`` by default) so developers
can run locally without configuration.  In any production deployment,
``AUTH_ENABLED=true`` and ``API_KEY`` must be set.

Excluded paths (``/health``, ``/metrics``) are always unauthenticated so
Kubernetes liveness probes and Prometheus scrapers don't need credentials.

Why middleware over FastAPI Depends?
── Middleware catches ALL routes including ones added by third-party routers.
── It returns a consistent 401 JSON structure regardless of route.
── It avoids duplicating ``Depends(verify_api_key)`` on every endpoint.
"""

from __future__ import annotations

import hmac

from fastapi import Request, Response
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from app.config.settings import load_settings
from app.exceptions import ConfigurationError

# Paths that bypass authentication — health checks and metrics scrapers.
_OPEN_PATHS: frozenset[str] = frozenset({"/health", "/metrics", "/docs", "/openapi.json"})


class APIKeyMiddleware(BaseHTTPMiddleware):
    """Validate ``X-Api-Key`` header on every request (when auth is enabled)."""

    async def dispatch(self, request: Request, call_next: object) -> Response:
        from collections.abc import Callable  # noqa: PLC0415

        call_next_fn: Callable[..., object] = call_next  # type: ignore[assignment]
        settings = load_settings()

        if not settings.auth_enabled:
            return await call_next_fn(request)  # type: ignore[return-value]

        if request.url.path in _OPEN_PATHS:
            return await call_next_fn(request)  # type: ignore[return-value]

        if not settings.api_key:
            raise ConfigurationError(
                "AUTH_ENABLED=true but API_KEY is not configured. "
                "Set API_KEY in your environment or .env file."
            )

        provided = request.headers.get("X-Api-Key", "")
        expected = settings.api_key

        # constant-time comparison — prevents timing oracle attacks
        if not hmac.compare_digest(provided.encode(), expected.encode()):
            return JSONResponse(
                status_code=401,
                content={"error": "Unauthorized", "detail": "Invalid or missing API key"},
            )

        return await call_next_fn(request)  # type: ignore[return-value]
