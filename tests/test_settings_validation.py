"""Unit tests for stricter rate limit configuration parsing."""

import pytest

from server.settings import (
    LEASE_SECONDS_ENV,
    RATE_LIMIT_REQUESTS_ENV,
    RATE_LIMIT_WINDOW_ENV,
    LeaseConfigurationError,
    RateLimitConfigurationError,
    get_lease_settings,
    get_rate_limit_settings,
    get_settings_bundle,
    reload_lease_settings,
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
