from app.config.settings import Settings


def test_settings_load_runtime_host_and_port_from_env(monkeypatch):
    """Settings constructed directly reflect environment overrides.

    Asserts against a standalone Settings() instance rather than the global
    singleton — this test only cares that env vars are read correctly, not
    that they take effect app-wide, so it has no business mutating shared
    state other tests depend on.
    """
    monkeypatch.setenv("HOST", "0.0.0.0")
    monkeypatch.setenv("PORT", "9000")
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")

    settings = Settings()

    assert settings.host == "0.0.0.0"
    assert settings.port == 9000
    assert settings.openai_api_key == "test-key"


def test_settings_defaults() -> None:
    """Default settings have sensible values."""
    settings = Settings()
    assert settings.app_name == "AgentOps"
    assert settings.port == 8000
    assert settings.log_level == "INFO"
    assert settings.trace_backend == "memory"
    assert settings.auth_enabled is False


def test_settings_log_level_validation() -> None:
    """Settings accept all valid log levels."""
    for level in ("DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"):
        s = Settings(log_level=level)
        assert s.log_level == level


def test_valid_api_keys_merges_legacy_and_list() -> None:
    s = Settings(api_key="legacy", api_keys="a,b, c ,")
    assert s.valid_api_keys() == frozenset({"legacy", "a", "b", "c"})


def test_valid_api_keys_empty_when_unconfigured() -> None:
    s = Settings()
    assert s.valid_api_keys() == frozenset()


def test_valid_api_keys_ignores_blank_entries() -> None:
    s = Settings(api_keys=",, ,")
    assert s.valid_api_keys() == frozenset()
