"""Route a goal through the supervisor, both explicitly and via the decomposer.

Run:
    python -m app.main &
    python examples/03_route_goal.py
"""

from __future__ import annotations

from agentops_client import AgentOpsClient


def main() -> None:
    with AgentOpsClient(base_url="http://localhost:8000") as client:
        print("registered agents:")
        for agent in client.list_agents():
            print(f"  {agent.name}: {agent.description}")

        # Explicit subtasks — deterministic, no decomposer call.
        explicit = client.route_goal(
            goal="summarize and echo this ticket",
            subtasks=[
                {"agent_name": "summary", "payload": {"ticket": "customer wants a refund"}},
                {"agent_name": "echo", "payload": {"ticket": "customer wants a refund"}},
            ],
        )
        print(f"\nexplicit routing status: {explicit.status}")
        for result in explicit.results:
            print(f"  {result.agent_name}: {result.status} -> {result.output}")

        # Omit subtasks to use the configured decomposer (OpenAI if
        # OPENAI_API_KEY is set, otherwise a deterministic keyword matcher).
        decomposed = client.route_goal(goal="please echo this support request")
        print(f"\ndecomposed routing status: {decomposed.status}")
        for result in decomposed.results:
            print(f"  {result.agent_name}: {result.status} -> {result.output}")


if __name__ == "__main__":
    main()
