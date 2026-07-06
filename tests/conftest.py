"""Shared test fixtures for AgentOps test suite."""
from __future__ import annotations

import os

import pytest
from fastapi.testclient import TestClient

from app.config.settings import Settings, override_settings
from app.main import app
from app.registry.tool_registry import ToolRegistry
from app.runtime.runtime import AgentOpsRuntime
from app.runtime.trace_store import TraceStore

# CI sets REDIS_URL to a real service container (see .github/workflows/ci.yml).
# Locally, tests that need Redis are skipped rather than failed so `pytest`
# works without Docker running — the Redis-backed classes still get full
# coverage in CI, which is where persistence bugs actually matter.
REDIS_TEST_URL = os.environ.get("REDIS_URL", "redis://localhost:6379/0")


@pytest.fixture(scope="session", autouse=True)
def isolated_settings() -> None:
    """Override settings with test-safe defaults for the whole session.

    redis_url is forced to None even though pydantic-settings would
    otherwise pick up REDIS_URL from the environment (CI sets it for the
    Redis-backed persistence tests) — most tests want the pre-Redis
    default behavior and shouldn't be coupled to whether that env var
    happens to be set.
    """
    override_settings(Settings(trace_backend="memory", auth_enabled=False, redis_url=None))


@pytest.fixture()
async def redis_client():  # type: ignore[no-untyped-def]
    """A real redis.asyncio client, skipping the test if none is reachable."""
    redis = pytest.importorskip("redis.asyncio")
    client = redis.from_url(REDIS_TEST_URL, decode_responses=True)
    try:
        await client.ping()
    except Exception:  # noqa: BLE001
        pytest.skip(f"No Redis reachable at {REDIS_TEST_URL}")
    # Keep the test database isolated from anything else using this Redis.
    await client.flushdb()
    yield client
    await client.flushdb()
    await client.aclose()


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
