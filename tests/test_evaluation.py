from __future__ import annotations

from app.evaluation.evaluator import EvaluationResult, evaluate_pipeline
from app.evaluation.fake_data import build_fake_tickets


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
