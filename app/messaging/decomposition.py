"""Agent task decomposition providers.

Provides decomposition of high-level goals into subtask lists.
"""

from __future__ import annotations

import json
import logging
from abc import ABC, abstractmethod

from app.config.settings import load_settings
from app.exceptions import AgentRoutingError, ConfigurationError
from app.messaging.message import SubTask

logger = logging.getLogger(__name__)


class DecompositionProvider(ABC):
    """Base provider for task decomposition."""

    @abstractmethod
    async def decompose(
        self,
        goal: str,
        available_agents: list[str],
    ) -> list[SubTask]:
        """Decompose a goal into a list of SubTasks.

        Parameters
        ----------
        goal:             The high-level goal string.
        available_agents: List of registered agent names.

        Returns
        -------
        A list of SubTasks to execute.
        """
        raise NotImplementedError


class DeterministicDecompositionProvider(DecompositionProvider):
    """Keyword-based deterministic task decomposition.

    Used in local development, testing, or when OpenAI API is disabled.
    """

    async def decompose(
        self,
        goal: str,
        available_agents: list[str],
    ) -> list[SubTask]:
        goal_lower = goal.lower()
        subtasks: list[SubTask] = []

        # Simple keyword matching to decide which agents to invoke
        if "echo" in goal_lower:
            if "echo" in available_agents:
                subtasks.append(
                    SubTask(
                        task_id="task_echo",
                        agent_name="echo",
                        payload={"message": goal, "source": "deterministic_decomp"},
                    )
                )
        if "summar" in goal_lower:
            if "summary" in available_agents:
                subtasks.append(
                    SubTask(
                        task_id="task_summary",
                        agent_name="summary",
                        payload={"text": goal, "source": "deterministic_decomp"},
                    )
                )

        # Fallback if no keywords matched
        if not subtasks:
            # Dispatch to echo if available
            if "echo" in available_agents:
                fallback = "echo"
            elif available_agents:
                fallback = available_agents[0]
            else:
                fallback = None

            if fallback:
                subtasks.append(
                    SubTask(
                        task_id="task_fallback",
                        agent_name=fallback,
                        payload={"message": goal, "fallback": True},
                    )
                )

        return subtasks


class OpenAIDecompositionProvider(DecompositionProvider):
    """Decomposes goals using OpenAI chat completion API."""

    def __init__(self, api_key: str | None = None, model: str = "gpt-4o-mini") -> None:
        settings = load_settings()
        key = api_key or settings.openai_api_key
        if not key:
            raise ConfigurationError(
                "OpenAIDecompositionProvider requires OPENAI_API_KEY. "
                "Configure it in your environment or pass it explicitly."
            )
        from openai import AsyncOpenAI  # noqa: PLC0415

        self._client = AsyncOpenAI(api_key=key)
        self._model = model

    async def decompose(
        self,
        goal: str,
        available_agents: list[str],
    ) -> list[SubTask]:
        if not available_agents:
            raise AgentRoutingError("No agents available for task decomposition.")

        system_prompt = (
            "You are a task decomposition assistant. Given a goal and a list of available agents, "
            "decompose the goal into a list of subtasks. "
            "Respond ONLY with a JSON object in the format:\n"

            "{\n"
            '  "subtasks": [\n'
            "    {\n"
            '      "task_id": "unique_string",\n'
            '      "agent_name": "one of the available agents",\n'
            '      "payload": { ... input dictionary for the agent ... }\n'
            "    }\n"
            "  ]\n"
            "}"
        )

        user_content = f"Goal: {goal}\nAvailable Agents: {available_agents}"

        try:
            response = await self._client.chat.completions.create(
                model=self._model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_content},
                ],
                response_format={"type": "json_object"},
                temperature=0.0,
            )

            raw_text = response.choices[0].message.content
            if not raw_text:
                raise AgentRoutingError("OpenAI returned an empty response.")

            parsed = json.loads(raw_text)
            subtask_dicts = parsed.get("subtasks", [])

            subtasks: list[SubTask] = []
            for d in subtask_dicts:
                agent_name = d["agent_name"]
                if agent_name not in available_agents:
                    logger.warning(
                        "decomposer_suggested_unknown_agent",
                        extra={"agent_name": agent_name, "available": available_agents},
                    )
                    continue  # skip invalid agents

                subtasks.append(
                    SubTask(
                        task_id=d["task_id"],
                        agent_name=agent_name,
                        payload=d.get("payload", {}),
                    )
                )

            if not subtasks:
                raise AgentRoutingError("No valid subtasks were decomposed from the goal.")

            return subtasks

        except Exception as exc:
            if not isinstance(exc, AgentRoutingError):
                raise AgentRoutingError(f"OpenAI decomposition failed: {exc}") from exc
            raise
