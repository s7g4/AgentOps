from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass, field
from threading import RLock
from typing import Protocol, runtime_checkable

from app.schemas.trace import Trace

# Safety cap: in-memory store evicts oldest entry when this size is reached.
_MAX_TRACES = 10_000


@runtime_checkable
class TraceStoreProtocol(Protocol):
    """Structural protocol satisfied by all async trace store implementations."""

    async def put(self, trace: Trace) -> None: ...
    async def get(self, trace_id: str) -> Trace | None: ...
    async def list(self, limit: int, offset: int) -> list[Trace]: ...
    async def count(self) -> int: ...


class TraceStore:
    """Thread-safe, in-memory async trace store.

    Uses a sync RLock (not asyncio.Lock) because it also supports the legacy
    sync runtime that V1 tests instantiate directly.

    Evicts the oldest entry when ``_MAX_TRACES`` is reached, preventing
    unbounded memory growth in long-running processes.

    For production deployments needing persistence or multi-instance reads,
    use ``RedisTraceStore`` (selected via ``TRACE_BACKEND=redis``).
    """

    def __init__(self) -> None:
        self._lock = RLock()
        self._traces: dict[str, Trace] = {}

    async def put(self, trace: Trace) -> None:
        with self._lock:
            if len(self._traces) >= _MAX_TRACES:
                oldest = next(iter(self._traces))
                del self._traces[oldest]
            self._traces[trace.trace_id] = trace

    async def get(self, trace_id: str) -> Trace | None:
        with self._lock:
            return self._traces.get(trace_id)

    async def list(self, limit: int = 100, offset: int = 0) -> list[Trace]:
        """Return a paginated slice of traces, most recent first."""
        with self._lock:
            all_traces = list(reversed(list(self._traces.values())))
            return all_traces[offset : offset + limit]

    async def count(self) -> int:
        with self._lock:
            return len(self._traces)

    # Synchronous accessors kept for backward-compat with V1 tests.
    def put_sync(self, trace: Trace) -> None:
        with self._lock:
            if len(self._traces) >= _MAX_TRACES:
                oldest = next(iter(self._traces))
                del self._traces[oldest]
            self._traces[trace.trace_id] = trace

    def get_sync(self, trace_id: str) -> Trace | None:
        with self._lock:
            return self._traces.get(trace_id)

    def list_sync(self, limit: int = 100, offset: int = 0) -> list[Trace]:
        with self._lock:
            all_traces = list(reversed(list(self._traces.values())))
            return all_traces[offset : offset + limit]

    def count_sync(self) -> int:
        with self._lock:
            return len(self._traces)

    @classmethod
    def default(cls) -> TraceStore:
        return cls()


class RedisTraceStore:
    """Redis-backed async trace store.

    Traces are serialised to JSON and stored as Redis strings with an
    optional TTL.  A separate sorted-set (``agentops:traces:index``) keyed
    by creation timestamp enables fast paginated listing.

    Why Redis?
    ──────────
    • Persistence across restarts
    • Multi-instance support (all replicas share state)
    • Built-in TTL for automatic expiry (default: 7 days)
    • O(log N) sorted-set operations for ordered pagination

    Requires: ``redis>=5.0.0`` with asyncio support.
    """

    _KEY_PREFIX = "agentops:trace:"
    _INDEX_KEY = "agentops:traces:index"
    _DEFAULT_TTL = 7 * 24 * 3600  # 7 days

    def __init__(self, redis_url: str, ttl_seconds: int = _DEFAULT_TTL) -> None:
        import redis.asyncio as aioredis  # lazy import: only needed if Redis is configured

        self._redis = aioredis.from_url(redis_url, decode_responses=True)
        self._ttl = ttl_seconds

    async def put(self, trace: Trace) -> None:
        import time  # noqa: PLC0415

        key = f"{self._KEY_PREFIX}{trace.trace_id}"
        payload = json.dumps(trace.to_dict())
        ts = time.time()
        async with self._redis.pipeline(transaction=True) as pipe:
            pipe.set(key, payload, ex=self._ttl)
            pipe.zadd(self._INDEX_KEY, {trace.trace_id: ts})
            pipe.expire(self._INDEX_KEY, self._ttl)
            await pipe.execute()

    async def get(self, trace_id: str) -> Trace | None:
        key = f"{self._KEY_PREFIX}{trace_id}"
        raw = await self._redis.get(key)
        if raw is None:
            return None
        return Trace.from_dict(json.loads(raw))

    async def list(self, limit: int = 100, offset: int = 0) -> list[Trace]:
        """Return traces ordered by insertion time, most recent first."""
        # ZREVRANGEBYSCORE for newest-first ordering.
        ids: list[str] = await self._redis.zrevrange(
            self._INDEX_KEY, offset, offset + limit - 1
        )
        if not ids:
            return []
        keys = [f"{self._KEY_PREFIX}{tid}" for tid in ids]
        raws = await self._redis.mget(*keys)
        return [
            Trace.from_dict(json.loads(r)) for r in raws if r is not None
        ]

    async def count(self) -> int:
        return await self._redis.zcard(self._INDEX_KEY)

    async def ping(self) -> bool:
        """Return True if Redis is reachable — used by health check."""
        try:
            await self._redis.ping()
            return True
        except Exception:  # noqa: BLE001
            return False

    async def close(self) -> None:
        await self._redis.aclose()
