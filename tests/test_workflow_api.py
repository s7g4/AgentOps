"""Integration tests for the Workflow API endpoints via TestClient."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.api.main import create_app
from app.config.settings import Settings, override_settings

_VALID_WORKFLOW = {
    "name": "Refund flow",
    "description": "Check refund policy",
    "steps": [
        {"id": "step1", "tool_name": "refund_policy", "static_input": {}, "depends_on": []},
    ],
}

_TWO_STEP_WORKFLOW = {
    "name": "Order then refund",
    "steps": [
        {"id": "order", "tool_name": "check_order_status", "static_input": {"order_id": "X1"}},
        {"id": "refund", "tool_name": "refund_policy", "depends_on": ["order"]},
    ],
}


@pytest.fixture()
def client() -> TestClient:
    override_settings(Settings())
    app = create_app()
    with TestClient(app) as c:
        yield c


# ── Create ────────────────────────────────────────────────────────────────────

def test_create_workflow_returns_201(client: TestClient) -> None:
    r = client.post("/workflows", json=_VALID_WORKFLOW)
    assert r.status_code == 201
    data = r.json()
    assert data["name"] == "Refund flow"
    assert "id" in data
    assert len(data["steps"]) == 1


def test_create_workflow_with_cycle_returns_422(client: TestClient) -> None:
    cyclic = {
        "name": "cyclic",
        "steps": [
            {"id": "a", "depends_on": ["b"]},
            {"id": "b", "depends_on": ["a"]},
        ],
    }
    # Steps missing tool_name — Pydantic will 422 first on validation,
    # which is correct: bad input is rejected before cycle check.
    r = client.post("/workflows", json=cyclic)
    assert r.status_code == 422


def test_create_workflow_with_dag_cycle_returns_422(client: TestClient) -> None:
    cyclic = {
        "name": "cyclic",
        "steps": [
            {"id": "a", "tool_name": "refund_policy", "depends_on": ["b"]},
            {"id": "b", "tool_name": "refund_policy", "depends_on": ["a"]},
        ],
    }
    r = client.post("/workflows", json=cyclic)
    assert r.status_code == 422
    assert "cycle" in r.json()["detail"].lower()


# ── Get ───────────────────────────────────────────────────────────────────────

def test_get_workflow_returns_definition(client: TestClient) -> None:
    wf_id = client.post("/workflows", json=_VALID_WORKFLOW).json()["id"]
    r = client.get(f"/workflows/{wf_id}")
    assert r.status_code == 200
    assert r.json()["id"] == wf_id


def test_get_nonexistent_workflow_returns_404(client: TestClient) -> None:
    r = client.get("/workflows/does-not-exist")
    assert r.status_code == 404


# ── List ──────────────────────────────────────────────────────────────────────

def test_list_workflows_returns_created(client: TestClient) -> None:
    client.post("/workflows", json=_VALID_WORKFLOW)
    client.post("/workflows", json=_VALID_WORKFLOW)
    r = client.get("/workflows?limit=10&offset=0")
    assert r.status_code == 200
    data = r.json()
    assert data["total"] >= 2
    assert len(data["workflows"]) >= 2


# ── Delete ────────────────────────────────────────────────────────────────────

def test_delete_workflow_returns_204(client: TestClient) -> None:
    wf_id = client.post("/workflows", json=_VALID_WORKFLOW).json()["id"]
    r = client.delete(f"/workflows/{wf_id}")
    assert r.status_code == 204
    assert client.get(f"/workflows/{wf_id}").status_code == 404


def test_delete_nonexistent_workflow_returns_404(client: TestClient) -> None:
    r = client.delete("/workflows/ghost-id")
    assert r.status_code == 404


# ── Run ───────────────────────────────────────────────────────────────────────

def test_run_workflow_returns_completed_execution(client: TestClient) -> None:
    wf_id = client.post("/workflows", json=_VALID_WORKFLOW).json()["id"]
    r = client.post(f"/workflows/{wf_id}/run", json={"context": {}})
    assert r.status_code == 200
    data = r.json()
    assert data["status"] == "completed"
    assert "step1" in data["step_results"]
    assert data["step_results"]["step1"]["status"] == "success"


def test_run_two_step_workflow_succeeds(client: TestClient) -> None:
    wf_id = client.post("/workflows", json=_TWO_STEP_WORKFLOW).json()["id"]
    r = client.post(f"/workflows/{wf_id}/run", json={"context": {}})
    assert r.status_code == 200
    data = r.json()
    assert data["status"] == "completed"
    assert data["step_results"]["order"]["status"] == "success"
    assert data["step_results"]["refund"]["status"] == "success"


def test_run_workflow_with_context_override(client: TestClient) -> None:
    wf = {
        "name": "order_flow",
        "steps": [{"id": "s", "tool_name": "check_order_status"}],
    }
    wf_id = client.post("/workflows", json=wf).json()["id"]
    r = client.post(f"/workflows/{wf_id}/run", json={"context": {"order_id": "ORD-42"}})
    assert r.status_code == 200
    assert r.json()["status"] == "completed"


def test_run_nonexistent_workflow_returns_404(client: TestClient) -> None:
    r = client.post("/workflows/ghost-id/run", json={"context": {}})
    assert r.status_code == 404


# ── Runs (execution history) ──────────────────────────────────────────────────

def test_list_runs_returns_executions(client: TestClient) -> None:
    wf_id = client.post("/workflows", json=_VALID_WORKFLOW).json()["id"]
    client.post(f"/workflows/{wf_id}/run", json={"context": {}})
    client.post(f"/workflows/{wf_id}/run", json={"context": {}})

    r = client.get(f"/workflows/{wf_id}/runs")
    assert r.status_code == 200
    data = r.json()
    assert data["total"] >= 2


def test_get_run_by_id(client: TestClient) -> None:
    wf_id = client.post("/workflows", json=_VALID_WORKFLOW).json()["id"]
    exec_id = client.post(f"/workflows/{wf_id}/run", json={"context": {}}).json()["execution_id"]

    r = client.get(f"/workflows/{wf_id}/runs/{exec_id}")
    assert r.status_code == 200
    assert r.json()["execution_id"] == exec_id
    assert r.json()["status"] == "completed"


def test_get_run_wrong_workflow_returns_404(client: TestClient) -> None:
    wf_id = client.post("/workflows", json=_VALID_WORKFLOW).json()["id"]
    exec_id = client.post(f"/workflows/{wf_id}/run", json={"context": {}}).json()["execution_id"]

    r = client.get(f"/workflows/other-wf-id/runs/{exec_id}")
    assert r.status_code == 404
