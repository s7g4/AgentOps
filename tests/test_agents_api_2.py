"""Integration tests for the agents routing API history and decomposition endpoints."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.api.main import create_app
from app.config.settings import Settings, override_settings


@pytest.fixture()
def client() -> TestClient:
    override_settings(Settings(redis_url=None))
    app = create_app()
    with TestClient(app) as c:
        yield c


# ── POST /agents/route (Auto-decomposition) ──────────────────────────────────

def test_route_auto_decomposition_echo(client: TestClient) -> None:
    r = client.post(
        "/agents/route",
        json={"goal": "please echo this support request"},
    )
    assert r.status_code == 200
    data = r.json()
    assert data["status"] == "completed"
    assert len(data["results"]) == 1
    assert data["results"][0]["agent_name"] == "echo"


def test_route_auto_decomposition_summary(client: TestClient) -> None:
    r = client.post(
        "/agents/route",
        json={"goal": "please summarize this support request"},
    )
    assert r.status_code == 200
    data = r.json()
    assert data["status"] == "completed"
    assert len(data["results"]) == 1
    assert data["results"][0]["agent_name"] == "summary"


# ── GET /agents/routes (History) ─────────────────────────────────────────────

def test_list_routes_history(client: TestClient) -> None:
    # Trigger two routing runs
    client.post("/agents/route", json={"goal": "echo test"})
    client.post("/agents/route", json={"goal": "summarize test"})

    r = client.get("/agents/routes?limit=10&offset=0")
    assert r.status_code == 200
    data = r.json()
    assert data["total"] >= 2
    assert len(data["routes"]) >= 2
    assert data["routes"][0]["goal"] == "summarize test"
    assert data["routes"][1]["goal"] == "echo test"


def test_get_routing_run_by_id(client: TestClient) -> None:
    res = client.post("/agents/route", json={"goal": "unique test run"})
    routing_id = res.json()["routing_id"]

    r = client.get(f"/agents/routes/{routing_id}")
    assert r.status_code == 200
    data = r.json()
    assert data["routing_id"] == routing_id
    assert data["goal"] == "unique test run"


def test_get_nonexistent_routing_run(client: TestClient) -> None:
    r = client.get("/agents/routes/ghost-id")
    assert r.status_code == 404
