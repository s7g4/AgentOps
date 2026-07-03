"""Tests for AgentBus — dispatch, unknown recipient, reply structure."""

from __future__ import annotations

import asyncio

import pytest

from app.agents.registry import AgentRegistry
from app.exceptions import AgentNotFoundError
from app.messaging.bus import AgentBus
from app.messaging.message import AgentMessage


def _registry() -> AgentRegistry:
    return AgentRegistry.default()


def _bus() -> AgentBus:
    return AgentBus()


# ── Successful dispatch ───────────────────────────────────────────────────────

def test_send_to_echo_returns_reply() -> None:
    bus = _bus()
    registry = _registry()
    msg = AgentMessage(sender="user", recipient="echo", payload={"hello": "world"})

    reply = asyncio.run(bus.send(msg, registry))

    assert reply.sender == "echo"
    assert reply.reply_to == msg.id
    assert reply.payload["hello"] == "world"
    assert reply.payload["_echo"] is True


def test_send_to_summary_returns_structural_summary() -> None:
    bus = _bus()
    registry = _registry()
    msg = AgentMessage(
        sender="user",
        recipient="summary",
        payload={"order_id": "X1", "amount": 99},
    )

    reply = asyncio.run(bus.send(msg, registry))

    assert reply.sender == "summary"
    assert reply.reply_to == msg.id
    assert reply.payload["key_count"] == 2
    assert set(reply.payload["keys"]) == {"order_id", "amount"}  # type: ignore[arg-type]


# ── Unknown recipient ─────────────────────────────────────────────────────────

def test_send_to_unknown_recipient_raises_agent_not_found() -> None:
    bus = _bus()
    registry = _registry()
    msg = AgentMessage(sender="user", recipient="nonexistent", payload={})

    with pytest.raises(AgentNotFoundError):
        asyncio.run(bus.send(msg, registry))


# ── Reply structure ───────────────────────────────────────────────────────────

def test_reply_has_new_id() -> None:
    """Each message and its reply must have distinct IDs."""
    bus = _bus()
    registry = _registry()
    msg = AgentMessage(sender="user", recipient="echo", payload={})

    reply = asyncio.run(bus.send(msg, registry))

    assert reply.id != msg.id


# ── Concurrent sends ──────────────────────────────────────────────────────────

def test_concurrent_sends_all_resolve() -> None:
    bus = _bus()
    registry = _registry()

    async def _run() -> list[AgentMessage]:
        messages = [
            AgentMessage(sender="user", recipient="echo", payload={"n": i})
            for i in range(5)
        ]
        return await asyncio.gather(*[bus.send(m, registry) for m in messages])

    replies = asyncio.run(_run())
    assert len(replies) == 5
    for r in replies:
        assert r.sender == "echo"
