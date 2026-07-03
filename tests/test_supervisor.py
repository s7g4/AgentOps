"""Tests for SupervisorAgent — single subtask, parallel, partial failure."""

from __future__ import annotations

import asyncio

from app.agents.registry import AgentRegistry
from app.messaging.bus import AgentBus
from app.messaging.message import SubTask
from app.messaging.supervisor import SupervisorAgent


def _supervisor() -> SupervisorAgent:
    return SupervisorAgent(bus=AgentBus(), registry=AgentRegistry.default())


# ── Single subtask ────────────────────────────────────────────────────────────

def test_single_subtask_succeeds() -> None:
    sv = _supervisor()
    tasks = [SubTask(task_id="t1", agent_name="echo", payload={"x": 1})]

    result = asyncio.run(sv.route("test goal", tasks))

    assert result.status == "completed"
    assert len(result.results) == 1
    assert result.results[0].status == "success"
    assert result.results[0].task_id == "t1"
    assert result.results[0].output is not None


# ── Multiple parallel subtasks ────────────────────────────────────────────────

def test_parallel_subtasks_all_succeed() -> None:
    sv = _supervisor()
    tasks = [
        SubTask(task_id="a", agent_name="echo", payload={"n": 1}),
        SubTask(task_id="b", agent_name="summary", payload={"k": "v"}),
        SubTask(task_id="c", agent_name="echo", payload={"n": 3}),
    ]

    result = asyncio.run(sv.route("parallel goal", tasks))

    assert result.status == "completed"
    assert len(result.results) == 3
    for r in result.results:
        assert r.status == "success"


# ── Partial failure ───────────────────────────────────────────────────────────

def test_one_failed_subtask_gives_partial_status() -> None:
    sv = _supervisor()
    tasks = [
        SubTask(task_id="good", agent_name="echo", payload={}),
        SubTask(task_id="bad", agent_name="nonexistent_agent", payload={}),
    ]

    result = asyncio.run(sv.route("partial goal", tasks))

    assert result.status == "partial"
    by_id = {r.task_id: r for r in result.results}
    assert by_id["good"].status == "success"
    assert by_id["bad"].status == "error"
    assert "nonexistent_agent" in (by_id["bad"].error or "")


# ── All failed ────────────────────────────────────────────────────────────────

def test_all_failed_gives_failed_status() -> None:
    sv = _supervisor()
    tasks = [
        SubTask(task_id="x", agent_name="bad_agent_1", payload={}),
        SubTask(task_id="y", agent_name="bad_agent_2", payload={}),
    ]

    result = asyncio.run(sv.route("failing goal", tasks))

    assert result.status == "failed"
    for r in result.results:
        assert r.status == "error"


# ── Metadata ──────────────────────────────────────────────────────────────────

def test_result_contains_goal_and_routing_id() -> None:
    sv = _supervisor()
    tasks = [SubTask(task_id="t", agent_name="echo", payload={})]

    result = asyncio.run(sv.route("my goal", tasks))

    assert result.goal == "my goal"
    assert len(result.routing_id) == 36  # UUID format
    assert result.duration_ms >= 0


def test_duration_ms_is_populated() -> None:
    sv = _supervisor()
    tasks = [SubTask(task_id="t", agent_name="echo", payload={})]

    result = asyncio.run(sv.route("goal", tasks))

    assert result.duration_ms > 0
    assert result.results[0].duration_ms >= 0


# ── Payload passthrough ───────────────────────────────────────────────────────

def test_payload_is_passed_to_agent() -> None:
    sv = _supervisor()
    tasks = [SubTask(task_id="t", agent_name="echo", payload={"key": "value"})]

    result = asyncio.run(sv.route("echo test", tasks))

    assert result.results[0].output is not None
    assert result.results[0].output.get("key") == "value"
