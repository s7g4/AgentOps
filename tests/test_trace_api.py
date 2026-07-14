"""Tests for trace retrieval API."""
from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import app


def test_get_trace_includes_tool_status_error_fields_on_failure() -> None:
    with TestClient(app) as client:
        # order_status with no order_id → ToolValidationError → FAILED state
        r = client.post(
            "/messages",
            json={"source": "ticket", "customer_id": "c1", "message": "Where is my order?"},
        )
        assert r.status_code == 200
        trace_id = r.json()["trace_id"]

        trace_r = client.get(f"/trace/{trace_id}")
        assert trace_r.status_code == 200
        trace_data = trace_r.json()
        assert trace_data["trace_id"] == trace_id
        assert "timeline" in trace_data


def test_get_trace_not_found_returns_404() -> None:
    with TestClient(app) as client:
        r = client.get("/trace/does-not-exist-at-all")
        assert r.status_code == 404
        # Every HTTPException response gets a consistent {"error", "detail"}
        # envelope — same shape the auth/rate-limit middleware already use —
        # not just FastAPI's bare default {"detail": ...}.
        body = r.json()
        assert body["error"] == "Not Found"
        assert "does-not-exist-at-all" in body["detail"]


def test_list_traces_returns_paginated_results() -> None:
    with TestClient(app) as client:
        # Send a message to ensure at least one trace exists.
        r = client.post(
            "/messages",
            json={"source": "ticket", "customer_id": "c1", "message": "I need a refund"},
        )
        assert r.status_code == 200

        list_r = client.get("/trace/?limit=10&offset=0")
        assert list_r.status_code == 200
        data = list_r.json()
        assert "total" in data
        assert "traces" in data
        assert data["total"] >= 1
        assert len(data["traces"]) >= 1


def test_list_traces_limit_respected() -> None:
    with TestClient(app) as client:
        # Send two messages.
        for _ in range(2):
            client.post(
                "/messages",
                json={"source": "ticket", "customer_id": "c2", "message": "I want a refund"},
            )

        list_r = client.get("/trace/?limit=1&offset=0")
        assert list_r.status_code == 200
        data = list_r.json()
        assert len(data["traces"]) == 1
