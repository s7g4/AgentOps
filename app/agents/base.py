"""RoutableAgent — ABC for agents that participate in supervisor routing.

Design
──────
Existing pipeline agents (ClassifierAgent, PlannerAgent, etc.) are NOT
required to implement this interface — they operate via the FSM runtime.

RoutableAgent is for agents that can be addressed by name on the AgentBus:
the supervisor posts an AgentMessage to a named recipient, and the agent's
handle() method processes it and returns a reply.

Every handle() implementation should be:
  • Async — bus dispatch runs concurrent handles via asyncio.gather.
  • Idempotent — the same message may be retried if the bus detects a failure.
  • Self-contained — no shared mutable state between concurrent invocations.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from app.messaging.message import AgentMessage


class RoutableAgent(ABC):
    """Abstract base for all agents addressable via AgentBus.

    Attributes
    ----------
    name:        Unique agent identifier in AgentRegistry.  Used as the
                 routing key in AgentMessage.recipient.
    description: Human-readable description exposed at GET /agents.
    """

    name: str
    description: str

    @abstractmethod
    async def handle(self, message: AgentMessage) -> AgentMessage:
        """Process an incoming message and return a reply.

        The reply's ``reply_to`` field must be set to ``message.id``.
        """
        raise NotImplementedError
