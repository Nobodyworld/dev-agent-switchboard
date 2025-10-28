from __future__ import annotations

from http import HTTPStatus

import pytest
from fastapi.testclient import TestClient

from server.api import AppConfig, create_app


@pytest.mark.unit
def test_create_app_supports_custom_title() -> None:
    app = create_app(
        AppConfig(title="Switchboard Test", include_ui=False, cors_allow_origins=[])
    )
    assert app.title == "Switchboard Test"
    with TestClient(app) as client:
        response = client.get("/health")
        assert response.status_code == HTTPStatus.OK
        assert response.text == "OK"


@pytest.mark.unit
def test_app_includes_configuration_routes() -> None:
    app = create_app(AppConfig(include_ui=False))
    with TestClient(app) as client:
        response = client.get("/api/settings")
        assert response.status_code == HTTPStatus.OK
        payload = response.json()
        assert "rate_limit" in payload
        assert "lease" in payload
