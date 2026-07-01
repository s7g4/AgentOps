"""Tests for runtime observability: tool metrics, trace events, escalation."""
from __future__ import annotations

import asyncio

from fastapi.testclient import TestClient

from app.main import app


def test_tool_execution_metrics_increment_on_success() -> None:
    with TestClient(app) as client:
        r = client.post(
            "/messages",
            json={"source": "ticket", "customer_id": "c1", "message": "I want a refund"},
        )
        assert r.status_code == 200

        m = client.get("/metrics")
        assert "agentops_tool_execution_total" in m.text
        assert 'status="success"' in m.text


def test_tool_execution_metrics_increment_on_error() -> None:
    with TestClient(app) as client:
        # Missing order ID causes check_order_status to raise ToolValidationError.
        r = client.post(
            "/messages",
            json={"source": "ticket", "customer_id": "c1", "message": "Where is my order?"},
        )
        assert r.status_code == 200  # runtime returns safe FAILED response

        m = client.get("/metrics")
        assert "agentops_tool_execution_total" in m.text


def test_verifier_escalation_metric_counts() -> None:
    """No-tool-output path triggers deterministic escalation."""
    with TestClient(app) as client:
        # general_question produces no tool calls → verifier escalates.
        r = client.post(
            "/messages",
            json={"source": "ticket", "customer_id": "c1", "message": "Hello there"},
        )
        assert r.status_code == 200

        m = client.get("/metrics")
        assert "agentops_verifier_escalations_total" in m.text


def test_trace_timeline_includes_observability_events() -> None:
    with TestClient(app) as client:
        r = client.post(
            "/messages",
            json={"source": "ticket", "customer_id": "c1", "message": "I want a refund"},
        )
        assert r.status_code == 200
        trace_id = r.json()["trace_id"]

        store = app.state.trace_store
        trace = asyncio.run(store.get(trace_id))
        assert trace is not None
        names = {e.name for e in trace.timeline}
        assert "state:received" in names
        assert "state:classified" in names
        assert "state:planning" in names
        assert "tool_execution" in names
        assert "state:completed" in names
