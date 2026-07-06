"""PipelineAgent — exposes the FSM pipeline as a RoutableAgent.

Design
──────
Before this, the classify → plan → execute → verify → respond pipeline
(AgentOpsRuntime) was only reachable via POST /messages.  The workflow
engine and the supervisor/bus had no way to invoke it — a workflow
couldn't run a support ticket through the pipeline as a step, and a
decomposed goal couldn't be routed to it as a subtask.

PipelineAgent closes that gap by wrapping AgentOpsRuntime.handle_message
behind the same RoutableAgent interface as every other bus agent. It does
not change the runtime itself — it's a thin adapter, so the pipeline keeps
its own trace store, metrics, and FSM enforcement exactly as before,
whether it's invoked directly via /messages or indirectly via a workflow
step or a supervisor subtask.

Payload contract
────────────────
Request payload matches MessageRequest: {"message": str, "customer_id": str,
"source": str (optional)}.  Reply payload matches MessageResponse:
{"trace_id", "intent", "confidence", "escalated", "response"}.
"""

from __future__ import annotations

from app.agents.base import RoutableAgent
from app.messaging.message import AgentMessage
from app.runtime.runtime import AgentOpsRuntime
from app.schemas.messages import MessageRequest


class PipelineAgent(RoutableAgent):
    """Adapts AgentOpsRuntime to the RoutableAgent interface.

    Registered by default as ``"support_pipeline"`` so it can be reached
    from a workflow agent-step or a supervisor subtask without any special
    casing at the call site.
    """

    name = "support_pipeline"
    description = (
        "Runs a message through the full classify/plan/execute/verify/respond "
        "pipeline and returns the same payload as POST /messages."
    )

    def __init__(self, runtime: AgentOpsRuntime) -> None:
        self._runtime = runtime

    async def handle(self, message: AgentMessage) -> AgentMessage:
        request = MessageRequest(
            message=str(message.payload["message"]),
            customer_id=str(message.payload.get("customer_id", message.sender)),
            source=message.payload.get("source", "other"),
        )
        response = await self._runtime.handle_message(request)
        return AgentMessage(
            sender=self.name,
            recipient=message.sender,
            payload=response.model_dump(),
            reply_to=message.id,
        )
