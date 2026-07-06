"""Tests for PipelineAgent — the RoutableAgent adapter around AgentOpsRuntime."""

from __future__ import annotations

import asyncio

from app.agents.pipeline_agent import PipelineAgent
from app.messaging.message import AgentMessage
from app.runtime.runtime import AgentOpsRuntime


def test_pipeline_agent_runs_message_through_runtime() -> None:
    agent = PipelineAgent(AgentOpsRuntime.default())
    message = AgentMessage(
        sender="supervisor",
        recipient="support_pipeline",
        payload={"message": "I want a refund", "customer_id": "cust_1"},
    )

    reply = asyncio.run(agent.handle(message))

    assert reply.sender == "support_pipeline"
    assert reply.recipient == "supervisor"
    assert reply.reply_to == message.id
    assert "trace_id" in reply.payload
    assert reply.payload["intent"] == "refund"


def test_pipeline_agent_defaults_customer_id_to_sender() -> None:
    agent = PipelineAgent(AgentOpsRuntime.default())
    message = AgentMessage(
        sender="cust_42",
        recipient="support_pipeline",
        payload={"message": "where is my order"},
    )

    reply = asyncio.run(agent.handle(message))

    assert reply.payload["intent"] == "order_status"


def test_pipeline_agent_registered_in_agent_registry() -> None:
    from app.api.deps import get_agent_registry

    registry = get_agent_registry()
    agent = registry.get("support_pipeline")
    assert agent.name == "support_pipeline"
