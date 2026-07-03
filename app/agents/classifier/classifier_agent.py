from __future__ import annotations

import inspect
from typing import cast

from app.providers.base import (
    AnyClassificationProvider,
    ClassificationProvider,
)
from app.schemas.classification import Classification


class DeterministicClassifierProvider(ClassificationProvider):
    def classify(self, message: str) -> Classification:
        m = message.lower()
        if "refund" in m or "money back" in m:
            return Classification(intent="refund", confidence=0.92)
        if "order status" in m or "tracking" in m or "where is my" in m:
            return Classification(intent="order_status", confidence=0.9)
        if "spam" in m:
            return Classification(intent="spam", confidence=0.95)
        return Classification(intent="general_question", confidence=0.6)


class ClassifierAgent:
    """Classifies customer messages into structured intents.

    Accepts both sync (``ClassificationProvider``) and async
    (``AsyncClassificationProvider``) providers.  The ``classify`` coroutine
    detects which calling convention to use at runtime, so the same agent
    class works for tests (deterministic, sync) and production (LLM, async).
    """

    def __init__(self, provider: AnyClassificationProvider | None = None) -> None:
        self.provider: AnyClassificationProvider = (
            provider or DeterministicClassifierProvider()
        )

    async def classify(self, message: str) -> Classification:
        if inspect.iscoroutinefunction(self.provider.classify):
            return await self.provider.classify(message)  # type: ignore[no-any-return]
        return cast(Classification, self.provider.classify(message))
