"""API key authentication middleware.

Design
──────
API keys are compared using ``hmac.compare_digest`` (constant-time comparison)
to prevent timing attacks.  A naive ``==`` comparison leaks key length via
timing differences — compare_digest eliminates this.  We check the provided
key against every configured key rather than short-circuiting on the first
match/mismatch, so the response time doesn't leak how many keys are
configured or which position a match was found at.

Multiple keys (``API_KEYS``, comma-separated) exist so different callers —
or an old and new key mid-rotation — each hold a distinct, independently
revocable credential, without needing per-tenant infrastructure. The legacy
single ``API_KEY`` is folded into the same set (see ``Settings.valid_api_keys``).
This is deliberately simpler than JWT/OAuth: there's no session state or
expiry to manage because there's no notion of a logged-in user, just a
caller presenting a shared secret.

The middleware is opt-in (``AUTH_ENABLED=false`` by default) so developers
can run locally without configuration.  In any production deployment,
``AUTH_ENABLED=true`` and at least one key must be set.

Excluded paths (``/health``, ``/metrics``) are always unauthenticated so
Kubernetes liveness probes and Prometheus scrapers don't need credentials.

Why middleware over FastAPI Depends?
── Middleware catches ALL routes including ones added by third-party routers.
── It returns a consistent 401 JSON structure regardless of route.
── It avoids duplicating ``Depends(verify_api_key)`` on every endpoint.
"""

from __future__ import annotations

import hmac
import logging
from collections.abc import Awaitable, Callable

from fastapi import Request, Response
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from app.config.settings import load_settings
from app.exceptions import ConfigurationError

logger = logging.getLogger(__name__)

# Paths that bypass authentication — health checks and metrics scrapers.
_OPEN_PATHS: frozenset[str] = frozenset({"/health", "/metrics", "/docs", "/openapi.json"})


def _matches_any(provided: str, keys: frozenset[str]) -> bool:
    """Constant-time membership check against every configured key.

    Iterates the full set instead of stopping at the first match so timing
    doesn't correlate with which key (if any) matched.
    """
    provided_bytes = provided.encode()
    matched = False
    for key in keys:
        if hmac.compare_digest(provided_bytes, key.encode()):
            matched = True
    return matched


class APIKeyMiddleware(BaseHTTPMiddleware):
    """Validate ``X-Api-Key`` header on every request (when auth is enabled)."""

    async def dispatch(
        self, request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        settings = load_settings()

        if not settings.auth_enabled:
            return await call_next(request)

        if request.url.path in _OPEN_PATHS:
            return await call_next(request)

        valid_keys = settings.valid_api_keys()
        if not valid_keys:
            raise ConfigurationError(
                "AUTH_ENABLED=true but no API key is configured. "
                "Set API_KEYS (or the legacy API_KEY) in your environment or .env file."
            )

        provided = request.headers.get("X-Api-Key", "")

        if not provided or not _matches_any(provided, valid_keys):
            logger.warning(
                "auth_rejected",
                extra={"path": request.url.path, "client": _client_ip(request)},
            )
            return JSONResponse(
                status_code=401,
                content={"error": "Unauthorized", "detail": "Invalid or missing API key"},
            )

        logger.info("auth_ok", extra={"path": request.url.path})
        return await call_next(request)


def _client_ip(request: Request) -> str:
    forwarded_for = request.headers.get("X-Forwarded-For")
    if forwarded_for:
        return forwarded_for.split(",")[0].strip()
    return request.client.host if request.client else "unknown"
