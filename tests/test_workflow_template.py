"""Tests for workflow step output chaining / template resolution."""

from __future__ import annotations

import pytest

from app.exceptions import WorkflowExecutionError
from app.workflows.execution import StepResult, StepStatus
from app.workflows.template import resolve_templates


def _make_success_result(step_id: str, output: dict[str, object]) -> StepResult:
    return StepResult(
        step_id=step_id,
        status=StepStatus.SUCCESS,
        started_at="2026-07-03T12:00:00Z",
        finished_at="2026-07-03T12:00:01Z",
        output=output,
    )


# ── Success cases ─────────────────────────────────────────────────────────────

def test_resolve_templates_success() -> None:
    static_input = {
        "order_id": "$step.step1.order_id",
        "static_val": "hello",
        "numeric_val": 42,
    }
    step_results = {
        "step1": _make_success_result("step1", {"order_id": "ORD-123", "other": "val"})
    }

    resolved = resolve_templates(static_input, step_results)

    assert resolved == {
        "order_id": "ORD-123",
        "static_val": "hello",
        "numeric_val": 42,
    }


def test_resolve_templates_no_templates() -> None:
    static_input = {"a": 1, "b": "xyz"}
    assert resolve_templates(static_input, {}) == static_input


# ── Error cases ───────────────────────────────────────────────────────────────

def test_resolve_templates_invalid_format() -> None:
    static_input = {"val": "$step.step1"}
    with pytest.raises(WorkflowExecutionError, match="Invalid template format"):
        resolve_templates(static_input, {})


def test_resolve_templates_missing_step() -> None:
    static_input = {"val": "$step.step2.key"}
    step_results = {
        "step1": _make_success_result("step1", {"key": "val"})
    }
    with pytest.raises(
        WorkflowExecutionError,
        match="references step 'step2' which has not been executed",
    ):
        resolve_templates(static_input, step_results)


def test_resolve_templates_step_no_output() -> None:
    static_input = {"val": "$step.step1.key"}
    step_results = {
        "step1": StepResult(
            step_id="step1",
            status=StepStatus.FAILED,
            started_at="2026-07-03T12:00:00Z",
            finished_at="2026-07-03T12:00:01Z",
            error="Something failed",
            output=None,
        )
    }
    with pytest.raises(
        WorkflowExecutionError, match="references step 'step1' which has no output"
    ):
        resolve_templates(static_input, step_results)


def test_resolve_templates_missing_key() -> None:
    static_input = {"val": "$step.step1.missing_key"}
    step_results = {
        "step1": _make_success_result("step1", {"existing_key": "val"})
    }
    with pytest.raises(
        WorkflowExecutionError,
        match="Key 'missing_key' not found in output of step 'step1'",
    ):
        resolve_templates(static_input, step_results)
