"""Tests for RedisRoutingStore against a real Redis instance.

Skipped automatically when no Redis is reachable (see conftest.redis_client).
"""

from __future__ import annotations

from conftest import REDIS_TEST_URL

from app.messaging.message import RoutingResult, SubTaskResult
from app.messaging.routing_store import RedisRoutingStore


def _make_routing(routing_id: str, goal: str = "test goal") -> RoutingResult:
    return RoutingResult(
        routing_id=routing_id,
        goal=goal,
        results=[
            SubTaskResult(
                task_id="t1",
                agent_name="echo",
                status="success",
                duration_ms=5.0,
                output={"msg": "hello"},
            )
        ],
        duration_ms=5.0,
    )


async def test_put_and_get_roundtrip(redis_client) -> None:  # noqa: ANN001
    store = RedisRoutingStore(redis_url=REDIS_TEST_URL)
    result = _make_routing("r1")

    await store.put(result)
    fetched = await store.get("r1")

    assert fetched is not None
    assert fetched.goal == "test goal"
    assert fetched.results[0].agent_name == "echo"
    assert fetched.status == "completed"
    await store.close()


async def test_get_missing_returns_none(redis_client) -> None:  # noqa: ANN001
    store = RedisRoutingStore(redis_url=REDIS_TEST_URL)
    assert await store.get("nope") is None
    await store.close()


async def test_list_most_recent_first_and_count(redis_client) -> None:  # noqa: ANN001
    store = RedisRoutingStore(redis_url=REDIS_TEST_URL)
    for rid in ("r1", "r2", "r3"):
        await store.put(_make_routing(rid))

    assert await store.count() == 3
    listed = await store.list(limit=10, offset=0)
    assert [r.routing_id for r in listed] == ["r3", "r2", "r1"]
    await store.close()


async def test_list_respects_pagination(redis_client) -> None:  # noqa: ANN001
    store = RedisRoutingStore(redis_url=REDIS_TEST_URL)
    for i in range(5):
        await store.put(_make_routing(f"r{i}"))

    page = await store.list(limit=2, offset=2)
    assert len(page) == 2
    await store.close()
