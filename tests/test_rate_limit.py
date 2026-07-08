"""Tests for RateLimitMiddleware — in-memory limiter, Redis limiter, 429 behavior."""

from __future__ import annotations

import asyncio

from conftest import REDIS_TEST_URL
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.middleware.rate_limit import (
    _MAX_TRACKED_KEYS,
    InMemoryRateLimiter,
    RateLimitConfig,
    RateLimitMiddleware,
    RedisRateLimiter,
)


def _make_app(
    config: RateLimitConfig, limiter=None, trust_proxy_headers: bool = False  # noqa: ANN001
) -> FastAPI:
    app = FastAPI()

    @app.get("/ping")
    def ping() -> dict[str, bool]:
        return {"ok": True}

    @app.get("/health")
    def health() -> dict[str, bool]:
        return {"ok": True}

    app.add_middleware(
        RateLimitMiddleware,
        config=config,
        limiter=limiter,
        trust_proxy_headers=trust_proxy_headers,
    )
    return app


# ── In-memory limiter ─────────────────────────────────────────────────────────

async def test_in_memory_limiter_allows_up_to_the_limit() -> None:
    limiter = InMemoryRateLimiter()
    config = RateLimitConfig(requests_per_window=3, window_seconds=60)

    results = [await limiter.is_allowed("client-a", config) for _ in range(3)]
    assert results == [True, True, True]
    assert await limiter.is_allowed("client-a", config) is False


async def test_in_memory_limiter_evicts_oldest_key_once_at_cap() -> None:
    """Regression test: a spoofable key (X-Forwarded-For) must not let a
    caller grow tracked state without bound."""
    limiter = InMemoryRateLimiter()
    config = RateLimitConfig(requests_per_window=5, window_seconds=60)

    await limiter.is_allowed("first-client", config)
    for i in range(_MAX_TRACKED_KEYS):
        await limiter.is_allowed(f"client-{i}", config)

    assert len(limiter._windows) == _MAX_TRACKED_KEYS
    assert "first-client" not in limiter._windows


async def test_in_memory_limiter_tracks_keys_independently() -> None:
    limiter = InMemoryRateLimiter()
    config = RateLimitConfig(requests_per_window=1, window_seconds=60)

    assert await limiter.is_allowed("client-a", config) is True
    assert await limiter.is_allowed("client-b", config) is True
    assert await limiter.is_allowed("client-a", config) is False


async def test_in_memory_limiter_evicts_expired_entries() -> None:
    limiter = InMemoryRateLimiter()
    # Window shorter than the sleep below — the first timestamp must be
    # expired and evicted by the time the second call is made.
    config = RateLimitConfig(requests_per_window=1, window_seconds=1)

    assert await limiter.is_allowed("client-a", config) is True
    assert await limiter.is_allowed("client-a", config) is False
    await asyncio.sleep(1.05)
    assert await limiter.is_allowed("client-a", config) is True


# ── Middleware behavior ───────────────────────────────────────────────────────

def test_middleware_returns_429_over_limit() -> None:
    app = _make_app(RateLimitConfig(requests_per_window=2, window_seconds=60))
    with TestClient(app) as client:
        assert client.get("/ping").status_code == 200
        assert client.get("/ping").status_code == 200
        third = client.get("/ping")
        assert third.status_code == 429
        assert "Retry-After" in third.headers


def test_middleware_exempts_health_and_metrics() -> None:
    app = _make_app(RateLimitConfig(requests_per_window=1, window_seconds=60))
    with TestClient(app) as client:
        for _ in range(5):
            assert client.get("/health").status_code == 200


def test_middleware_keys_by_x_forwarded_for_when_trusted() -> None:
    """Only honor X-Forwarded-For when the deployment has opted in via
    trust_proxy_headers=True (i.e. a reverse proxy sits in front)."""
    app = _make_app(
        RateLimitConfig(requests_per_window=1, window_seconds=60), trust_proxy_headers=True
    )
    with TestClient(app) as client:
        assert client.get("/ping", headers={"X-Forwarded-For": "1.1.1.1"}).status_code == 200
        assert client.get("/ping", headers={"X-Forwarded-For": "2.2.2.2"}).status_code == 200
        assert client.get("/ping", headers={"X-Forwarded-For": "1.1.1.1"}).status_code == 429


def test_middleware_uses_rightmost_forwarded_hop_when_trusted() -> None:
    """The leftmost X-Forwarded-For entry is attacker-controllable; a
    well-behaved proxy appends the real client IP as the last hop."""
    app = _make_app(
        RateLimitConfig(requests_per_window=1, window_seconds=60), trust_proxy_headers=True
    )
    with TestClient(app) as client:
        assert (
            client.get("/ping", headers={"X-Forwarded-For": "spoofed, 9.9.9.9"}).status_code
            == 200
        )
        # Same real (rightmost) hop, different spoofed prefix — still one bucket.
        assert (
            client.get("/ping", headers={"X-Forwarded-For": "other-spoof, 9.9.9.9"}).status_code
            == 429
        )


def test_middleware_ignores_x_forwarded_for_by_default() -> None:
    """Regression test: without trust_proxy_headers, a caller can't reset
    their own rate-limit bucket by sending a fresh spoofed X-Forwarded-For
    on every request — the key falls back to the socket peer address."""
    app = _make_app(RateLimitConfig(requests_per_window=1, window_seconds=60))
    with TestClient(app) as client:
        assert client.get("/ping", headers={"X-Forwarded-For": "1.1.1.1"}).status_code == 200
        assert client.get("/ping", headers={"X-Forwarded-For": "2.2.2.2"}).status_code == 429


# ── Redis limiter ──────────────────────────────────────────────────────────────

async def test_redis_limiter_allows_up_to_the_limit(redis_client) -> None:  # noqa: ANN001
    limiter = RedisRateLimiter(redis_url=REDIS_TEST_URL)
    config = RateLimitConfig(requests_per_window=3, window_seconds=60)

    results = [await limiter.is_allowed("client-a", config) for _ in range(3)]
    assert results == [True, True, True]
    assert await limiter.is_allowed("client-a", config) is False
    await limiter.close()


async def test_redis_limiter_shared_across_instances(redis_client) -> None:  # noqa: ANN001
    """Two limiter instances pointed at the same Redis share one counter —
    this is the whole point of the Redis backend: every replica agrees."""
    config = RateLimitConfig(requests_per_window=2, window_seconds=60)
    limiter_a = RedisRateLimiter(redis_url=REDIS_TEST_URL)
    limiter_b = RedisRateLimiter(redis_url=REDIS_TEST_URL)

    assert await limiter_a.is_allowed("shared-client", config) is True
    assert await limiter_b.is_allowed("shared-client", config) is True
    assert await limiter_a.is_allowed("shared-client", config) is False

    await limiter_a.close()
    await limiter_b.close()


async def test_redis_limiter_tracks_keys_independently(redis_client) -> None:  # noqa: ANN001
    limiter = RedisRateLimiter(redis_url=REDIS_TEST_URL)
    config = RateLimitConfig(requests_per_window=1, window_seconds=60)

    assert await limiter.is_allowed("client-a", config) is True
    assert await limiter.is_allowed("client-b", config) is True
    assert await limiter.is_allowed("client-a", config) is False
    await limiter.close()
