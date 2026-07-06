"""Points the client at the real AgentOps ASGI app with no network involved."""

from __future__ import annotations

import sys
from pathlib import Path

# The server package (app/) lives in the parent repo, not inside client/.
# Tests run against it directly via ASGITransport rather than a live server.
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import httpx
import pytest
from app.api.main import create_app
from app.config.settings import Settings, override_settings

from agentops_client.client import AgentOpsClient, AsyncAgentOpsClient


@pytest.fixture()
def _clean_settings() -> None:
    override_settings(Settings(trace_backend="memory", auth_enabled=False, redis_url=None))


@pytest.fixture()
async def transport(_clean_settings: None) -> httpx.ASGITransport:
    # httpx.ASGITransport does not send lifespan events on its own, but
    # /tools, /trace, and /health read singletons off app.state that are
    # only populated by the app's lifespan handler — so it must be driven
    # explicitly here, the same way TestClient does internally.
    app = create_app()
    async with app.router.lifespan_context(app):
        yield httpx.ASGITransport(app=app)


@pytest.fixture()
async def async_client(transport: httpx.ASGITransport) -> AsyncAgentOpsClient:
    client = AsyncAgentOpsClient(base_url="http://testserver", transport=transport)
    yield client
    await client.aclose()


@pytest.fixture()
def sync_client(transport: httpx.ASGITransport) -> AgentOpsClient:
    return AgentOpsClient(base_url="http://testserver", transport=transport)
