"""AgentRegistry — named registry for RoutableAgent instances.

Mirrors the design of ToolRegistry:
  register(agent) → put into dict keyed by agent.name
  get(name)       → return agent or raise AgentNotFoundError
  names()         → list of registered names
  descriptions()  → list of (name, description) pairs for GET /agents

AgentRegistry.default() pre-registers the two built-in agents (echo,
summary) so the system works out of the box with no configuration.
"""

from __future__ import annotations

from app.agents.base import RoutableAgent
from app.exceptions import AgentNotFoundError


class AgentRegistry:
    """Thread-safe registry of named RoutableAgent instances.

    Registration is write-once: attempting to register a second agent
    under the same name raises ValueError immediately, preventing silent
    mis-configuration at startup.
    """

    def __init__(self) -> None:
        self._agents: dict[str, RoutableAgent] = {}

    def register(self, agent: RoutableAgent) -> None:
        """Register an agent.  Raises ValueError if the name is already taken."""
        if agent.name in self._agents:
            raise ValueError(f"Agent already registered: {agent.name!r}")
        self._agents[agent.name] = agent

    def get(self, name: str) -> RoutableAgent:
        """Return the agent registered under ``name``.

        Raises AgentNotFoundError if the name is not registered.
        """
        if name not in self._agents:
            raise AgentNotFoundError(
                f"No agent registered with name {name!r}. "
                f"Available: {list(self._agents)}"
            )
        return self._agents[name]

    def names(self) -> list[str]:
        """Return a sorted list of all registered agent names."""
        return sorted(self._agents)

    def descriptions(self) -> list[dict[str, str]]:
        """Return name + description pairs — used by GET /agents."""
        return [
            {"name": a.name, "description": a.description}
            for a in sorted(self._agents.values(), key=lambda a: a.name)
        ]

    def __len__(self) -> int:
        return len(self._agents)

    @classmethod
    def default(cls) -> AgentRegistry:
        """Return a registry pre-loaded with built-in agents."""
        from app.agents.builtin import EchoAgent, SummaryAgent  # noqa: PLC0415

        reg = cls()
        reg.register(EchoAgent())
        reg.register(SummaryAgent())
        return reg
