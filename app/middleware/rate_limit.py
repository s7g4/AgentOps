"""Rate limiter middleware — in-memory sliding window or Redis fixed window.

In-memory backend: sliding window counter
──────────────────────────────────────────
Each caller gets a fixed-size time window (default: 60 seconds, 100 requests).
On each request:
  1. Remove timestamps older than ``window_seconds``.
  2. If ``len(window) >= limit``: reject with 429.
  3. Else: append current timestamp and allow.

Why sliding window over fixed window?
  Fixed windows allow 2× the limit at window boundaries (burst at end of
  old window + start of new).  Sliding window prevents this by always
  looking at the last N seconds, not the current calendar minute.

Correct only for a single process — each replica keeps its own counters, so
a caller effectively gets ``limit × replica_count`` requests. Fine for local
dev and single-instance deployments; use the Redis backend the moment more
than one replica sits behind the same host.

Redis backend: fixed window counter
────────────────────────────────────
``INCR`` a per-key, per-window counter and set its expiry on first write.
This is a real approximation, not sliding: a caller can burst up to
``2 × limit`` requests across a window boundary (half at the end of one
window, half at the start of the next). That tradeoff buys a single round
trip per request — no Lua script, no read-modify-write — and it's shared
across every replica, which is the property that actually matters once you
have more than one process answering requests.

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
from typing import Protocol

from fastapi import Request, Response
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

# Paths that are never rate-limited.
_EXEMPT_PATHS: frozenset[str] = frozenset({"/health", "/metrics"})


@dataclass
class RateLimitConfig:
    requests_per_window: int = 100
    window_seconds: int = 60


class RateLimiter(Protocol):
    """Strategy interface — decides whether a caller may proceed."""

    async def is_allowed(self, key: str, config: RateLimitConfig) -> bool: ...


# Caps the number of distinct keys tracked at once. The rate-limit key is
# client-supplied (X-Forwarded-For or socket address) and never cleaned up
# on its own — without a cap, cycling through spoofed header values is an
# unbounded memory-growth vector. Same eviction idiom as TraceStore's
# _MAX_TRACES: oldest tracked key is dropped once the cap is hit.
_MAX_TRACKED_KEYS = 10_000


class InMemoryRateLimiter:
    """Per-process sliding-window limiter. See module docstring for tradeoffs."""

    def __init__(self) -> None:
        self._windows: dict[str, deque[float]] = {}
        self._lock = asyncio.Lock()

    async def is_allowed(self, key: str, config: RateLimitConfig) -> bool:
        now = time.monotonic()
        async with self._lock:
            window = self._windows.get(key)
            if window is None:
                if len(self._windows) >= _MAX_TRACKED_KEYS:
                    del self._windows[next(iter(self._windows))]
                window = deque()

            cutoff = now - config.window_seconds
            while window and window[0] < cutoff:
                window.popleft()

            if len(window) >= config.requests_per_window:
                self._windows[key] = window
                return False

            window.append(now)
            self._windows[key] = window
            return True


class RedisRateLimiter:
    """Shared fixed-window limiter backed by Redis. See module docstring."""

    _PREFIX = "agentops:ratelimit:"

    def __init__(self, redis_url: str) -> None:
        import redis.asyncio as aioredis  # noqa: PLC0415

        self._redis = aioredis.from_url(redis_url, decode_responses=True)

    async def is_allowed(self, key: str, config: RateLimitConfig) -> bool:
        window_id = int(time.time()) // config.window_seconds
        redis_key = f"{self._PREFIX}{key}:{window_id}"

        async with self._redis.pipeline(transaction=True) as pipe:
            pipe.incr(redis_key)
            pipe.expire(redis_key, config.window_seconds)
            count, _ = await pipe.execute()

        return int(count) <= config.requests_per_window

    async def close(self) -> None:
        await self._redis.aclose()


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Rejects requests over the configured rate with a 429."""

    def __init__(
        self,
        app: object,
        config: RateLimitConfig | None = None,
        limiter: RateLimiter | None = None,
    ) -> None:
        super().__init__(app)  # type: ignore[arg-type]
        self.config = config or RateLimitConfig()
        self.limiter = limiter or InMemoryRateLimiter()

    async def dispatch(
        self, request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        if request.url.path in _EXEMPT_PATHS:
            return await call_next(request)

        key = self._get_key(request)
        allowed = await self.limiter.is_allowed(key, self.config)

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
