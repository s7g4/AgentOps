"""Tests for APIKeyMiddleware — multi-key auth, open paths, rejection behavior."""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from app.api.main import create_app
from app.config.settings import Settings, override_settings
from app.exceptions import ConfigurationError


def _restore_default_settings() -> None:
    override_settings(Settings(trace_backend="memory", auth_enabled=False, redis_url=None))


@pytest.fixture()
def auth_client() -> Iterator[TestClient]:
    override_settings(
        Settings(auth_enabled=True, api_keys="key-one,key-two", trace_backend="memory")
    )
    try:
        with TestClient(create_app()) as c:
            yield c
    finally:
        _restore_default_settings()


def test_missing_key_is_rejected(auth_client: TestClient) -> None:
    resp = auth_client.get("/tools")
    assert resp.status_code == 401


def test_wrong_key_is_rejected(auth_client: TestClient) -> None:
    resp = auth_client.get("/tools", headers={"X-Api-Key": "not-a-real-key"})
    assert resp.status_code == 401


def test_first_configured_key_is_accepted(auth_client: TestClient) -> None:
    resp = auth_client.get("/tools", headers={"X-Api-Key": "key-one"})
    assert resp.status_code == 200


def test_second_configured_key_is_accepted(auth_client: TestClient) -> None:
    resp = auth_client.get("/tools", headers={"X-Api-Key": "key-two"})
    assert resp.status_code == 200


def test_open_paths_bypass_auth(auth_client: TestClient) -> None:
    assert auth_client.get("/health").status_code in (200, 503)
    assert auth_client.get("/metrics").status_code == 200


def test_docs_and_openapi_require_auth(auth_client: TestClient) -> None:
    """Regression test: the API schema shouldn't be handed out for free to
    an unauthenticated caller once auth is enabled."""
    assert auth_client.get("/docs").status_code == 401
    assert auth_client.get("/openapi.json").status_code == 401
    assert auth_client.get("/docs", headers={"X-Api-Key": "key-one"}).status_code == 200


def test_legacy_single_api_key_still_works() -> None:
    override_settings(Settings(auth_enabled=True, api_key="legacy-secret", trace_backend="memory"))
    try:
        with TestClient(create_app()) as c:
            assert c.get("/tools", headers={"X-Api-Key": "legacy-secret"}).status_code == 200
            assert c.get("/tools", headers={"X-Api-Key": "wrong"}).status_code == 401
    finally:
        _restore_default_settings()


def test_auth_enabled_without_any_key_configured_raises() -> None:
    override_settings(Settings(auth_enabled=True, trace_backend="memory"))
    try:
        with (
            TestClient(create_app(), raise_server_exceptions=True) as c,
            pytest.raises(ConfigurationError),
        ):
            c.get("/tools")
    finally:
        _restore_default_settings()


def test_disabled_auth_allows_any_request() -> None:
    """Sanity check: with AUTH_ENABLED=false (the default), no key is required."""
    override_settings(Settings(auth_enabled=False, trace_backend="memory"))
    try:
        with TestClient(create_app()) as c:
            assert c.get("/tools").status_code == 200
    finally:
        _restore_default_settings()
