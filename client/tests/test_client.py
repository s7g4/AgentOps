"""Integration tests for AsyncAgentOpsClient / AgentOpsClient against the real
ASGI app via httpx.ASGITransport — no live server, no network."""

from __future__ import annotations

import pytest

from agentops_client.client import AgentOpsClient, AsyncAgentOpsClient
from agentops_client.exceptions import AgentOpsHTTPError

_WORKFLOW_STEPS = [{"id": "step1", "tool_name": "refund_policy"}]


# ── Async client ───────────────────────────────────────────────────────────────

async def test_async_health(async_client: AsyncAgentOpsClient) -> None:
    status = await async_client.health()
    assert status.status == "ok"


async def test_async_send_message(async_client: AsyncAgentOpsClient) -> None:
    result = await async_client.send_message(message="I want a refund", customer_id="cust_1")
    assert result.intent == "refund"
    assert result.trace_id


async def test_async_get_trace_after_send(async_client: AsyncAgentOpsClient) -> None:
    sent = await async_client.send_message(message="where is my order", customer_id="cust_2")
    trace = await async_client.get_trace(sent.trace_id)
    assert trace["trace_id"] == sent.trace_id


async def test_async_list_tools(async_client: AsyncAgentOpsClient) -> None:
    tools = await async_client.list_tools()
    assert "refund_policy" in tools


async def test_async_workflow_lifecycle(async_client: AsyncAgentOpsClient) -> None:
    wf = await async_client.create_workflow("cli-test", _WORKFLOW_STEPS)
    assert wf.name == "cli-test"

    fetched = await async_client.get_workflow(wf.id)
    assert fetched.id == wf.id

    execution = await async_client.run_workflow(wf.id)
    assert execution.status == "completed"
    assert execution.step_results["step1"].status == "success"

    page = await async_client.list_workflows()
    assert any(w.id == wf.id for w in page.items)

    await async_client.delete_workflow(wf.id)
    with pytest.raises(AgentOpsHTTPError) as exc_info:
        await async_client.get_workflow(wf.id)
    assert exc_info.value.status_code == 404


async def test_async_background_workflow_run(async_client: AsyncAgentOpsClient) -> None:
    wf = await async_client.create_workflow("bg-test", _WORKFLOW_STEPS)
    execution = await async_client.run_workflow(wf.id, background=True)
    assert execution.status == "pending"

    fetched = await async_client.get_execution(wf.id, execution.execution_id)
    assert fetched.status in ("pending", "running", "completed")


async def test_async_list_agents_includes_pipeline(async_client: AsyncAgentOpsClient) -> None:
    agents = await async_client.list_agents()
    names = {a.name for a in agents}
    assert {"echo", "summary", "support_pipeline"} <= names


async def test_async_route_goal_explicit_subtasks(async_client: AsyncAgentOpsClient) -> None:
    result = await async_client.route_goal(
        "test goal", subtasks=[{"agent_name": "echo", "payload": {"hello": "world"}}]
    )
    assert result.status == "completed"
    assert result.results[0].agent_name == "echo"


async def test_async_routing_history(async_client: AsyncAgentOpsClient) -> None:
    routed = await async_client.route_goal(
        "history goal", subtasks=[{"agent_name": "echo", "payload": {}}]
    )
    page = await async_client.list_routing_runs()
    assert any(r.routing_id == routed.routing_id for r in page.items)

    fetched = await async_client.get_routing_run(routed.routing_id)
    assert fetched.routing_id == routed.routing_id


async def test_async_http_error_maps_to_exception(async_client: AsyncAgentOpsClient) -> None:
    with pytest.raises(AgentOpsHTTPError) as exc_info:
        await async_client.get_workflow("does-not-exist")
    assert exc_info.value.status_code == 404


# ── Sync client ──────────────────────────────────────────────────────────────

def test_sync_health(sync_client: AgentOpsClient) -> None:
    assert sync_client.health().status == "ok"


def test_sync_multiple_sequential_calls(sync_client: AgentOpsClient) -> None:
    """Regression test: each call must open/close its own loop cleanly —
    a shared httpx.AsyncClient across asyncio.run() calls breaks on the
    second call with 'Event loop is closed'."""
    assert sync_client.health().status == "ok"
    assert "refund_policy" in sync_client.list_tools()
    result = sync_client.send_message(message="I want a refund", customer_id="cust_1")
    assert result.intent == "refund"


def test_sync_workflow_create_and_run(sync_client: AgentOpsClient) -> None:
    wf = sync_client.create_workflow("sync-test", _WORKFLOW_STEPS)
    execution = sync_client.run_workflow(wf.id)
    assert execution.status == "completed"
