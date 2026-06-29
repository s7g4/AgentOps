"""Tests for TraceStore: async, thread-safety, pagination, eviction cap."""
from __future__ import annotations

import threading

from app.runtime.trace_store import TraceStore, _MAX_TRACES
from app.schemas.trace import Trace


def _make_trace(trace_id: str = "abc") -> Trace:
    return Trace(trace_id=trace_id)


class TestTraceStorePutGet:
    async def test_put_and_get_roundtrip(self) -> None:
        store = TraceStore()
        trace = _make_trace("t1")
        await store.put(trace)
        assert await store.get("t1") is trace

    async def test_get_missing_returns_none(self) -> None:
        store = TraceStore()
        assert await store.get("nonexistent") is None

    async def test_put_overwrites_existing(self) -> None:
        store = TraceStore()
        t1 = _make_trace("dup")
        t2 = _make_trace("dup")
        await store.put(t1)
        await store.put(t2)
        assert await store.get("dup") is t2

    async def test_count(self) -> None:
        store = TraceStore()
        assert await store.count() == 0
        await store.put(_make_trace("a"))
        await store.put(_make_trace("b"))
        assert await store.count() == 2


class TestTraceStoreList:
    async def test_list_empty(self) -> None:
        store = TraceStore()
        assert await store.list() == []

    async def test_list_returns_traces(self) -> None:
        store = TraceStore()
        for tid in ["x1", "x2", "x3"]:
            await store.put(_make_trace(tid))
        result = await store.list(limit=10)
        assert len(result) == 3

    async def test_list_limit(self) -> None:
        store = TraceStore()
        for i in range(10):
            await store.put(_make_trace(str(i)))
        result = await store.list(limit=3)
        assert len(result) == 3

    async def test_list_offset(self) -> None:
        store = TraceStore()
        for i in range(5):
            await store.put(_make_trace(str(i)))
        result = await store.list(limit=100, offset=3)
        assert len(result) == 2

    async def test_list_most_recent_first(self) -> None:
        store = TraceStore()
        await store.put(_make_trace("first"))
        await store.put(_make_trace("second"))
        result = await store.list()
        assert result[0].trace_id == "second"
        assert result[1].trace_id == "first"


class TestTraceStoreEviction:
    async def test_evicts_oldest_when_at_cap(self) -> None:
        store = TraceStore()
        for i in range(_MAX_TRACES):
            await store.put(_make_trace(str(i)))
        assert await store.count() == _MAX_TRACES
        await store.put(_make_trace("overflow"))
        assert await store.count() == _MAX_TRACES
        assert await store.get("0") is None
        assert await store.get("overflow") is not None


class TestTraceStoreThreadSafety:
    async def test_concurrent_puts_are_safe(self) -> None:
        import asyncio  # noqa: PLC0415
        store = TraceStore()
        errors: list[Exception] = []

        async def writer(n: int) -> None:
            try:
                for i in range(50):
                    await store.put(_make_trace(f"{n}-{i}"))
            except Exception as e:  # noqa: BLE001
                errors.append(e)

        await asyncio.gather(*[writer(n) for n in range(4)])
        assert not errors
        assert await store.count() > 0
