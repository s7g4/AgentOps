"""Tests for SupervisorAgent with decomposition and persistence integration."""

from __future__ import annotations

import asyncio

import pytest

from app.agents.registry import AgentRegistry
from app.exceptions import AgentRoutingError
from app.messaging.bus import AgentBus
from app.messaging.decomposition import DeterministicDecompositionProvider
from app.messaging.message import SubTask
from app.messaging.routing_store import InMemoryRoutingStore
from app.messaging.supervisor import SupervisorAgent


def test_supervisor_routes_with_auto_decomposition() -> None:
    bus = AgentBus()
    registry = AgentRegistry.default()
    decomposer = DeterministicDecompositionProvider()
    store = InMemoryRoutingStore()

    sv = SupervisorAgent(bus=bus, registry=registry, decomposer=decomposer, store=store)

    # Route with subtasks=None triggers decomposition
    result = asyncio.run(sv.route("summarize this order"))

    assert result.status == "completed"
    assert len(result.results) == 1
    assert result.results[0].agent_name == "summary"

    # Verify history persistence
    fetched = asyncio.run(store.get(result.routing_id))
    assert fetched is not None
    assert fetched.routing_id == result.routing_id
    assert fetched.status == "completed"


def test_supervisor_routes_with_explicit_subtasks_override() -> None:
    bus = AgentBus()
    registry = AgentRegistry.default()
    decomposer = DeterministicDecompositionProvider()
    store = InMemoryRoutingStore()

    sv = SupervisorAgent(bus=bus, registry=registry, decomposer=decomposer, store=store)

    # Decomposer says "summary" for "summarize", but we explicitly pass "echo"
    tasks = [SubTask(task_id="t1", agent_name="echo", payload={"msg": "hi"})]
    result = asyncio.run(sv.route("summarize this order", subtasks=tasks))

    assert result.status == "completed"
    assert len(result.results) == 1
    assert result.results[0].agent_name == "echo"  # overrides decomposer


def test_supervisor_raises_routing_error_if_no_decomposer() -> None:
    bus = AgentBus()
    registry = AgentRegistry.default()
    store = InMemoryRoutingStore()

    # No decomposer configured
    sv = SupervisorAgent(bus=bus, registry=registry, decomposer=None, store=store)

    with pytest.raises(AgentRoutingError, match="no decomposer is configured"):
        asyncio.run(sv.route("summarize this order"))
