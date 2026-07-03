"""Core message types for the AgentOps multi-agent messaging system.

Three main types:

AgentMessage
  The atom of communication on the AgentBus.  Every send() call posts
  one AgentMessage and receives one AgentMessage reply.

SubTask
  A named routing directive: which agent to call and with what payload.
  The supervisor converts a RouteRequest into a list of SubTasks before
  dispatching them concurrently on the bus.

SubTaskResult
  The outcome of a single dispatched SubTask: status, output, error,
  and wall-clock duration.  The supervisor collects one per SubTask and
  assembles them into a RoutingResult.

RoutingResult
  The aggregate outcome of a full supervisor routing run.  Contains all
  SubTaskResults and an overall status:
    "completed" — all subtasks succeeded
    "partial"   — at least one succeeded, at least one failed
    "failed"    — all subtasks failed
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any, Literal

from app.schemas.trace import utc_now_iso


@dataclass
class AgentMessage:
    """A single message exchanged between agents on the AgentBus.

    Attributes
    ----------
    sender:     Name of the sending agent, or ``"user"`` for requests from
                the API layer.
    recipient:  Name of the target agent in AgentRegistry.
    payload:    Arbitrary key-value data for the recipient.
    id:         Auto-generated UUID.  Used as the correlation key for replies.
    reply_to:   ID of the message this is replying to, or None for new messages.
    created_at: ISO-8601 UTC timestamp.
    """

    sender: str
    recipient: str
    payload: dict[str, Any]
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    reply_to: str | None = None
    created_at: str = field(default_factory=utc_now_iso)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "sender": self.sender,
            "recipient": self.recipient,
            "payload": self.payload,
            "reply_to": self.reply_to,
            "created_at": self.created_at,
        }


@dataclass
class SubTask:
    """A routing directive: which agent to call and with what payload.

    Attributes
    ----------
    task_id:    Unique identifier for this subtask within a routing run.
    agent_name: Must match a name registered in AgentRegistry.
    payload:    Input passed as the AgentMessage payload to the agent.
    """

    task_id: str
    agent_name: str
    payload: dict[str, Any] = field(default_factory=dict)


@dataclass
class SubTaskResult:
    """The outcome of a single executed SubTask.

    Attributes
    ----------
    task_id:     Correlates with SubTask.task_id.
    agent_name:  The agent that handled this subtask.
    status:      ``"success"`` or ``"error"``.
    output:      The reply payload from the agent, or None on error.
    error:       Error message string, or None on success.
    duration_ms: Wall-clock execution time in milliseconds.
    """

    task_id: str
    agent_name: str
    status: Literal["success", "error"]
    duration_ms: float
    output: dict[str, Any] | None = None
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "task_id": self.task_id,
            "agent_name": self.agent_name,
            "status": self.status,
            "output": self.output,
            "error": self.error,
            "duration_ms": self.duration_ms,
        }


@dataclass
class RoutingResult:
    """Aggregate outcome of a full supervisor routing run.

    Attributes
    ----------
    routing_id:  UUID for this routing run.
    goal:        The original goal string from the RouteRequest.
    results:     One SubTaskResult per dispatched SubTask.
    created_at:  ISO-8601 UTC timestamp of when routing was initiated.
    duration_ms: Total wall-clock time for the entire routing run.

    status: Derived from results:
      "completed" — all subtasks succeeded
      "partial"   — at least one succeeded AND at least one failed
      "failed"    — all subtasks failed (or no subtasks)
    """

    routing_id: str
    goal: str
    results: list[SubTaskResult]
    duration_ms: float
    created_at: str = field(default_factory=utc_now_iso)

    @property
    def status(self) -> str:
        if not self.results:
            return "failed"
        successes = sum(1 for r in self.results if r.status == "success")
        if successes == len(self.results):
            return "completed"
        if successes == 0:
            return "failed"
        return "partial"
