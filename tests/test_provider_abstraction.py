"""Tests for provider injection pattern across all four agents."""
from __future__ import annotations

from app.agents.classifier.classifier_agent import ClassifierAgent
from app.agents.planner.planner_agent import PlannerAgent
from app.agents.response_generator.response_generator_agent import ResponseGeneratorAgent
from app.agents.verifier.verifier_agent import VerifierAgent
from app.providers.base import (
    ClassificationProvider,
    PlanningProvider,
    ResponseProvider,
    VerificationProvider,
)
from app.schemas.classification import Classification
from app.schemas.plan import ToolPlan
from app.schemas.verification import VerificationResult


class StubProvider(ClassificationProvider):
    def classify(self, message: str) -> Classification:
        return Classification(intent="refund", confidence=0.99)


class StubPlanningProvider(PlanningProvider):
    def plan(self, intent: str, message: str) -> ToolPlan:
        return ToolPlan(tool_calls=[{"tool_name": "demo_tool", "input": {"intent": intent}}])


class StubVerificationProvider(VerificationProvider):
    def verify(
        self, intent: str, tool_outputs: list[dict[str, object]], original_message: str
    ) -> VerificationResult:
        return VerificationResult(confidence=0.97, escalated=False, needs_human_reason=None)


class StubResponseProvider(ResponseProvider):
    def generate(
        self, intent: str, tool_outputs: list[dict[str, object]], original_message: str
    ) -> str:
        return "custom response"


async def test_classifier_accepts_injected_provider() -> None:
    classifier = ClassifierAgent(provider=StubProvider())
    result = await classifier.classify("Please refund my order")
    assert result.intent == "refund"
    assert result.confidence == 0.99


async def test_planner_accepts_injected_provider() -> None:
    planner = PlannerAgent(provider=StubPlanningProvider())
    result = await planner.plan("refund", "Please refund my order")
    assert result.tool_calls[0]["tool_name"] == "demo_tool"


async def test_verifier_accepts_injected_provider() -> None:
    verifier = VerifierAgent(provider=StubVerificationProvider())
    result = await verifier.verify("refund", [], "Please refund my order")
    assert result.confidence == 0.97
    assert result.escalated is False


async def test_response_generator_accepts_injected_provider() -> None:
    responder = ResponseGeneratorAgent(provider=StubResponseProvider())
    result = await responder.generate("refund", [], "Please refund my order")
    assert result == "custom response"
