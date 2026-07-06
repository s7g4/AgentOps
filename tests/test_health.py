"""Tests for GET /health — dependency checks and status derivation."""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from conftest import REDIS_TEST_URL
from fastapi.testclient import TestClient

from app.api.main import create_app
from app.config.settings import Settings, override_settings


def _restore_default_settings() -> None:
    override_settings(Settings(trace_backend="memory", auth_enabled=False, redis_url=None))


def test_health_with_no_redis_configured() -> None:
    with TestClient(create_app()) as client:
        resp = client.get("/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["checks"]["redis"] == "not_configured"
    assert body["checks"]["openai"] == "not_configured"


def test_health_reports_openai_configured() -> None:
    override_settings(Settings(trace_backend="memory", openai_api_key="sk-test"))
    try:
        with TestClient(create_app()) as client:
            resp = client.get("/health")
        assert resp.json()["checks"]["openai"] == "configured"
    finally:
        _restore_default_settings()


def test_health_reports_redis_error_on_unreachable_url() -> None:
    override_settings(Settings(trace_backend="memory", redis_url="redis://localhost:1/0"))
    try:
        with TestClient(create_app()) as client:
            resp = client.get("/health")
        body = resp.json()
        assert body["checks"]["redis"] == "error"
        assert body["status"] == "degraded"
    finally:
        _restore_default_settings()


@pytest.fixture()
def _reachable_redis_settings(redis_client) -> Iterator[None]:  # noqa: ANN001
    override_settings(Settings(trace_backend="memory", redis_url=REDIS_TEST_URL))
    yield
    _restore_default_settings()


def test_health_reports_redis_ok_when_reachable(_reachable_redis_settings: None) -> None:
    with TestClient(create_app()) as client:
        resp = client.get("/health")
    body = resp.json()
    assert body["checks"]["redis"] == "ok"
    assert body["status"] == "ok"
