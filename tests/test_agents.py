"""Tests for ClassifierAgent, PlannerAgent, and their deterministic providers."""
from __future__ import annotations

from app.agents.classifier.classifier_agent import ClassifierAgent
from app.agents.planner.planner_agent import PlannerAgent


class TestClassifierAgent:
    async def test_refund_intent(self) -> None:
        agent = ClassifierAgent()
        result = await agent.classify("I want my money back")
        assert result.intent == "refund"
        assert result.confidence == 0.92

    async def test_refund_keyword(self) -> None:
        result = await ClassifierAgent().classify("Can you process a refund?")
        assert result.intent == "refund"

    async def test_order_status_intent(self) -> None:
        result = await ClassifierAgent().classify("What is my order status?")
        assert result.intent == "order_status"
        assert result.confidence == 0.9

    async def test_order_tracking_keyword(self) -> None:
        result = await ClassifierAgent().classify("Tracking my package")
        assert result.intent == "order_status"

    async def test_where_is_my_keyword(self) -> None:
        result = await ClassifierAgent().classify("Where is my shipment?")
        assert result.intent == "order_status"

    async def test_spam_intent(self) -> None:
        result = await ClassifierAgent().classify("This is spam")
        assert result.intent == "spam"
        assert result.confidence == 0.95

    async def test_general_question_fallback(self) -> None:
        result = await ClassifierAgent().classify("Hello, I have a question")
        assert result.intent == "general_question"
        assert result.confidence == 0.6

    async def test_case_insensitive_matching(self) -> None:
        result = await ClassifierAgent().classify("REFUND MY ORDER PLEASE")
        assert result.intent == "refund"

    async def test_custom_provider_is_used(self) -> None:
        from app.providers.base import ClassificationProvider  # noqa: PLC0415
        from app.schemas.classification import Classification  # noqa: PLC0415

        class FixedProvider(ClassificationProvider):
            def classify(self, message: str) -> Classification:
                return Classification(intent="custom", confidence=1.0)

        agent = ClassifierAgent(provider=FixedProvider())
        assert (await agent.classify("anything")).intent == "custom"


class TestPlannerAgent:
    async def test_refund_generates_refund_policy_call(self) -> None:
        agent = PlannerAgent()
        plan = await agent.plan("refund", "I need a refund")
        assert len(plan.tool_calls) == 1
        assert plan.tool_calls[0]["tool_name"] == "refund_policy"

    async def test_order_status_generates_check_order_call(self) -> None:
        agent = PlannerAgent()
        plan = await agent.plan("order_status", "Where is order #12345?")
        assert len(plan.tool_calls) == 1
        assert plan.tool_calls[0]["tool_name"] == "check_order_status"

    async def test_order_status_extracts_order_id(self) -> None:
        agent = PlannerAgent()
        plan = await agent.plan("order_status", "Where is order #12345?")
        # Planner lowercases and splits on whitespace; strips leading #.
        assert plan.tool_calls[0]["input"]["order_id"] == "12345?"

    async def test_unknown_intent_generates_no_tool_calls(self) -> None:
        agent = PlannerAgent()
        plan = await agent.plan("general_question", "Hello there")
        assert plan.tool_calls == []

    async def test_order_id_defaults_to_unknown(self) -> None:
        agent = PlannerAgent()
        plan = await agent.plan("order_status", "Where is my order?")
        assert plan.tool_calls[0]["input"]["order_id"] == "unknown"
