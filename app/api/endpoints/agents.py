"""Multi-agent routing API endpoints.

Routes
──────
GET  /agents           List all registered agents (name + description)
POST /agents/route     Route a goal through the supervisor

Design decisions
────────────────
• POST /agents/route executes synchronously within the request.
  All subtasks run concurrently via asyncio.gather in SupervisorAgent.
  The response is returned only after all subtasks complete (or fail).

• The caller supplies an explicit subtask list — the supervisor does not
  decompose the goal via LLM in V4.  This keeps routing deterministic
  and testable without an API key.

• Unknown agent names in subtasks produce status="error" SubTaskResults
  rather than an HTTP 422, so other subtasks can still succeed
  (partial routing is a valid outcome).
"""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends

from app.agents.registry import AgentRegistry
from app.api.deps import get_agent_registry, get_supervisor
from app.messaging.message import SubTask
from app.messaging.supervisor import SupervisorAgent
from app.schemas.routing import (
    AgentInfoResponse,
    AgentListResponse,
    RouteRequest,
    RoutingResponse,
    SubTaskResultResponse,
)

agents_router = APIRouter(prefix="/agents", tags=["agents"])


# ── GET /agents ───────────────────────────────────────────────────────────────

@agents_router.get("", response_model=AgentListResponse, summary="List agents")
async def list_agents(
    registry: Annotated[AgentRegistry, Depends(get_agent_registry)],
) -> AgentListResponse:
    """Return all agents registered in the AgentRegistry."""
    descriptions = registry.descriptions()
    return AgentListResponse(
        count=len(descriptions),
        agents=[AgentInfoResponse(**d) for d in descriptions],
    )


# ── POST /agents/route ────────────────────────────────────────────────────────

@agents_router.post("/route", response_model=RoutingResponse, summary="Route goal")
async def route(
    body: RouteRequest,
    supervisor: Annotated[SupervisorAgent, Depends(get_supervisor)],
) -> RoutingResponse:
    """Dispatch a goal to multiple agents concurrently and return results.

    Each subtask in the request body is dispatched to the named agent.
    Subtasks run concurrently — one failing subtask does not cancel others.

    Overall status:
      • ``completed`` — all subtasks succeeded
      • ``partial``   — some succeeded, some failed
      • ``failed``    — all subtasks failed
    """
    subtasks = [
        SubTask(
            task_id=str(uuid.uuid4()),
            agent_name=st.agent_name,
            payload=dict(st.payload),
        )
        for st in body.subtasks
    ]

    result = await supervisor.route(goal=body.goal, subtasks=subtasks)

    return RoutingResponse(
        routing_id=result.routing_id,
        goal=result.goal,
        status=result.status,
        results=[
            SubTaskResultResponse(
                task_id=r.task_id,
                agent_name=r.agent_name,
                status=r.status,
                output=r.output,
                error=r.error,
                duration_ms=r.duration_ms,
            )
            for r in result.results
        ],
        created_at=result.created_at,
        duration_ms=result.duration_ms,
    )
