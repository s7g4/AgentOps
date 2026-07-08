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

import logging
import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query

from app.agents.registry import AgentRegistry
from app.api.deps import get_agent_registry, get_routing_store, get_supervisor
from app.messaging.message import RoutingResult, SubTask
from app.messaging.routing_store import RoutingStoreProtocol
from app.messaging.supervisor import SupervisorAgent
from app.schemas.routing import (
    AgentInfoResponse,
    AgentListResponse,
    RouteRequest,
    RoutingListResponse,
    RoutingResponse,
    SubTaskResultResponse,
)

agents_router = APIRouter(prefix="/agents", tags=["agents"])
logger = logging.getLogger(__name__)


def _to_routing_response(result: RoutingResult) -> RoutingResponse:
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

    If ``subtasks`` are provided in the request body, they are run.
    If ``subtasks`` are omitted, the decomposer generates them automatically.

    Overall status:
      • ``completed`` — all subtasks succeeded
      • ``partial``   — some succeeded, some failed
      • ``failed``    — all subtasks failed
    """
    subtasks = (
        [
            SubTask(
                task_id=str(uuid.uuid4()),
                agent_name=st.agent_name,
                payload=dict(st.payload),
            )
            for st in body.subtasks
        ]
        if body.subtasks is not None
        else None
    )

    try:
        result = await supervisor.route(goal=body.goal, subtasks=subtasks)
    except Exception as exc:  # noqa: BLE001
        logger.exception("agent_routing_failed", extra={"goal": body.goal})
        raise HTTPException(status_code=500, detail="Routing failed.") from exc

    return _to_routing_response(result)


# ── GET /agents/routes (History) ─────────────────────────────────────────────

@agents_router.get("/routes", response_model=RoutingListResponse, summary="List routing runs")
async def list_routing_runs(
    store: Annotated[RoutingStoreProtocol, Depends(get_routing_store)],
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> RoutingListResponse:
    """Return a paginated list of all routing runs, most recent first."""
    routes = await store.list(limit=limit, offset=offset)
    total = await store.count()
    return RoutingListResponse(
        total=total,
        routes=[_to_routing_response(r) for r in routes],
    )


@agents_router.get(
    "/routes/{routing_id}", response_model=RoutingResponse, summary="Get routing run"
)
async def get_routing_run(
    routing_id: str,
    store: Annotated[RoutingStoreProtocol, Depends(get_routing_store)],
) -> RoutingResponse:
    """Retrieve a single routing run by its routing_id."""
    result = await store.get(routing_id)
    if result is None:
        raise HTTPException(status_code=404, detail=f"Routing run {routing_id!r} not found.")
    return _to_routing_response(result)

