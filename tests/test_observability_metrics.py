"""Tests for Prometheus metric counters and trace timeline observability."""
from __future__ import annotations

import asyncio

from fastapi.testclient import TestClient

from app.main import app


def test_metrics_tool_counters_exist() -> None:
    with TestClient(app) as client:
        r = client.post(
            "/messages",
            json={"source": "ticket", "customer_id": "c1", "message": "Need help with refund"},
        )
        assert r.status_code == 200

        metrics_r = client.get("/metrics")
        assert metrics_r.status_code == 200
        text = metrics_r.text

        assert "agentops_tool_execution_total" in text
        assert "agentops_tool_execution_latency_seconds" in text


def test_trace_contains_state_transition_events_and_structured_context() -> None:
    with TestClient(app) as client:
        response = client.post(
            "/messages",
            json={"source": "ticket", "customer_id": "c1", "message": "Need help with refund"},
        )
        assert response.status_code == 200
        trace_id = response.json()["trace_id"]

        # Fetch trace via async store — run in event loop.
        store = app.state.trace_store
        trace = asyncio.run(store.get(trace_id))
        assert trace is not None
        assert any(event.name == "state:received" for event in trace.timeline)
        assert any(event.name == "state:completed" for event in trace.timeline)
        assert any(event.data.get("trace_id") == trace_id for event in trace.timeline)
        assert any("duration_ms" in event.data for event in trace.timeline)
        assert any(event.name == "tool_execution" for event in trace.timeline)


def test_metrics_verifier_escalation_counter_present() -> None:
    with TestClient(app) as client:
        r = client.post(
            "/messages",
            json={
                "source": "ticket",
                "customer_id": "c1",
                "message": "Where is my order #missing-123?",
            },
        )
        assert r.status_code == 200

        metrics_r = client.get("/metrics")
        assert metrics_r.status_code == 200
        assert "agentops_verifier_escalations_total" in metrics_r.text
