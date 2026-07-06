"""Tests for RedisTraceStore against a real Redis instance.

Skipped automatically when no Redis is reachable (see conftest.redis_client).
CI always has one; local runs without Docker just skip these.
"""

from __future__ import annotations

from conftest import REDIS_TEST_URL

from app.runtime.trace_store import RedisTraceStore
from app.schemas.trace import Trace, TraceEvent


def _make_trace(trace_id: str = "abc") -> Trace:
    trace = Trace(trace_id=trace_id)
    event = TraceEvent(timestamp="2026-01-01T00:00:00Z", name="state:received", data={})
    trace.timeline.append(event)
    return trace


async def test_put_and_get_roundtrip(redis_client) -> None:  # noqa: ANN001
    store = RedisTraceStore(redis_url=REDIS_TEST_URL)
    trace = _make_trace("redis-t1")

    await store.put(trace)
    fetched = await store.get("redis-t1")

    assert fetched is not None
    assert fetched.trace_id == "redis-t1"
    assert len(fetched.timeline) == 1
    await store.close()


async def test_get_missing_returns_none(redis_client) -> None:  # noqa: ANN001
    store = RedisTraceStore(redis_url=REDIS_TEST_URL)
    assert await store.get("does-not-exist") is None
    await store.close()


async def test_count_and_list_most_recent_first(redis_client) -> None:  # noqa: ANN001
    store = RedisTraceStore(redis_url=REDIS_TEST_URL)
    for tid in ("t1", "t2", "t3"):
        await store.put(_make_trace(tid))

    assert await store.count() == 3
    traces = await store.list_traces(limit=10)
    assert [t.trace_id for t in traces] == ["t3", "t2", "t1"]
    await store.close()


async def test_list_respects_limit_and_offset(redis_client) -> None:  # noqa: ANN001
    store = RedisTraceStore(redis_url=REDIS_TEST_URL)
    for i in range(5):
        await store.put(_make_trace(f"x{i}"))

    page = await store.list_traces(limit=2, offset=1)
    assert len(page) == 2
    await store.close()


async def test_ping_reports_reachable(redis_client) -> None:  # noqa: ANN001
    store = RedisTraceStore(redis_url=REDIS_TEST_URL)
    assert await store.ping() is True
    await store.close()


async def test_ping_reports_unreachable_for_bad_url(redis_client) -> None:  # noqa: ANN001
    store = RedisTraceStore(redis_url="redis://localhost:1/0")
    assert await store.ping() is False
    await store.close()
