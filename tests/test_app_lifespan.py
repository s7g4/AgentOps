"""Tests for app startup/shutdown wiring in app/api/main.py.

Regression coverage for a gap found in review: routing_store is created via
the same get_routing_store() the supervisor uses internally, but was never
bound to app.state nor included in the shutdown-close loop, so its backing
resource (a Redis connection, when TRACE_BACKEND=redis) was never closed on
shutdown.

get_routing_store (like every other DI getter in app/api/deps.py) is
lru_cache'd process-wide with no invalidation hook, and almost every other
test in this suite calls create_app() under the default memory-backend
settings — so by the time any single test runs, that cache is likely
already permanently populated with an in-memory instance. Rather than fight
that (real, separate) test-isolation limitation, this test patches the
dependency getter directly to verify main.py's *wiring* — that whatever
get_routing_store() returns gets bound to app.state and closed on
shutdown — independent of which backend deps.py would actually select.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

from app.api.main import create_app


def test_all_singletons_bound_to_app_state() -> None:
    with TestClient(create_app()) as client:
        app = client.app
        for state_key in (
            "runtime",
            "tool_registry",
            "trace_store",
            "workflow_store",
            "workflow_executor",
            "agent_registry",
            "routing_store",
            "supervisor",
            "rate_limiter",
        ):
            assert getattr(app.state, state_key, None) is not None, state_key


def test_routing_store_closed_on_shutdown() -> None:
    fake_store = AsyncMock()

    with patch("app.api.deps.get_routing_store", return_value=fake_store):
        with TestClient(create_app()) as client:
            assert client.app.state.routing_store is fake_store
            fake_store.close.assert_not_called()

        # Lifespan shutdown has now run.
        fake_store.close.assert_awaited_once()
