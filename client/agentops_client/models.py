"""Typed response models for the AgentOps client.

Dataclasses, not Pydantic — these are read-only views of server responses,
not validated inputs. Each has a from_dict() so the client can stay a thin
translation layer over the raw JSON.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class HealthStatus:
    status: str
    version: str
    checks: dict[str, str]

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> HealthStatus:
        return cls(status=d["status"], version=d["version"], checks=d["checks"])


@dataclass(frozen=True)
class MessageResult:
    trace_id: str
    intent: str
    confidence: float
    escalated: bool
    response: str

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> MessageResult:
        return cls(
            trace_id=d["trace_id"],
            intent=d["intent"],
            confidence=d["confidence"],
            escalated=d["escalated"],
            response=d["response"],
        )


@dataclass(frozen=True)
class WorkflowStep:
    id: str
    kind: str
    tool_name: str | None
    agent_name: str | None
    static_input: dict[str, Any]
    depends_on: list[str]

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> WorkflowStep:
        return cls(
            id=d["id"],
            kind=d.get("kind", "tool"),
            tool_name=d.get("tool_name"),
            agent_name=d.get("agent_name"),
            static_input=d.get("static_input", {}),
            depends_on=d.get("depends_on", []),
        )


@dataclass(frozen=True)
class Workflow:
    id: str
    name: str
    description: str
    steps: list[WorkflowStep]
    created_at: str
    updated_at: str

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> Workflow:
        return cls(
            id=d["id"],
            name=d["name"],
            description=d["description"],
            steps=[WorkflowStep.from_dict(s) for s in d["steps"]],
            created_at=d["created_at"],
            updated_at=d["updated_at"],
        )


@dataclass(frozen=True)
class StepResult:
    step_id: str
    status: str
    output: dict[str, Any] | None
    error: str | None
    started_at: str
    finished_at: str


@dataclass(frozen=True)
class Execution:
    execution_id: str
    workflow_id: str
    status: str
    step_results: dict[str, StepResult]
    created_at: str
    updated_at: str

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> Execution:
        return cls(
            execution_id=d["execution_id"],
            workflow_id=d["workflow_id"],
            status=d["status"],
            step_results={
                sid: StepResult(
                    step_id=r["step_id"],
                    status=r["status"],
                    output=r.get("output"),
                    error=r.get("error"),
                    started_at=r["started_at"],
                    finished_at=r["finished_at"],
                )
                for sid, r in d["step_results"].items()
            },
            created_at=d["created_at"],
            updated_at=d["updated_at"],
        )


@dataclass(frozen=True)
class AgentInfo:
    name: str
    description: str


@dataclass(frozen=True)
class SubTaskResult:
    task_id: str
    agent_name: str
    status: str
    output: dict[str, Any] | None
    error: str | None
    duration_ms: float


@dataclass(frozen=True)
class RoutingResult:
    routing_id: str
    goal: str
    status: str
    results: list[SubTaskResult]
    created_at: str
    duration_ms: float

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> RoutingResult:
        return cls(
            routing_id=d["routing_id"],
            goal=d["goal"],
            status=d["status"],
            results=[
                SubTaskResult(
                    task_id=r["task_id"],
                    agent_name=r["agent_name"],
                    status=r["status"],
                    output=r.get("output"),
                    error=r.get("error"),
                    duration_ms=r["duration_ms"],
                )
                for r in d["results"]
            ],
            created_at=d["created_at"],
            duration_ms=d["duration_ms"],
        )


@dataclass(frozen=True)
class Page:
    """A generic paginated listing — total count plus the items on this page."""

    total: int
    items: list[Any] = field(default_factory=list)
