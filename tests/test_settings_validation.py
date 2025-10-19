"""Unit tests for stricter rate limit configuration parsing."""

import pytest

from server.settings import (
    RATE_LIMIT_REQUESTS_ENV,
    RATE_LIMIT_WINDOW_ENV,
    RateLimitConfigurationError,
    get_rate_limit_settings,
    reload_rate_limit_settings,
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
