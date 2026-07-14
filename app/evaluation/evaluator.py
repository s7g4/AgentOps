from __future__ import annotations

import asyncio
from dataclasses import dataclass
from statistics import mean
from time import perf_counter

from app.agents.classifier.classifier_agent import ClassifierAgent
from app.agents.planner.planner_agent import PlannerAgent
from app.evaluation.fake_data import FakeTicket


@dataclass(frozen=True)
class EvaluationResult:
    total_tickets: int
    classification_accuracy: float
    tool_selection_accuracy: float
    average_latency_ms: float
    average_cost_usd: float
    escalation_rate: float
    failure_rate: float


class Evaluator:
    def __init__(self) -> None:
        self.classifier = ClassifierAgent()
        self.planner = PlannerAgent()

    async def evaluate_ticket(
        self, ticket: FakeTicket
    ) -> tuple[float, float, float, float, float, float]:
        start = perf_counter()
        classification = await self.classifier.classify(ticket.message)
        plan = await self.planner.plan(classification.intent, ticket.message)
        latency_ms = (perf_counter() - start) * 1000.0

        expected_intent = self._expected_intent(ticket.message)
        intent_score = 1.0 if classification.intent == expected_intent else 0.0

        expected_tool_count = self._expected_tool_count(expected_intent)
        tool_score = 1.0 if len(plan.tool_calls) == expected_tool_count else 0.0

        cost_usd = 0.0
        # Always 0.0 — this harness stops after classify+plan, so there's no
        # verifier run to report a real escalation or failure from.
        escalation = 0.0
        failure = 0.0

        return (
            intent_score,
            tool_score,
            latency_ms,
            cost_usd,
            escalation,
            failure,
        )

    def _expected_intent(self, message: str) -> str:
        """Ground truth for classification accuracy.

        Deliberately has no "escalate to a human" branch — escalation is a
        VerifierAgent outcome (VerificationResult.escalated) decided after
        classification runs, and DeterministicClassifierProvider doesn't
        produce it as an intent. An earlier version of this method expected
        one anyway, which made one fake ticket template ("please escalate to
        a human...") mismatch on every run regardless of classifier quality,
        silently capping classification_accuracy below 100%.
        """
        lowered = message.lower()
        if "refund" in lowered or "money back" in lowered:
            return "refund"
        if "order status" in lowered or "tracking" in lowered or "where is my" in lowered:
            return "order_status"
        if "spam" in lowered:
            return "spam"
        return "general_question"

    def _expected_tool_count(self, intent: str) -> int:
        if intent == "refund":
            return 1
        if intent == "order_status":
            return 1
        return 0


async def evaluate_pipeline_async(tickets: list[FakeTicket]) -> EvaluationResult:
    evaluator = Evaluator()
    results = await asyncio.gather(*[evaluator.evaluate_ticket(ticket) for ticket in tickets])

    classification_accuracy = mean(score[0] for score in results) if results else 0.0
    tool_selection_accuracy = mean(score[1] for score in results) if results else 0.0
    average_latency_ms = mean(score[2] for score in results) if results else 0.0
    average_cost_usd = mean(score[3] for score in results) if results else 0.0
    escalation_rate = mean(score[4] for score in results) if results else 0.0
    failure_rate = mean(score[5] for score in results) if results else 0.0

    return EvaluationResult(
        total_tickets=len(tickets),
        classification_accuracy=classification_accuracy,
        tool_selection_accuracy=tool_selection_accuracy,
        average_latency_ms=average_latency_ms,
        average_cost_usd=average_cost_usd,
        escalation_rate=escalation_rate,
        failure_rate=failure_rate,
    )


def evaluate_pipeline(tickets: list[FakeTicket]) -> EvaluationResult:
    """Synchronous entrypoint wrapper for backwards compatibility."""
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None

    if loop and loop.is_running():
        # Running in an event loop (e.g. FastAPI request thread)
        return asyncio.run_coroutine_threadsafe(
            evaluate_pipeline_async(tickets), loop
        ).result()
    else:
        return asyncio.run(evaluate_pipeline_async(tickets))
