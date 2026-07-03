"""SupervisorAgent — concurrent multi-agent task dispatcher.

Responsibility
──────────────
The supervisor receives a goal string and a list of SubTasks (each
specifying which agent to call and with what payload).  It dispatches all
subtasks concurrently via the AgentBus and aggregates the results into a
RoutingResult.

Decomposition strategy (V4 — caller-explicit)
──────────────────────────────────────────────
The caller supplies the subtask list explicitly in the RouteRequest body.
The supervisor does not infer subtasks from the goal text — that requires
an LLM call and is deferred to V5.  This keeps V4:
  • Deterministic and testable without an API key.
  • Fast — no extra network round-trips for decomposition.
  • Transparent — the caller controls exactly which agents run.

Aggregation
───────────
All subtasks run concurrently via asyncio.gather with return_exceptions=True
so that one failing subtask never cancels the others.  Each result is
inspected individually and wrapped in a SubTaskResult.

RoutingResult.status is derived:
  "completed" → all succeeded
  "partial"   → some succeeded, some failed
  "failed"    → all failed (or empty subtask list)
"""

from __future__ import annotations

import asyncio
import logging
import time
import uuid

from app.agents.registry import AgentRegistry
from app.messaging.bus import AgentBus
from app.messaging.message import AgentMessage, RoutingResult, SubTask, SubTaskResult

logger = logging.getLogger(__name__)


class SupervisorAgent:
    """Dispatches subtasks concurrently and aggregates results.

    Parameters
    ----------
    bus:      The AgentBus used to dispatch each SubTask.
    registry: The AgentRegistry for agent resolution.
    """

    def __init__(self, bus: AgentBus, registry: AgentRegistry) -> None:
        self._bus = bus
        self._registry = registry

    async def route(
        self,
        goal: str,
        subtasks: list[SubTask],
    ) -> RoutingResult:
        """Dispatch all subtasks concurrently and return the RoutingResult.

        Parameters
        ----------
        goal:     Human-readable description of the overall goal.
        subtasks: List of SubTask directives to dispatch.

        Returns
        -------
        RoutingResult containing one SubTaskResult per SubTask.
        """
        routing_id = str(uuid.uuid4())
        wall_start = time.perf_counter()

        logger.info(
            "supervisor_routing_started",
            extra={
                "routing_id": routing_id,
                "goal": goal,
                "subtask_count": len(subtasks),
            },
        )

        # Dispatch all subtasks concurrently — failures in one do not
        # cancel the others.
        raw_results = await asyncio.gather(
            *[self._dispatch(task) for task in subtasks],
            return_exceptions=True,
        )

        results: list[SubTaskResult] = []
        for task, raw in zip(subtasks, raw_results, strict=True):
            if isinstance(raw, SubTaskResult):
                results.append(raw)
            else:
                # Unexpected exception not caught in _dispatch — wrap it.
                results.append(
                    SubTaskResult(
                        task_id=task.task_id,
                        agent_name=task.agent_name,
                        status="error",
                        error=str(raw),
                        duration_ms=0.0,
                    )
                )

        total_ms = (time.perf_counter() - wall_start) * 1000
        result = RoutingResult(
            routing_id=routing_id,
            goal=goal,
            results=results,
            duration_ms=round(total_ms, 2),
        )

        logger.info(
            "supervisor_routing_completed",
            extra={
                "routing_id": routing_id,
                "status": result.status,
                "duration_ms": result.duration_ms,
            },
        )
        return result

    async def _dispatch(self, task: SubTask) -> SubTaskResult:
        """Dispatch a single SubTask on the bus and return its SubTaskResult."""
        start = time.perf_counter()
        message = AgentMessage(
            sender="supervisor",
            recipient=task.agent_name,
            payload=task.payload,
        )
        try:
            reply = await self._bus.send(message, self._registry)
            duration_ms = round((time.perf_counter() - start) * 1000, 2)
            return SubTaskResult(
                task_id=task.task_id,
                agent_name=task.agent_name,
                status="success",
                output=reply.payload,
                duration_ms=duration_ms,
            )
        except Exception as exc:  # noqa: BLE001
            duration_ms = round((time.perf_counter() - start) * 1000, 2)
            logger.warning(
                "supervisor_subtask_failed",
                extra={
                    "task_id": task.task_id,
                    "agent_name": task.agent_name,
                    "error": str(exc),
                },
            )
            return SubTaskResult(
                task_id=task.task_id,
                agent_name=task.agent_name,
                status="error",
                error=str(exc),
                duration_ms=duration_ms,
            )
