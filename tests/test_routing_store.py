"""Tests for InMemoryRoutingStore — basic CRUD, list, limit, offset, count."""

from __future__ import annotations

import asyncio

from app.messaging.message import RoutingResult, SubTaskResult
from app.messaging.routing_store import InMemoryRoutingStore


def _make_routing(routing_id: str, goal: str = "test") -> RoutingResult:
    return RoutingResult(
        routing_id=routing_id,
        goal=goal,
        results=[
            SubTaskResult(
                task_id="t1",
                agent_name="echo",
                status="success",
                duration_ms=10.0,
                output={"msg": "hello"},
            )
        ],
        duration_ms=10.0,
    )


def test_routing_store_put_and_get() -> None:
    store = InMemoryRoutingStore()
    r = _make_routing("r1")

    asyncio.run(store.put(r))

    fetched = asyncio.run(store.get("r1"))
    assert fetched is not None
    assert fetched.routing_id == "r1"
    assert fetched.goal == "test"
    assert len(fetched.results) == 1
    assert fetched.results[0].agent_name == "echo"


def test_routing_store_get_nonexistent() -> None:
    store = InMemoryRoutingStore()
    fetched = asyncio.run(store.get("r2"))
    assert fetched is None


def test_routing_store_list_and_count() -> None:
    store = InMemoryRoutingStore()
    r1 = _make_routing("r1")
    r2 = _make_routing("r2")
    r3 = _make_routing("r3")

    asyncio.run(store.put(r1))
    asyncio.run(store.put(r2))
    asyncio.run(store.put(r3))

    assert asyncio.run(store.count()) == 3

    # list returns most recent first (reversed insertion order)
    routes = asyncio.run(store.list(limit=2, offset=0))
    assert len(routes) == 2
    assert routes[0].routing_id == "r3"
    assert routes[1].routing_id == "r2"

    routes_offset = asyncio.run(store.list(limit=2, offset=2))
    assert len(routes_offset) == 1
    assert routes_offset[0].routing_id == "r1"
