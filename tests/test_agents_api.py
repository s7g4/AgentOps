"""Integration tests for the multi-agent routing API endpoints."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.api.main import create_app
from app.config.settings import Settings, override_settings


@pytest.fixture()
def client() -> TestClient:
    override_settings(Settings())
    app = create_app()
    with TestClient(app) as c:
        yield c


# ── GET /agents ───────────────────────────────────────────────────────────────

def test_list_agents_returns_builtin_agents(client: TestClient) -> None:
    r = client.get("/agents")
    assert r.status_code == 200
    data = r.json()
    assert data["count"] >= 2
    names = [a["name"] for a in data["agents"]]
    assert "echo" in names
    assert "summary" in names


def test_list_agents_response_has_description(client: TestClient) -> None:
    r = client.get("/agents")
    for agent in r.json()["agents"]:
        assert "name" in agent
        assert "description" in agent
        assert len(agent["description"]) > 0


# ── POST /agents/route — success ──────────────────────────────────────────────

def test_route_single_echo_subtask(client: TestClient) -> None:
    r = client.post(
        "/agents/route",
        json={
            "goal": "echo test",
            "subtasks": [{"agent_name": "echo", "payload": {"msg": "hi"}}],
        },
    )
    assert r.status_code == 200
    data = r.json()
    assert data["status"] == "completed"
    assert data["goal"] == "echo test"
    assert len(data["results"]) == 1
    assert data["results"][0]["status"] == "success"
    assert data["results"][0]["output"]["msg"] == "hi"


def test_route_multiple_subtasks_all_succeed(client: TestClient) -> None:
    r = client.post(
        "/agents/route",
        json={
            "goal": "multi agent test",
            "subtasks": [
                {"agent_name": "echo", "payload": {"n": 1}},
                {"agent_name": "summary", "payload": {"k": "v", "x": 2}},
            ],
        },
    )
    assert r.status_code == 200
    data = r.json()
    assert data["status"] == "completed"
    assert len(data["results"]) == 2
    for r_item in data["results"]:
        assert r_item["status"] == "success"


def test_route_response_has_routing_id_and_duration(client: TestClient) -> None:
    r = client.post(
        "/agents/route",
        json={
            "goal": "metadata check",
            "subtasks": [{"agent_name": "echo", "payload": {}}],
        },
    )
    data = r.json()
    assert "routing_id" in data
    assert len(data["routing_id"]) == 36
    assert data["duration_ms"] >= 0


# ── POST /agents/route — partial/failed ───────────────────────────────────────

def test_route_unknown_agent_returns_partial(client: TestClient) -> None:
    r = client.post(
        "/agents/route",
        json={
            "goal": "partial test",
            "subtasks": [
                {"agent_name": "echo", "payload": {}},
                {"agent_name": "ghost_agent", "payload": {}},
            ],
        },
    )
    assert r.status_code == 200
    data = r.json()
    assert data["status"] == "partial"
    by_agent = {res["agent_name"]: res for res in data["results"]}
    assert by_agent["echo"]["status"] == "success"
    assert by_agent["ghost_agent"]["status"] == "error"


def test_route_all_unknown_agents_returns_failed(client: TestClient) -> None:
    r = client.post(
        "/agents/route",
        json={
            "goal": "all fail",
            "subtasks": [
                {"agent_name": "x", "payload": {}},
                {"agent_name": "y", "payload": {}},
            ],
        },
    )
    assert r.status_code == 200
    assert r.json()["status"] == "failed"


# ── POST /agents/route — validation ──────────────────────────────────────────

def test_route_empty_subtasks_returns_422(client: TestClient) -> None:
    r = client.post(
        "/agents/route",
        json={"goal": "no subtasks", "subtasks": []},
    )
    assert r.status_code == 422


def test_route_missing_goal_returns_422(client: TestClient) -> None:
    r = client.post(
        "/agents/route",
        json={"subtasks": [{"agent_name": "echo", "payload": {}}]},
    )
    assert r.status_code == 422


# ── Summary agent content ─────────────────────────────────────────────────────

def test_summary_agent_returns_key_metadata(client: TestClient) -> None:
    r = client.post(
        "/agents/route",
        json={
            "goal": "summarise payload",
            "subtasks": [
                {
                    "agent_name": "summary",
                    "payload": {"order_id": "O1", "amount": 42, "status": "open"},
                }
            ],
        },
    )
    data = r.json()
    output = data["results"][0]["output"]
    assert output["key_count"] == 3
    assert set(output["keys"]) == {"order_id", "amount", "status"}
