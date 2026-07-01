import asyncio
from fastapi import APIRouter

from app.evaluation.evaluator import evaluate_pipeline
from app.evaluation.fake_data import build_fake_tickets

evaluation_router = APIRouter(prefix="/evaluation", tags=["evaluation"])


@evaluation_router.get("")
async def evaluation_status() -> dict[str, object]:
    tickets = build_fake_tickets(25)
    # Run CPU-bound evaluation in thread pool to avoid blocking event loop.
    result = await asyncio.to_thread(evaluate_pipeline, tickets)
    return {
        "status": "completed",
        "total_tickets": result.total_tickets,
        "classification_accuracy": round(result.classification_accuracy, 4),
        "tool_selection_accuracy": round(result.tool_selection_accuracy, 4),
        "average_latency_ms": round(result.average_latency_ms, 4),
        "average_cost_usd": round(result.average_cost_usd, 4),
        "escalation_rate": round(result.escalation_rate, 4),
        "failure_rate": round(result.failure_rate, 4),
    }
