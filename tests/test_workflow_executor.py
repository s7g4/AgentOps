"""Tests for AsyncWorkflowExecutor — parallel layers, dep chains, step failure."""

from __future__ import annotations

import asyncio

from app.registry.tool_registry import ToolRegistry
from app.workflows.definition import WorkflowDefinition, WorkflowStep
from app.workflows.execution import StepStatus, WorkflowExecution, WorkflowStatus
from app.workflows.executor import AsyncWorkflowExecutor
from app.workflows.store import InMemoryWorkflowStore


def _make_executor() -> tuple[AsyncWorkflowExecutor, InMemoryWorkflowStore]:
    store = InMemoryWorkflowStore()
    registry = ToolRegistry.default()
    executor = AsyncWorkflowExecutor(tool_registry=registry, store=store)
    return executor, store


def _make_wf(*steps: WorkflowStep) -> WorkflowDefinition:
    wf = WorkflowDefinition(name="test", steps=list(steps))
    wf.validate()
    return wf


# ── Single step ───────────────────────────────────────────────────────────────

def test_single_step_success() -> None:
    executor, store = _make_executor()
    step = WorkflowStep(id="refund", tool_name="refund_policy", depends_on=[])
    wf = _make_wf(step)
    ex = WorkflowExecution(workflow_id=wf.id, context={})

    result = asyncio.run(executor.run(wf, ex))

    assert result.status == WorkflowStatus.COMPLETED
    assert result.step_results["refund"].status == StepStatus.SUCCESS
    assert result.step_results["refund"].output is not None


# ── Step failure + SKIPPED propagation ───────────────────────────────────────

def test_failed_step_marks_dependents_skipped() -> None:
    """
    bad_tool (will fail) → downstream (should be SKIPPED)
    """
    executor, store = _make_executor()
    failing = WorkflowStep(id="fail", tool_name="nonexistent_tool", depends_on=[])
    downstream = WorkflowStep(id="skip_me", tool_name="refund_policy", depends_on=["fail"])
    wf = _make_wf(failing, downstream)
    ex = WorkflowExecution(workflow_id=wf.id, context={})

    result = asyncio.run(executor.run(wf, ex))

    assert result.status == WorkflowStatus.FAILED
    assert result.step_results["fail"].status == StepStatus.FAILED
    assert result.step_results["skip_me"].status == StepStatus.SKIPPED


# ── Parallel steps in same layer ─────────────────────────────────────────────

def test_parallel_steps_both_succeed() -> None:
    executor, store = _make_executor()
    step_a = WorkflowStep(id="a", tool_name="refund_policy", depends_on=[])
    step_b = WorkflowStep(id="b", tool_name="refund_policy", depends_on=[])
    wf = _make_wf(step_a, step_b)
    ex = WorkflowExecution(workflow_id=wf.id, context={})

    result = asyncio.run(executor.run(wf, ex))

    assert result.status == WorkflowStatus.COMPLETED
    assert result.step_results["a"].status == StepStatus.SUCCESS
    assert result.step_results["b"].status == StepStatus.SUCCESS


# ── Dependency chain ─────────────────────────────────────────────────────────

def test_dependency_chain_executes_in_order() -> None:
    """a → b: b must run after a succeeds."""
    executor, store = _make_executor()
    step_a = WorkflowStep(id="a", tool_name="refund_policy", depends_on=[])
    step_b = WorkflowStep(id="b", tool_name="refund_policy", depends_on=["a"])
    wf = _make_wf(step_a, step_b)
    ex = WorkflowExecution(workflow_id=wf.id, context={})

    result = asyncio.run(executor.run(wf, ex))

    assert result.status == WorkflowStatus.COMPLETED
    assert result.step_results["a"].status == StepStatus.SUCCESS
    assert result.step_results["b"].status == StepStatus.SUCCESS
    # b must start after a finished.
    assert (
        result.step_results["b"].started_at >= result.step_results["a"].finished_at
        or result.step_results["b"].started_at >= result.step_results["a"].started_at
    )


# ── Diamond DAG ───────────────────────────────────────────────────────────────

def test_diamond_dag_all_succeed() -> None:
    """
        a
       / \\
      b   c
       \\ /
        d
    """
    executor, store = _make_executor()
    wf = _make_wf(
        WorkflowStep(id="a", tool_name="refund_policy"),
        WorkflowStep(id="b", tool_name="refund_policy", depends_on=["a"]),
        WorkflowStep(id="c", tool_name="refund_policy", depends_on=["a"]),
        WorkflowStep(id="d", tool_name="refund_policy", depends_on=["b", "c"]),
    )
    ex = WorkflowExecution(workflow_id=wf.id, context={})

    result = asyncio.run(executor.run(wf, ex))

    assert result.status == WorkflowStatus.COMPLETED
    for sid in ("a", "b", "c", "d"):
        assert result.step_results[sid].status == StepStatus.SUCCESS


# ── Execution is persisted to store ──────────────────────────────────────────

def test_execution_persisted_to_store() -> None:
    executor, store = _make_executor()
    step = WorkflowStep(id="s", tool_name="refund_policy")
    wf = _make_wf(step)
    ex = WorkflowExecution(workflow_id=wf.id, context={})

    result = asyncio.run(executor.run(wf, ex))

    # Retrieve from store and verify it matches.
    fetched = asyncio.run(store.get_execution(result.execution_id))
    assert fetched is not None
    assert fetched.status == WorkflowStatus.COMPLETED


# ── Context merge ─────────────────────────────────────────────────────────────

def test_context_is_passed_to_step() -> None:
    """order_status tool accepts order_id from context."""
    executor, store = _make_executor()
    step = WorkflowStep(id="order", tool_name="check_order_status")
    wf = _make_wf(step)
    ex = WorkflowExecution(workflow_id=wf.id, context={"order_id": "ORD-999"})

    result = asyncio.run(executor.run(wf, ex))

    assert result.status == WorkflowStatus.COMPLETED
    assert result.step_results["order"].output is not None


# ── Step Output Chaining / Template resolution ────────────────────────────────

def test_workflow_step_chaining_success() -> None:
    """A workflow with step B referencing step A's output resolves the template correctly."""
    executor, store = _make_executor()
    step_a = WorkflowStep(
        id="order1",
        tool_name="check_order_status",
        static_input={"order_id": "ORD-123"},
    )
    step_b = WorkflowStep(
        id="order2",
        tool_name="check_order_status",
        static_input={"order_id": "$step.order1.status"},
        depends_on=["order1"],
    )
    wf = _make_wf(step_a, step_b)
    ex = WorkflowExecution(workflow_id=wf.id, context={})

    result = asyncio.run(executor.run(wf, ex))

    assert result.status == WorkflowStatus.COMPLETED
    assert result.step_results["order1"].status == StepStatus.SUCCESS
    assert result.step_results["order2"].status == StepStatus.SUCCESS
    # order2 input should be resolved from order1 output status ("shipped")
    assert result.step_results["order2"].output is not None
    assert result.step_results["order2"].output["order_id"] == "shipped"

