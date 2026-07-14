from __future__ import annotations

from app.evaluation.evaluator import EvaluationResult, Evaluator, evaluate_pipeline
from app.evaluation.fake_data import FakeTicket, build_fake_tickets
from app.schemas.classification import Classification
from app.schemas.plan import ToolPlan


class _FakeClassifier:
    def __init__(self, intent: str, confidence: float = 0.9) -> None:
        self._intent = intent
        self._confidence = confidence

    async def classify(self, message: str) -> Classification:
        return Classification(intent=self._intent, confidence=self._confidence)


class _FakePlanner:
    def __init__(self, tool_calls: list[dict[str, object]]) -> None:
        self._tool_calls = tool_calls

    async def plan(self, intent: str, message: str) -> ToolPlan:
        return ToolPlan(tool_calls=self._tool_calls)


def test_evaluate_pipeline_returns_expected_summary() -> None:
    tickets = build_fake_tickets(5)
    result = evaluate_pipeline(tickets)

    assert isinstance(result, EvaluationResult)
    assert result.total_tickets == 5
    assert result.classification_accuracy >= 0.0
    assert result.tool_selection_accuracy >= 0.0
    assert result.average_latency_ms >= 0.0
    assert result.average_cost_usd >= 0.0
    assert result.escalation_rate >= 0.0
    assert result.failure_rate >= 0.0


def test_evaluate_pipeline_empty_ticket_list_does_not_crash() -> None:
    result = evaluate_pipeline([])

    assert result.total_tickets == 0
    assert result.classification_accuracy == 0.0
    assert result.tool_selection_accuracy == 0.0


async def test_evaluate_ticket_scores_one_on_correct_classification() -> None:
    """Regression test: the deterministic classifier's real intents and this
    harness's ground truth (_expected_intent) must actually agree — one fake
    ticket template used to always mismatch (see _expected_intent's
    docstring), silently capping accuracy below 100% regardless of
    classifier quality. Every real classifier intent here has to score 1.0
    against a matching real fake ticket, not just "some number >= 0"."""
    evaluator = Evaluator()
    for ticket in build_fake_tickets(6):  # one of each template
        intent_score, tool_score, *_ = await evaluator.evaluate_ticket(ticket)
        assert intent_score == 1.0, f"classifier/ground-truth mismatch on: {ticket.message!r}"
        assert tool_score == 1.0, f"tool-count/ground-truth mismatch on: {ticket.message!r}"


async def test_evaluate_ticket_scores_zero_on_wrong_classification() -> None:
    evaluator = Evaluator()
    evaluator.classifier = _FakeClassifier(intent="spam")  # type: ignore[assignment]

    ticket = FakeTicket(customer_id="c1", message="I need a refund for my broken item")
    intent_score, _tool_score, *_ = await evaluator.evaluate_ticket(ticket)

    assert intent_score == 0.0


async def test_evaluate_ticket_scores_zero_on_wrong_tool_count() -> None:
    evaluator = Evaluator()
    # Ground truth for a refund message expects exactly 1 tool call.
    evaluator.planner = _FakePlanner(tool_calls=[])  # type: ignore[assignment]

    ticket = FakeTicket(customer_id="c1", message="I need a refund for my broken item")
    _intent_score, tool_score, *_ = await evaluator.evaluate_ticket(ticket)

    assert tool_score == 0.0


def test_expected_intent_never_expects_human_escalation() -> None:
    """The classifier has no "human_escalation" intent — that's a
    VerifierAgent outcome (VerificationResult.escalated), decided after
    classification, not a classification category. Ground truth must not
    expect a value the classifier is structurally incapable of producing."""
    evaluator = Evaluator()
    expected = evaluator._expected_intent(
        "Please escalate this issue to a human because the booking is incorrect."
    )
    assert expected != "human_escalation"
    assert expected == "general_question"
