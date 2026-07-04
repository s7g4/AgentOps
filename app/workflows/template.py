"""Workflow step input template resolution.

Parses and resolves template variables referencing prior step outputs.
Supports the syntax: $step.<step_id>.<key>
"""

from __future__ import annotations

from typing import Any

from app.exceptions import WorkflowExecutionError
from app.workflows.execution import StepResult


def resolve_templates(
    static_input: dict[str, Any],
    step_results: dict[str, StepResult],
) -> dict[str, Any]:
    """Resolve $step.<step_id>.<key> templates in string values.

    Parameters
    ----------
    static_input: Static configuration dict of a step.
    step_results: Results of already executed steps.

    Returns
    -------
    A new dictionary with all templates resolved.

    Raises
    ------
    WorkflowExecutionError: If a template references a step or key that
                             does not exist, or if the referenced step failed.
    """
    resolved: dict[str, Any] = {}

    for k, v in static_input.items():
        if isinstance(v, str) and v.startswith("$step."):
            parts = v.split(".", 2)
            if len(parts) < 3:
                raise WorkflowExecutionError(
                    f"Invalid template format: {v!r}. Expected '$step.<step_id>.<key>'"
                )

            _, step_id, key = parts
            if step_id not in step_results:
                raise WorkflowExecutionError(
                    f"Template references step {step_id!r} which has not "
                    "been executed yet or doesn't exist."
                )

            result = step_results[step_id]
            if result.output is None:
                raise WorkflowExecutionError(
                    f"Template references step {step_id!r} which has no "
                    f"output (status: {result.status})."
                )

            if key not in result.output:
                raise WorkflowExecutionError(
                    f"Key {key!r} not found in output of step {step_id!r}. "
                    f"Available keys: {list(result.output.keys())}"
                )

            resolved[k] = result.output[key]
        else:
            resolved[k] = v

    return resolved
