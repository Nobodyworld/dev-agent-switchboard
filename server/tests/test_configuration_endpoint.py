from __future__ import annotations

import os
import shutil
from collections.abc import Iterable

import pytest
from fastapi.testclient import TestClient

from server.app import app
from server.application.configuration_service import ConfigurationService
from server.settings import (
    ADMIN_TOKEN_ENV,
    ENABLE_BUILTIN_EXTENSIONS_ENV,
    EXTENSION_MODULES_ENV,
    LEASE_SECONDS_ENV,
    RATE_LIMIT_REQUESTS_ENV,
    RATE_LIMIT_TRUSTED_ENV,
    RATE_LIMIT_TRUSTED_PROXIES_ENV,
    RATE_LIMIT_WINDOW_ENV,
    reload_admin_token,
    reload_extension_settings,
    reload_lease_settings,
    reload_rate_limit_settings,
    reload_settings_bundle,
)

HTTP_OK = 200


@pytest.fixture(autouse=True)
def reset_settings() -> Iterable[None]:
    """Ensure configuration caches are cleared between tests."""

    reload_rate_limit_settings()
    reload_lease_settings()
    reload_extension_settings()
    reload_settings_bundle()
    reload_admin_token()
    yield
    for name in (
        RATE_LIMIT_REQUESTS_ENV,
        RATE_LIMIT_WINDOW_ENV,
        RATE_LIMIT_TRUSTED_ENV,
        RATE_LIMIT_TRUSTED_PROXIES_ENV,
        LEASE_SECONDS_ENV,
        EXTENSION_MODULES_ENV,
        ENABLE_BUILTIN_EXTENSIONS_ENV,
        ADMIN_TOKEN_ENV,
    ):
        os.environ.pop(name, None)
    reload_rate_limit_settings()
    reload_lease_settings()
    reload_extension_settings()
    reload_settings_bundle()
    reload_admin_token()


def _request_configuration() -> dict[str, object]:
    with TestClient(app) as client:
        response = client.get("/api/configuration")
    assert response.status_code == HTTP_OK
    return response.json()


def test_configuration_endpoint_returns_snapshot(files_root):
    payload = _request_configuration()

    assert "settings" in payload
    assert payload["admin"] == {"configured": False}

    storage = payload["storage"]
    assert storage["root"] == str(files_root)
    assert storage["exists"] in {True, False}
    assert storage["writable"] in {True, False}

    database = payload["database"]
    assert "url" in database
    assert "engine_options" in database

    runtime = payload["runtime"]
    assert "started_at" in runtime
    assert "pid" in runtime

    environment = payload["environment"]
    assert isinstance(environment, list)
    assert all("name" in entry for entry in environment)


def test_configuration_endpoint_marks_admin_token(monkeypatch):
    monkeypatch.setenv(ADMIN_TOKEN_ENV, "top-secret")
    reload_admin_token()

    payload = _request_configuration()
    assert payload["admin"]["configured"] is True

    names = {entry["name"] for entry in payload["environment"]}
    assert ADMIN_TOKEN_ENV not in names


def test_configuration_service_emits_storage_warning_when_unwritable(
    files_root, monkeypatch
):
    _ = files_root
    monkeypatch.setattr(
        "server.application.configuration_service.os.access",
        lambda _path, _mode: False,
        raising=False,
    )
    service = ConfigurationService()
    snapshot = service.snapshot()
    assert any("writable" in warning for warning in snapshot.warnings)


def test_configuration_service_warns_when_disk_usage_unavailable(
    files_root, monkeypatch
):
    _ = files_root

    def _raise(_path):
        raise PermissionError

    monkeypatch.setattr(
        "server.application.configuration_service.shutil.disk_usage",
        _raise,
        raising=False,
    )
    service = ConfigurationService()
    snapshot = service.snapshot()
    assert snapshot.storage.total_bytes is None
    assert snapshot.storage.free_bytes is None
    assert any("disk usage" in warning for warning in snapshot.warnings)


def test_configuration_service_warns_when_parent_unwritable(files_root, monkeypatch):
    root = files_root
    shutil.rmtree(root)

    def _deny(_path, _mode):
        return False

    monkeypatch.setattr(
        "server.application.configuration_service.os.access",
        _deny,
        raising=False,
    )
    try:
        service = ConfigurationService()
        snapshot = service.snapshot()
    finally:
        root.mkdir(parents=True, exist_ok=True)

    assert snapshot.storage.exists is False
    assert any("parent" in warning for warning in snapshot.warnings)


def test_configuration_service_masks_database_password(monkeypatch):
    url = "postgresql+asyncpg://user:secret@example.test/db"
    monkeypatch.setenv("DATABASE_URL", url)
    monkeypatch.setattr(
        "server.application.configuration_service.DATABASE_URL",
        url,
        raising=False,
    )
    service = ConfigurationService()
    snapshot = service.snapshot()
    assert "secret" not in snapshot.database.url
    assert snapshot.database.configured_via_env is True
