import os

import pytest
from fastapi.testclient import TestClient

from server.app import app
from server.extensions import EXTENSION_API_VERSION
from server.middleware.rate_limit import get_current_rate_limit_middleware
from server.settings import (
    ENABLE_BUILTIN_EXTENSIONS_ENV,
    EXTENSION_MODULES_ENV,
    LEASE_SECONDS_ENV,
    RATE_LIMIT_REQUESTS_ENV,
    RATE_LIMIT_TRUSTED_ENV,
    RATE_LIMIT_TRUSTED_PROXIES_ENV,
    RATE_LIMIT_WINDOW_ENV,
    get_extension_settings,
    get_settings_bundle,
    reload_extension_settings,
    reload_lease_settings,
    reload_rate_limit_settings,
    reload_settings_bundle,
)

HTTP_OK = 200
DEFAULT_REQUESTS = 120
DEFAULT_WINDOW_SECONDS = 60
DEFAULT_LEASE_SECONDS = 300


@pytest.fixture(autouse=True)
def reset_settings():
    """Ensure caches are cleared between tests."""

    reload_rate_limit_settings()
    reload_lease_settings()
    reload_extension_settings()
    reload_settings_bundle()
    yield
    for name in (
        LEASE_SECONDS_ENV,
        RATE_LIMIT_REQUESTS_ENV,
        RATE_LIMIT_WINDOW_ENV,
        RATE_LIMIT_TRUSTED_ENV,
        RATE_LIMIT_TRUSTED_PROXIES_ENV,
        EXTENSION_MODULES_ENV,
        ENABLE_BUILTIN_EXTENSIONS_ENV,
    ):
        os.environ.pop(name, None)
    reload_lease_settings()
    reload_rate_limit_settings()
    reload_extension_settings()
    reload_settings_bundle()


def _request_settings():
    middleware = get_current_rate_limit_middleware()
    if middleware is not None:
        middleware.reset()
    with TestClient(app) as client:
        response = client.get("/api/settings")
    assert response.status_code == HTTP_OK
    return response.json()


def test_settings_endpoint_returns_defaults():
    payload = _request_settings()
    rate = payload["rate_limit"]
    lease = payload["lease"]
    extensions = payload["extensions"]
    bundle = get_settings_bundle()
    registered = extensions["registered"]

    assert rate["requests"] == bundle.rate_limit.requests == DEFAULT_REQUESTS
    assert (
        rate["window_seconds"]
        == bundle.rate_limit.window_seconds
        == DEFAULT_WINDOW_SECONDS
    )
    assert rate["trusted_bypass"] == []
    assert rate["trusted_proxies"] == []
    assert rate["enabled"] is True
    assert (
        lease["duration_seconds"]
        == bundle.lease.duration_seconds
        == DEFAULT_LEASE_SECONDS
    )
    assert extensions["modules"] == list(bundle.extensions.modules)
    assert extensions["builtin_enabled"] is bundle.extensions.enable_builtin
    assert any(
        descriptor["name"] == "builtin.task_metrics" for descriptor in registered
    )
    assert extensions["contract_version"] == EXTENSION_API_VERSION
    assert all(isinstance(note, str) for note in extensions["contract_notes"])


def test_settings_endpoint_reflects_overrides(monkeypatch):
    monkeypatch.setenv(RATE_LIMIT_REQUESTS_ENV, "10")
    monkeypatch.setenv(RATE_LIMIT_WINDOW_ENV, "5")
    monkeypatch.setenv(RATE_LIMIT_TRUSTED_ENV, "10.0.0.1, 10.0.0.2")
    monkeypatch.setenv(RATE_LIMIT_TRUSTED_PROXIES_ENV, "192.168.0.1")
    monkeypatch.setenv(LEASE_SECONDS_ENV, "45")
    monkeypatch.setenv(EXTENSION_MODULES_ENV, "custom.module, custom.module")
    monkeypatch.setenv(ENABLE_BUILTIN_EXTENSIONS_ENV, "0")
    reload_rate_limit_settings()
    reload_lease_settings()
    reload_extension_settings()

    payload = _request_settings()
    rate = payload["rate_limit"]
    lease = payload["lease"]
    extensions = payload["extensions"]

    assert rate == {
        "requests": 10,
        "window_seconds": 5,
        "trusted_bypass": ["10.0.0.1", "10.0.0.2"],
        "trusted_proxies": ["192.168.0.1"],
        "enabled": True,
    }
    assert lease == {"duration_seconds": 45}
    assert extensions["modules"] == ["custom.module"]
    assert extensions["builtin_enabled"] is False
    assert extensions["registered"] == []
    assert extensions["contract_version"] == EXTENSION_API_VERSION
    assert extensions["contract_notes"] == []


def test_extension_settings_bundle_matches_runtime(monkeypatch):
    monkeypatch.setenv(EXTENSION_MODULES_ENV, "alpha.plugin, beta.plugin")
    monkeypatch.setenv(ENABLE_BUILTIN_EXTENSIONS_ENV, "true")
    reload_extension_settings()
    bundle = get_extension_settings()
    payload = _request_settings()["extensions"]
    assert payload["modules"] == list(bundle.modules)
    assert payload["builtin_enabled"] is bundle.enable_builtin
