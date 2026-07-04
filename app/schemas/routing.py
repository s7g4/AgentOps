"""Pydantic v2 request/response schemas for the multi-agent routing API."""

from __future__ import annotations

from pydantic import BaseModel, Field


class AgentInfoResponse(BaseModel):
    """Info about a single registered agent — returned by GET /agents."""

    name: str
    description: str


class AgentListResponse(BaseModel):
    """Full list of registered agents."""

    count: int
    agents: list[AgentInfoResponse]


class SubTaskRequest(BaseModel):
    """A single subtask directive in a RouteRequest."""

    agent_name: str = Field(..., description="Name of a registered agent to invoke.")
    payload: dict[str, object] = Field(
        default_factory=dict,
        description="Input payload passed to the agent.",
    )


class RouteRequest(BaseModel):
    """Request body for POST /agents/route."""

    goal: str = Field(
        ...,
        min_length=1,
        max_length=1024,
        description="Human-readable description of the overall goal.",
    )
    subtasks: list[SubTaskRequest] | None = Field(
        default=None,
        min_length=1,
        description=(
            "Explicit list of subtasks to dispatch concurrently. "
            "If omitted, uses LLM/deterministic decomposer."
        ),
    )



class SubTaskResultResponse(BaseModel):
    """Result of a single dispatched subtask."""

    task_id: str
    agent_name: str
    status: str
    output: dict[str, object] | None = None
    error: str | None = None
    duration_ms: float


class RoutingResponse(BaseModel):
    """Response for POST /agents/route."""

    routing_id: str
    goal: str
    status: str  # "completed" | "partial" | "failed"
    results: list[SubTaskResultResponse]
    created_at: str
    duration_ms: float


class RoutingListResponse(BaseModel):
    """Paginated list of routing run histories."""

    total: int
    routes: list[RoutingResponse]

