from __future__ import annotations

from app.providers.base import (
    AnyVerificationProvider,
    AsyncVerificationProvider,
    VerificationProvider,
)
from app.schemas.verification import VerificationResult


class DeterministicVerificationProvider(VerificationProvider):
    def verify(
        self, intent: str, tool_outputs: list[dict[str, object]], original_message: str
    ) -> VerificationResult:
        if not tool_outputs:
            return VerificationResult(
                confidence=0.45, escalated=True, needs_human_reason="No tools executed"
            )
        return VerificationResult(confidence=0.8, escalated=False, needs_human_reason=None)


class VerifierAgent:
    """Verifies tool outputs and decides whether to escalate to a human.

    Accepts sync and async verification providers interchangeably.
    """

    def __init__(self, provider: AnyVerificationProvider | None = None) -> None:
        self.provider: AnyVerificationProvider = (
            provider or DeterministicVerificationProvider()
        )

    async def verify(
        self, intent: str, tool_outputs: list[dict[str, object]], original_message: str
    ) -> VerificationResult:
        if isinstance(self.provider, AsyncVerificationProvider):
            return await self.provider.verify(intent, tool_outputs, original_message)

        return self.provider.verify(intent, tool_outputs, original_message)
