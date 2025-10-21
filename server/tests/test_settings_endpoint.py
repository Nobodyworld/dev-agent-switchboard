import os

import pytest
from fastapi.testclient import TestClient

from server.app import app
from server.settings import (
    LEASE_SECONDS_ENV,
    RATE_LIMIT_REQUESTS_ENV,
    RATE_LIMIT_TRUSTED_ENV,
    RATE_LIMIT_TRUSTED_PROXIES_ENV,
    RATE_LIMIT_WINDOW_ENV,
    get_settings_bundle,
    reload_lease_settings,
    reload_rate_limit_settings,
    reload_settings_bundle,
)


@pytest.fixture(autouse=True)
def reset_settings():
    """Ensure caches are cleared between tests."""

    yield
    for name in (
        LEASE_SECONDS_ENV,
        RATE_LIMIT_REQUESTS_ENV,
        RATE_LIMIT_WINDOW_ENV,
        RATE_LIMIT_TRUSTED_ENV,
        RATE_LIMIT_TRUSTED_PROXIES_ENV,
    ):
        os.environ.pop(name, None)
    reload_lease_settings()
    reload_rate_limit_settings()
    reload_settings_bundle()


def _request_settings():
    with TestClient(app) as client:
        response = client.get("/api/settings")
    assert response.status_code == 200
    return response.json()


def test_settings_endpoint_returns_defaults():
    payload = _request_settings()
    rate = payload["rate_limit"]
    lease = payload["lease"]
    bundle = get_settings_bundle()

    assert rate["requests"] == bundle.rate_limit.requests == 120
    assert (
        rate["window_seconds"]
        == bundle.rate_limit.window_seconds
        == 60
    )
    assert rate["trusted_bypass"] == []
    assert rate["trusted_proxies"] == []
    assert rate["enabled"] is True
    assert (
        lease["duration_seconds"]
        == bundle.lease.duration_seconds
        == 300
    )


def test_settings_endpoint_reflects_overrides(monkeypatch):
    monkeypatch.setenv(RATE_LIMIT_REQUESTS_ENV, "10")
    monkeypatch.setenv(RATE_LIMIT_WINDOW_ENV, "5")
    monkeypatch.setenv(RATE_LIMIT_TRUSTED_ENV, "10.0.0.1, 10.0.0.2")
    monkeypatch.setenv(RATE_LIMIT_TRUSTED_PROXIES_ENV, "192.168.0.1")
    monkeypatch.setenv(LEASE_SECONDS_ENV, "45")
    reload_rate_limit_settings()
    reload_lease_settings()

    payload = _request_settings()
    rate = payload["rate_limit"]
    lease = payload["lease"]

    assert rate == {
        "requests": 10,
        "window_seconds": 5,
        "trusted_bypass": ["10.0.0.1", "10.0.0.2"],
        "trusted_proxies": ["192.168.0.1"],
        "enabled": True,
    }
    assert lease == {"duration_seconds": 45}
