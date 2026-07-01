from app.config.settings import Settings, override_settings


def test_settings_load_runtime_host_and_port_from_env(monkeypatch):
    """Settings constructed directly reflect environment overrides."""
    monkeypatch.setenv("HOST", "0.0.0.0")
    monkeypatch.setenv("PORT", "9000")
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")

    # Bypass the singleton so env changes take effect.
    settings = Settings()
    override_settings(settings)

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
