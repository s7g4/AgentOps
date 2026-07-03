"""Pydantic v2 request/response schemas for the Workflow Engine API.

These are the API boundary types only — internal dataclasses live in
app/workflows/definition.py and app/workflows/execution.py.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class WorkflowStepSchema(BaseModel):
    """A single step in a workflow definition."""

    id: str = Field(..., description="Step identifier, unique within this workflow.")
    tool_name: str = Field(..., description="Name of the registered tool to execute.")
    static_input: dict[str, object] = Field(
        default_factory=dict,
        description="Input merged with runtime context before tool execution.",
    )
    depends_on: list[str] = Field(
        default_factory=list,
        description="IDs of steps that must complete successfully before this step runs.",
    )


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
