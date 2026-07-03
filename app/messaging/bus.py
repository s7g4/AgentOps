"""AgentBus — async in-process message bus.

Design
──────
The bus has one job: given an AgentMessage addressed to a named recipient,
look the agent up in AgentRegistry, call handle(), and return the reply.

Why not a queue?
  A pub/sub queue (asyncio.Queue, Redis Streams) is needed when producers
  and consumers run in different coroutines or processes.  Here, every
  send() is a request/reply pair that the supervisor awaits directly, so
  a queue would add latency for zero benefit.  The bus abstraction still
  lets us swap the backing to Redis Pub/Sub in V5 without changing call
  sites.

Concurrency:
  send() is a coroutine — multiple concurrent sends (from asyncio.gather
  in the supervisor) each run the target agent's handle() independently.
  No shared mutable state means no locking required.

Error handling:
  Any exception raised inside handle() propagates to the caller.  The
  supervisor catches it and records a SubTaskResult with status="error".
  The bus itself does not retry.
"""

from __future__ import annotations

import logging

from app.agents.registry import AgentRegistry
from app.messaging.message import AgentMessage

logger = logging.getLogger(__name__)


class AgentBus:
    """Synchronous-style async message bus for single-process deployments.

    Usage::

        bus = AgentBus()
        reply = await bus.send(message, registry)
    """

    async def send(
        self,
        message: AgentMessage,
        registry: AgentRegistry,
    ) -> AgentMessage:
        """Route a message to its recipient and return the reply.

        Parameters
        ----------
        message:  The AgentMessage to dispatch.  ``message.recipient`` must
                  match a name registered in the registry.
        registry: The AgentRegistry to look up the recipient in.

        Returns
        -------
        AgentMessage  The reply produced by the recipient's handle() method.

        Raises
        ------
        AgentNotFoundError  If ``message.recipient`` is not in the registry.
        Any exception raised by the recipient's handle() method.
        """
        logger.debug(
            "bus_send",
            extra={
                "msg_id": message.id,
                "sender": message.sender,
                "recipient": message.recipient,
            },
        )
        agent = registry.get(message.recipient)  # raises AgentNotFoundError if missing
        reply = await agent.handle(message)

        logger.debug(
            "bus_reply",
            extra={
                "msg_id": message.id,
                "reply_id": reply.id,
                "sender": reply.sender,
            },
        )
        return reply
