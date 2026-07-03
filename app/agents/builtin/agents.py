"""Built-in routable agents bundled with AgentOps.

These serve two purposes:
1. Make ``AgentRegistry.default()`` immediately functional without any
   external configuration.
2. Provide reference implementations that show how to write a RoutableAgent.

EchoAgent   — returns the payload unchanged; useful for integration tests
              and smoke-testing bus connectivity.
SummaryAgent — returns a summary of the payload (key count, key names, types);
              useful for debugging and introspection flows.
"""

from __future__ import annotations

from app.agents.base import RoutableAgent
from app.messaging.message import AgentMessage


class EchoAgent(RoutableAgent):
    """Returns the incoming payload unchanged.

    Use-cases:
    - Integration tests that need a real registered agent.
    - Smoke-testing bus connectivity end-to-end.
    - Passthrough node in a multi-step routing chain.
    """

    name = "echo"
    description = "Returns the request payload unchanged. Useful for testing."

    async def handle(self, message: AgentMessage) -> AgentMessage:
        return AgentMessage(
            sender=self.name,
            recipient=message.sender,
            payload={**message.payload, "_echo": True},
            reply_to=message.id,
        )


class SummaryAgent(RoutableAgent):
    """Produces a structural summary of the incoming payload.

    Returns:
      - ``key_count``: number of top-level keys
      - ``keys``: list of top-level key names
      - ``types``: mapping of key → type name
      - ``original_sender``: who sent the message
    """

    name = "summary"
    description = "Returns a structural summary of the payload (keys, types, sender)."

    async def handle(self, message: AgentMessage) -> AgentMessage:
        payload = message.payload
        summary: dict[str, object] = {
            "key_count": len(payload),
            "keys": list(payload.keys()),
            "types": {k: type(v).__name__ for k, v in payload.items()},
            "original_sender": message.sender,
        }
        return AgentMessage(
            sender=self.name,
            recipient=message.sender,
            payload=summary,
            reply_to=message.id,
        )
