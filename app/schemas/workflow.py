"""Pydantic v2 request/response schemas for the Workflow Engine API.

These are the API boundary types only — internal dataclasses live in
app/workflows/definition.py and app/workflows/execution.py.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, model_validator


class WorkflowStepSchema(BaseModel):
    """A single step in a workflow definition.

    Exactly one of tool_name / agent_name must be set, matching kind.
    """

    id: str = Field(..., description="Step identifier, unique within this workflow.")
    kind: Literal["tool", "agent"] = Field(
        default="tool", description="Whether this step calls a tool or an agent."
    )
    tool_name: str | None = Field(
        default=None,
        description="Name of the registered tool to execute. Required for kind='tool'.",
    )
    agent_name: str | None = Field(
        default=None,
        description="Name of the registered agent to invoke. Required for kind='agent'.",
    )
    static_input: dict[str, object] = Field(
        default_factory=dict,
        description="Input merged with runtime context before execution.",
    )
    depends_on: list[str] = Field(
        default_factory=list,
        description="IDs of steps that must complete successfully before this step runs.",
    )

    @model_validator(mode="after")
    def _check_target(self) -> WorkflowStepSchema:
        if self.kind == "tool" and not self.tool_name:
            raise ValueError(f"Step {self.id!r}: tool_name is required when kind='tool'")
        if self.kind == "agent" and not self.agent_name:
            raise ValueError(f"Step {self.id!r}: agent_name is required when kind='agent'")
        return self


class CreateWorkflowRequest(BaseModel):
    """Request body for POST /workflows."""

    name: str = Field(
        ..., min_length=1, max_length=128, description="Human-readable workflow name."
    )
    description: str = Field(default="", max_length=1024)
    steps: list[WorkflowStepSchema] = Field(..., min_length=1)


class WorkflowResponse(BaseModel):
    """Response for workflow definition endpoints."""

    id: str
    name: str
    description: str
    steps: list[WorkflowStepSchema]
    created_at: str
    updated_at: str


class WorkflowListResponse(BaseModel):
    """Paginated list of workflow definitions."""

    total: int
    workflows: list[WorkflowResponse]


class RunWorkflowRequest(BaseModel):
    """Request body for POST /workflows/{id}/run."""

    context: dict[str, object] = Field(
        default_factory=dict,
        description="Runtime key-value pairs merged into every step's input.",
    )
    background: bool = Field(
        default=False,
        description=(
            "If true, return immediately with a PENDING execution and run the "
            "workflow in the background; poll GET .../runs/{execution_id} for "
            "the result. If false (default), the request blocks until the "
            "workflow finishes."
        ),
    )


class StepResultResponse(BaseModel):
    """Result of a single workflow step."""

    step_id: str
    status: str
    output: dict[str, object] | None = None
    error: str | None = None
    started_at: str
    finished_at: str


class ExecutionResponse(BaseModel):
    """Response for workflow execution endpoints."""

    execution_id: str
    workflow_id: str
    status: str
    step_results: dict[str, StepResultResponse]
    created_at: str
    updated_at: str


class ExecutionListResponse(BaseModel):
    """Paginated list of workflow executions."""

    total: int
    executions: list[ExecutionResponse]
