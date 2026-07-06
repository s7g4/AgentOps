"""Routing history store interface and implementations.

Supports two namespaces / storage backends:
- InMemoryRoutingStore (default, for tests and local development)
- RedisRoutingStore (production, configuration-driven, with 30-day TTL)
"""

from __future__ import annotations

import json
import time
from threading import RLock
from typing import Protocol, cast, runtime_checkable

from app.messaging.message import RoutingResult, SubTaskResult

_ROUTING_TTL = 30 * 24 * 3600  # 30 days


@runtime_checkable
class RoutingStoreProtocol(Protocol):
    """Protocol for routing result storage."""

    async def put(self, result: RoutingResult) -> None: ...
    async def get(self, routing_id: str) -> RoutingResult | None: ...
    async def list(self, limit: int, offset: int) -> list[RoutingResult]: ...
    async def count(self) -> int: ...


class InMemoryRoutingStore:
    """Thread-safe in-memory store for routing results."""

    def __init__(self) -> None:
        self._lock = RLock()
        self._routes: dict[str, RoutingResult] = {}
        self._order: list[str] = []

    async def put(self, result: RoutingResult) -> None:
        with self._lock:
            if result.routing_id not in self._routes:
                self._order.append(result.routing_id)
            self._routes[result.routing_id] = result

    async def get(self, routing_id: str) -> RoutingResult | None:
        with self._lock:
            return self._routes.get(routing_id)

    async def list(self, limit: int = 20, offset: int = 0) -> list[RoutingResult]:
        with self._lock:
            ordered = list(reversed(self._order))
            page = ordered[offset : offset + limit]
            return [self._routes[rid] for rid in page if rid in self._routes]

    async def count(self) -> int:
        with self._lock:
            return len(self._routes)


class RedisRoutingStore:
    """Redis-backed storage for routing results."""

    _PREFIX = "agentops:routing:"
    _INDEX = "agentops:routings:index"

    def __init__(self, redis_url: str, ttl_seconds: int = _ROUTING_TTL) -> None:
        import redis.asyncio as aioredis  # noqa: PLC0415

        self._redis = aioredis.from_url(redis_url, decode_responses=True)
        self._ttl = ttl_seconds

    async def put(self, result: RoutingResult) -> None:
        key = f"{self._PREFIX}{result.routing_id}"
        ts = time.time()

        serialized = {
            "routing_id": result.routing_id,
            "goal": result.goal,
            "created_at": result.created_at,
            "duration_ms": result.duration_ms,
            "results": [r.to_dict() for r in result.results],
        }

        async with self._redis.pipeline(transaction=True) as pipe:
            pipe.set(key, json.dumps(serialized), ex=self._ttl)
            pipe.zadd(self._INDEX, {result.routing_id: ts}, nx=True)
            pipe.expire(self._INDEX, self._ttl)
            await pipe.execute()

    async def get(self, routing_id: str) -> RoutingResult | None:
        raw = await self._redis.get(f"{self._PREFIX}{routing_id}")
        if not raw:
            return None

        parsed = json.loads(raw)
        results = [
            SubTaskResult(
                task_id=r["task_id"],
                agent_name=r["agent_name"],
                status=r["status"],
                output=r.get("output"),
                error=r.get("error"),
                duration_ms=r["duration_ms"],
            )
            for r in parsed.get("results", [])
        ]

        return RoutingResult(
            routing_id=parsed["routing_id"],
            goal=parsed["goal"],
            results=results,
            duration_ms=parsed["duration_ms"],
            created_at=parsed["created_at"],
        )

    async def list(self, limit: int = 20, offset: int = 0) -> list[RoutingResult]:
        # decode_responses=True guarantees str members at runtime; the redis-py
        # stubs type zrevrange's return generically because withscores can
        # change the shape.
        ids = cast(
            "list[str]", await self._redis.zrevrange(self._INDEX, offset, offset + limit - 1)
        )
        if not ids:
            return []

        keys = [f"{self._PREFIX}{rid}" for rid in ids]
        raws = await self._redis.mget(*keys)

        routes: list[RoutingResult] = []
        for raw in raws:
            if not raw:
                continue
            parsed = json.loads(raw)
            results = [
                SubTaskResult(
                    task_id=r["task_id"],
                    agent_name=r["agent_name"],
                    status=r["status"],
                    output=r.get("output"),
                    error=r.get("error"),
                    duration_ms=r["duration_ms"],
                )
                for r in parsed.get("results", [])
            ]
            routes.append(
                RoutingResult(
                    routing_id=parsed["routing_id"],
                    goal=parsed["goal"],
                    results=results,
                    duration_ms=parsed["duration_ms"],
                    created_at=parsed["created_at"],
                )
            )
        return routes

    async def count(self) -> int:
        return await self._redis.zcard(self._INDEX)

    async def close(self) -> None:
        await self._redis.aclose()
