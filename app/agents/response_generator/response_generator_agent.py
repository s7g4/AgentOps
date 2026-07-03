from __future__ import annotations

import inspect
from typing import cast

from app.providers.base import (
    AnyResponseProvider,
    ResponseProvider,
)


class DeterministicResponseProvider(ResponseProvider):
    def generate(
        self, intent: str, tool_outputs: list[dict[str, object]], original_message: str
    ) -> str:
        if intent == "refund" and tool_outputs:
            policy = tool_outputs[0].get("policy", "")
            return f"Refund policy: {policy}"
        if intent == "order_status" and tool_outputs:
            o = tool_outputs[0]
            return (
                f"Order {o.get('order_id')}: status={o.get('status')}"
                f" ETA={o.get('eta_days')} days"
            )
        return "Thanks — I'm checking that now."


class ResponseGeneratorAgent:
    """Generates a customer-facing response from intent and tool outputs.

    Accepts sync and async response providers interchangeably.
    """

    def __init__(self, provider: AnyResponseProvider | None = None) -> None:
        self.provider: AnyResponseProvider = provider or DeterministicResponseProvider()

    async def generate(
        self, intent: str, tool_outputs: list[dict[str, object]], original_message: str
    ) -> str:
        if inspect.iscoroutinefunction(self.provider.generate):
            return await self.provider.generate(  # type: ignore[no-any-return]
                intent, tool_outputs, original_message
            )
        return cast(str, self.provider.generate(intent, tool_outputs, original_message))
