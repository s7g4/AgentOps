"""Provider interfaces for AgentOps.

Two tiers:

Synchronous (``ClassificationProvider``, ``PlanningProvider``, etc.)
  Used by deterministic in-process providers and existing tests.
  No I/O, instant — safe to call directly from async code.

Asynchronous (``AsyncClassificationProvider``, etc.)
  Used by LLM-backed providers (OpenAI, Anthropic …) where the call is
  network-bound and MUST be awaited so the event loop remains responsive.

The agents accept *either* tier via a union type and detect at runtime
which calling convention to use (``asyncio.iscoroutinefunction``).
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from app.schemas.classification import Classification
from app.schemas.plan import ToolPlan
from app.schemas.verification import VerificationResult


# ── Synchronous ABCs ───────────────────────────────────────────────────────────

class ClassificationProvider(ABC):
    @abstractmethod
    def classify(self, message: str) -> Classification:
        raise NotImplementedError


class PlanningProvider(ABC):
    @abstractmethod
    def plan(self, intent: str, message: str) -> ToolPlan:
        raise NotImplementedError


class VerificationProvider(ABC):
    @abstractmethod
    def verify(
        self,
        intent: str,
        tool_outputs: list[dict[str, object]],
        original_message: str,
    ) -> VerificationResult:
        raise NotImplementedError


class ResponseProvider(ABC):
    @abstractmethod
    def generate(
        self,
        intent: str,
        tool_outputs: list[dict[str, object]],
        original_message: str,
    ) -> str:
        raise NotImplementedError


# ── Asynchronous ABCs ──────────────────────────────────────────────────────────

class AsyncClassificationProvider(ABC):
    """Async variant — use for LLM-backed providers to avoid blocking the loop."""

    @abstractmethod
    async def classify(self, message: str) -> Classification:
        raise NotImplementedError


class AsyncPlanningProvider(ABC):
    @abstractmethod
    async def plan(self, intent: str, message: str) -> ToolPlan:
        raise NotImplementedError


class AsyncVerificationProvider(ABC):
    @abstractmethod
    async def verify(
        self,
        intent: str,
        tool_outputs: list[dict[str, object]],
        original_message: str,
    ) -> VerificationResult:
        raise NotImplementedError


class AsyncResponseProvider(ABC):
    @abstractmethod
    async def generate(
        self,
        intent: str,
        tool_outputs: list[dict[str, object]],
        original_message: str,
    ) -> str:
        raise NotImplementedError


# ── Union types used by agents ─────────────────────────────────────────────────

AnyClassificationProvider = ClassificationProvider | AsyncClassificationProvider
AnyPlanningProvider = PlanningProvider | AsyncPlanningProvider
AnyVerificationProvider = VerificationProvider | AsyncVerificationProvider
AnyResponseProvider = ResponseProvider | AsyncResponseProvider
