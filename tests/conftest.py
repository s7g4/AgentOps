"""Shared test fixtures for AgentOps test suite."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.config.settings import Settings, override_settings
from app.main import app
from app.registry.tool_registry import ToolRegistry
from app.runtime.runtime import AgentOpsRuntime
from app.runtime.trace_store import TraceStore


@pytest.fixture(scope="session", autouse=True)
def isolated_settings() -> None:
    """Override settings with test-safe defaults for the whole session."""
    override_settings(Settings(trace_backend="memory", auth_enabled=False))


@pytest.fixture()
def client() -> TestClient:
    with TestClient(app) as c:
        yield c


@pytest.fixture()
def runtime() -> AgentOpsRuntime:
    return AgentOpsRuntime.default()


@pytest.fixture()
def trace_store() -> TraceStore:
    return TraceStore.default()


@pytest.fixture()
def tool_registry() -> ToolRegistry:
    return ToolRegistry.default()
