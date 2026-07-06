"""Tests for RedisWorkflowStore against a real Redis instance.

Skipped automatically when no Redis is reachable (see conftest.redis_client).
"""

from __future__ import annotations

from conftest import REDIS_TEST_URL

from app.workflows.definition import WorkflowDefinition, WorkflowStep
from app.workflows.execution import StepResult, StepStatus, WorkflowExecution, WorkflowStatus
from app.workflows.store import RedisWorkflowStore


def _make_definition(name: str = "wf") -> WorkflowDefinition:
    return WorkflowDefinition(
        name=name,
        steps=[WorkflowStep(id="a", tool_name="refund_policy")],
    )


async def test_definition_put_and_get_roundtrip(redis_client) -> None:  # noqa: ANN001
    store = RedisWorkflowStore(redis_url=REDIS_TEST_URL)
    wf = _make_definition("checkout")

    await store.put_definition(wf)
    fetched = await store.get_definition(wf.id)

    assert fetched is not None
    assert fetched.name == "checkout"
    assert fetched.steps[0].id == "a"
    await store.close()


async def test_definition_get_missing_returns_none(redis_client) -> None:  # noqa: ANN001
    store = RedisWorkflowStore(redis_url=REDIS_TEST_URL)
    assert await store.get_definition("nope") is None
    await store.close()


async def test_definition_list_most_recent_first_and_count(redis_client) -> None:  # noqa: ANN001
    store = RedisWorkflowStore(redis_url=REDIS_TEST_URL)
    wfs = [_make_definition(f"wf-{i}") for i in range(3)]
    for wf in wfs:
        await store.put_definition(wf)

    assert await store.count_definitions() == 3
    listed = await store.list_definitions(limit=10)
    assert [w.id for w in listed] == [w.id for w in reversed(wfs)]
    await store.close()


async def test_definition_delete(redis_client) -> None:  # noqa: ANN001
    store = RedisWorkflowStore(redis_url=REDIS_TEST_URL)
    wf = _make_definition()
    await store.put_definition(wf)

    assert await store.delete_definition(wf.id) is True
    assert await store.get_definition(wf.id) is None
    assert await store.delete_definition(wf.id) is False
    await store.close()


async def test_execution_put_get_and_list(redis_client) -> None:  # noqa: ANN001
    store = RedisWorkflowStore(redis_url=REDIS_TEST_URL)
    wf = _make_definition()
    execution = WorkflowExecution(workflow_id=wf.id, context={"order_id": "ORD-1"})
    execution.status = WorkflowStatus.RUNNING
    execution.step_results["a"] = StepResult(
        step_id="a",
        status=StepStatus.SUCCESS,
        output={"status": "shipped"},
        started_at="2026-01-01T00:00:00Z",
        finished_at="2026-01-01T00:00:01Z",
    )

    await store.put_execution(execution)
    fetched = await store.get_execution(execution.execution_id)

    assert fetched is not None
    assert fetched.status == WorkflowStatus.RUNNING
    assert fetched.step_results["a"].output == {"status": "shipped"}

    listed = await store.list_executions(wf.id, limit=10)
    assert len(listed) == 1
    assert await store.count_executions(wf.id) == 1
    await store.close()
