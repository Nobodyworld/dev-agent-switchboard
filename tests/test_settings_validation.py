"""Unit tests for stricter rate limit configuration parsing."""

import pytest

from server.settings import (
    ENABLE_BUILTIN_EXTENSIONS_ENV,
    EXECUTION_ACTIVE_POLL_FRESHNESS_SECONDS_ENV,
    EXECUTION_HEARTBEAT_FRESHNESS_SECONDS_ENV,
    EXTENSION_MODULES_ENV,
    LEASE_SECONDS_ENV,
    MAX_LIVE_FILE_BYTES_ENV,
    RATE_LIMIT_REQUESTS_ENV,
    RATE_LIMIT_WINDOW_ENV,
    ExecutionRoutingConfigurationError,
    ExtensionConfigurationError,
    FileUploadConfigurationError,
    LeaseConfigurationError,
    RateLimitConfigurationError,
    get_execution_routing_settings,
    get_lease_settings,
    get_max_live_file_bytes,
    get_rate_limit_settings,
    get_settings_bundle,
    reload_execution_routing_settings,
    reload_extension_settings,
    reload_lease_settings,
    reload_max_live_file_bytes,
    reload_rate_limit_settings,
    reload_settings_bundle,
)


def test_invalid_requests_env_raises(monkeypatch):
    monkeypatch.setenv(RATE_LIMIT_REQUESTS_ENV, "not-an-int")
    with pytest.raises(RateLimitConfigurationError):
        reload_rate_limit_settings()
    monkeypatch.delenv(RATE_LIMIT_REQUESTS_ENV, raising=False)
    reload_rate_limit_settings()


def test_negative_window_env_raises(monkeypatch):
    monkeypatch.setenv(RATE_LIMIT_WINDOW_ENV, "-1")
    with pytest.raises(RateLimitConfigurationError):
        reload_rate_limit_settings()
    monkeypatch.delenv(RATE_LIMIT_WINDOW_ENV, raising=False)
    reload_rate_limit_settings()


def test_zero_requests_disables_rate_limit(monkeypatch):
    monkeypatch.setenv(RATE_LIMIT_REQUESTS_ENV, "0")
    monkeypatch.setenv(RATE_LIMIT_WINDOW_ENV, "10")
    settings = reload_rate_limit_settings()
    assert settings.requests == 0
    assert settings.enabled is False
    # Subsequent calls should reuse the cached, valid configuration.
    cached = get_rate_limit_settings()
    assert cached.requests == 0
    monkeypatch.delenv(RATE_LIMIT_REQUESTS_ENV, raising=False)
    monkeypatch.delenv(RATE_LIMIT_WINDOW_ENV, raising=False)
    restored = reload_rate_limit_settings()
    assert restored.requests > 0


def test_invalid_lease_env_raises(monkeypatch):
    monkeypatch.setenv(LEASE_SECONDS_ENV, "oops")
    with pytest.raises(LeaseConfigurationError):
        reload_lease_settings()
    monkeypatch.delenv(LEASE_SECONDS_ENV, raising=False)
    reload_lease_settings()


def test_zero_lease_env_raises(monkeypatch):
    monkeypatch.setenv(LEASE_SECONDS_ENV, "0")
    with pytest.raises(LeaseConfigurationError, match="positive integer"):
        reload_lease_settings()
    monkeypatch.delenv(LEASE_SECONDS_ENV, raising=False)
    reload_lease_settings()


def test_positive_lease_env_updates_setting(monkeypatch):
    monkeypatch.setenv(LEASE_SECONDS_ENV, "900")
    settings = reload_lease_settings()
    assert settings.duration_seconds == 900
    cached = get_lease_settings()
    assert cached.duration_seconds == 900
    monkeypatch.delenv(LEASE_SECONDS_ENV, raising=False)
    restored = reload_lease_settings()
    assert restored.duration_seconds == get_lease_settings().duration_seconds


