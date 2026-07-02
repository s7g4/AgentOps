"""Sliding-window rate limiter middleware.

Algorithm: sliding window counter
──────────────────────────────────
Each caller gets a fixed-size time window (default: 60 seconds, 100 requests).
On each request:
  1. Remove timestamps older than ``window_seconds``.
  2. If ``len(window) >= limit``: reject with 429.
  3. Else: append current timestamp and allow.

Why sliding window over fixed window?
  Fixed windows allow 2× the limit at window boundaries (burst at end of
  old window + start of new).  Sliding window prevents this by always
  looking at the last N seconds, not the current calendar minute.

Why in-memory over Redis for V2?
  Redis rate limiting requires atomic Lua scripts or MULTI/EXEC transactions.
  In-memory works for single-instance deployments and avoids a hard Redis
  dependency for rate limiting.  Redis-backed rate limiting will be added
  in V3 alongside the workflow engine (which already requires Redis).

Rate limit key: client IP address (``X-Forwarded-For`` → ``request.client.host``).
For customer-level rate limiting, the key should be ``customer_id`` from the
request body — this is done in the ``/messages`` endpoint handler directly.
"""

from __future__ import annotations

import asyncio
import time
from collections import deque
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from fastapi import Request, Response
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

# Paths that are never rate-limited.
_EXEMPT_PATHS: frozenset[str] = frozenset({"/health", "/metrics"})

# Global in-memory state (per process).
_WINDOWS: dict[str, deque[float]] = {}
_LOCK = asyncio.Lock()


@dataclass
class RateLimitConfig:
    requests_per_window: int = 100
    window_seconds: int = 60


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Per-IP sliding-window rate limiter.

    Returns 429 with ``Retry-After`` header when the limit is exceeded.
    """

    def __init__(self, app: object, config: RateLimitConfig | None = None) -> None:
        super().__init__(app)  # type: ignore[arg-type]
        self.config = config or RateLimitConfig()

    async def dispatch(
        self, request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        if request.url.path in _EXEMPT_PATHS:
            return await call_next(request)

        key = self._get_key(request)
        allowed = await self._is_allowed(key)

        if not allowed:
            return JSONResponse(
                status_code=429,
                content={
                    "error": "Too Many Requests",
                    "detail": (
                        f"Rate limit: {self.config.requests_per_window} requests "
                        f"per {self.config.window_seconds}s"
                    ),
                },
                headers={"Retry-After": str(self.config.window_seconds)},
            )

        return await call_next(request)

    def _get_key(self, request: Request) -> str:
        # Respect X-Forwarded-For if behind a proxy.
        forwarded_for = request.headers.get("X-Forwarded-For")
        if forwarded_for:
            return forwarded_for.split(",")[0].strip()
        if request.client:
            return request.client.host
        return "unknown"

    async def _is_allowed(self, key: str) -> bool:
        now = time.monotonic()
        cfg = self.config
        async with _LOCK:
            if key not in _WINDOWS:
                _WINDOWS[key] = deque()
            window = _WINDOWS[key]
            # Evict expired timestamps.
            cutoff = now - cfg.window_seconds
            while window and window[0] < cutoff:
                window.popleft()
            if len(window) >= cfg.requests_per_window:
                return False
            window.append(now)
            return True
