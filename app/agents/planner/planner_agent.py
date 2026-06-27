from __future__ import annotations

import inspect

from app.providers.base import AnyPlanningProvider, PlanningProvider
from app.schemas.plan import ToolPlan


class DeterministicPlanningProvider(PlanningProvider):
    def plan(self, intent: str, message: str) -> ToolPlan:
        m = message.lower()
        calls: list[dict[str, object]] = []

        if intent == "refund":
            calls.append({"tool_name": "refund_policy", "input": {}})
        elif intent == "order_status":
            order_id = "unknown"
            for token in m.split():
                if token.startswith("#"):
                    order_id = token.strip("#")
                    break
            calls.append({"tool_name": "check_order_status", "input": {"order_id": order_id}})
        return ToolPlan(tool_calls=calls)


class PlannerAgent:
    """Produces a ToolPlan from a classified intent.

    Accepts sync and async planning providers interchangeably.
    """

    def __init__(self, provider: AnyPlanningProvider | None = None) -> None:
        self.provider: AnyPlanningProvider = provider or DeterministicPlanningProvider()

    async def plan(self, intent: str, message: str) -> ToolPlan:
        if inspect.iscoroutinefunction(self.provider.plan):
            return await self.provider.plan(intent, message)  # type: ignore[return-value]
        return self.provider.plan(intent, message)  # type: ignore[return-value]