@pytest.mark.parametrize(
    ("name", "value"),
    [
        (EXECUTION_HEARTBEAT_FRESHNESS_SECONDS_ENV, "0"),
        (EXECUTION_HEARTBEAT_FRESHNESS_SECONDS_ENV, "86401"),
        (EXECUTION_ACTIVE_POLL_FRESHNESS_SECONDS_ENV, "0"),
        (EXECUTION_ACTIVE_POLL_FRESHNESS_SECONDS_ENV, "3601"),
        (EXECUTION_ACTIVE_POLL_FRESHNESS_SECONDS_ENV, "not-an-int"),
    ],
)
def test_execution_routing_freshness_is_positive_and_bounded(
    monkeypatch, name: str, value: str
) -> None:
    monkeypatch.setenv(name, value)
    with pytest.raises(ExecutionRoutingConfigurationError):
        reload_execution_routing_settings()
    monkeypatch.delenv(name, raising=False)
    reload_execution_routing_settings()


def test_execution_routing_freshness_overrides_are_cached(monkeypatch) -> None:
    monkeypatch.setenv(EXECUTION_HEARTBEAT_FRESHNESS_SECONDS_ENV, "720")
    monkeypatch.setenv(EXECUTION_ACTIVE_POLL_FRESHNESS_SECONDS_ENV, "45")
    settings = reload_execution_routing_settings()
    assert settings.heartbeat_freshness_seconds == 720
    assert settings.active_poll_freshness_seconds == 45
    assert get_execution_routing_settings() == settings
    monkeypatch.delenv(EXECUTION_HEARTBEAT_FRESHNESS_SECONDS_ENV, raising=False)
    monkeypatch.delenv(EXECUTION_ACTIVE_POLL_FRESHNESS_SECONDS_ENV, raising=False)
    reload_execution_routing_settings()


def test_live_file_limit_requires_positive_integer(monkeypatch):
    monkeypatch.setenv(MAX_LIVE_FILE_BYTES_ENV, "0")
    with pytest.raises(FileUploadConfigurationError, match="positive integer"):
        reload_max_live_file_bytes()
    monkeypatch.setenv(MAX_LIVE_FILE_BYTES_ENV, "4096")
    assert reload_max_live_file_bytes() == 4096
    assert get_max_live_file_bytes() == 4096
    monkeypatch.delenv(MAX_LIVE_FILE_BYTES_ENV, raising=False)
    reload_max_live_file_bytes()


def test_settings_bundle_tracks_current_configuration(monkeypatch):
    bundle = reload_settings_bundle()
    assert bundle.rate_limit == get_rate_limit_settings()
    assert bundle.lease == get_lease_settings()

    monkeypatch.setenv(RATE_LIMIT_REQUESTS_ENV, "200")
    monkeypatch.setenv(LEASE_SECONDS_ENV, "180")
    reload_rate_limit_settings()
    reload_lease_settings()

    updated_bundle = get_settings_bundle()
    assert updated_bundle.rate_limit.requests == 200
    assert updated_bundle.lease.duration_seconds == 180

    monkeypatch.delenv(RATE_LIMIT_REQUESTS_ENV, raising=False)
    monkeypatch.delenv(LEASE_SECONDS_ENV, raising=False)
    reload_rate_limit_settings()
    reload_lease_settings()
    reload_settings_bundle()


def test_lease_duration_helper_reflects_configuration(monkeypatch):
    monkeypatch.setenv(LEASE_SECONDS_ENV, "120")
    reload_lease_settings()
    try:
        assert get_lease_settings().duration_seconds == 120
    finally:
        monkeypatch.delenv(LEASE_SECONDS_ENV, raising=False)
        reload_lease_settings()


def test_extension_list_requires_valid_module_paths(monkeypatch):
    monkeypatch.setenv(EXTENSION_MODULES_ENV, "valid.module, invalid module")
    with pytest.raises(ExtensionConfigurationError):
        reload_extension_settings()
    monkeypatch.setenv(EXTENSION_MODULES_ENV, "extensions.custom,extensions.custom")
    settings = reload_extension_settings()
    assert settings.modules == ("extensions.custom",)
    monkeypatch.delenv(EXTENSION_MODULES_ENV, raising=False)
    reload_extension_settings()


def test_builtin_toggle_respects_truthy_values(monkeypatch):
    monkeypatch.setenv(ENABLE_BUILTIN_EXTENSIONS_ENV, "off")
    settings = reload_extension_settings()
    assert settings.enable_builtin is False
    monkeypatch.setenv(ENABLE_BUILTIN_EXTENSIONS_ENV, "TRUE")
    settings = reload_extension_settings()
    assert settings.enable_builtin is True
    monkeypatch.delenv(ENABLE_BUILTIN_EXTENSIONS_ENV, raising=False)
    reload_extension_settings()
