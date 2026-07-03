"""Workflow execution state model.

Tracks the live state of a workflow run — which steps have succeeded,
failed, or been skipped, and what they returned.

Design
──────
WorkflowExecution is a snapshot.  The executor writes it to the store
after every layer completes so that GET /runs/{id} always reflects
current progress, not just the final outcome.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

from app.schemas.trace import utc_now_iso


class StepStatus(StrEnum):
    """Lifecycle state of a single workflow step."""

    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"
    SKIPPED = "skipped"  # upstream step failed; this step was never started


class WorkflowStatus(StrEnum):
    """Overall status of a workflow execution."""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class StepResult:
    """The outcome of a single executed workflow step.

    Attributes
    ----------
    step_id:     ID of the WorkflowStep.
    status:      Final StepStatus after execution.
    output:      Tool output dict, or None if step failed or was skipped.
    error:       Error message string, or None on success.
    started_at:  ISO-8601 UTC timestamp when execution began.
    finished_at: ISO-8601 UTC timestamp when execution ended.
    """

    step_id: str
    status: StepStatus
    started_at: str
    finished_at: str
    output: dict[str, Any] | None = None
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "step_id": self.step_id,
            "status": self.status.value,
            "output": self.output,
            "error": self.error,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> StepResult:
        return cls(
            step_id=d["step_id"],
            status=StepStatus(d["status"]),
            output=d.get("output"),
            error=d.get("error"),
            started_at=d["started_at"],
            finished_at=d["finished_at"],
        )


@dataclass
class WorkflowExecution:
    """A single run of a WorkflowDefinition.

    Attributes
    ----------
    execution_id:  Unique identifier for this run (UUID).
    workflow_id:   ID of the WorkflowDefinition being executed.
    status:        Overall execution status.
    step_results:  Map of step_id → StepResult, filled in as steps complete.
    context:       Runtime input passed to all steps (merged with static_input).
    created_at:    ISO-8601 UTC timestamp when run was initiated.
    updated_at:    ISO-8601 UTC timestamp, updated after each layer.
    """

    workflow_id: str
    context: dict[str, Any]
    execution_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    status: WorkflowStatus = WorkflowStatus.PENDING
    step_results: dict[str, StepResult] = field(default_factory=dict)
    created_at: str = field(default_factory=utc_now_iso)
    updated_at: str = field(default_factory=utc_now_iso)

    def touch(self) -> None:
        """Update the updated_at timestamp."""
        self.updated_at = utc_now_iso()

    def to_dict(self) -> dict[str, Any]:
        return {
            "execution_id": self.execution_id,
            "workflow_id": self.workflow_id,
            "status": self.status.value,
            "step_results": {k: v.to_dict() for k, v in self.step_results.items()},
            "context": self.context,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> WorkflowExecution:
        return cls(
            execution_id=d["execution_id"],
            workflow_id=d["workflow_id"],
            status=WorkflowStatus(d["status"]),
            step_results={
                k: StepResult.from_dict(v) for k, v in d.get("step_results", {}).items()
            },
            context=d.get("context", {}),
            created_at=d["created_at"],
            updated_at=d["updated_at"],
        )
