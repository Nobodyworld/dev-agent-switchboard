from http import HTTPStatus
from unittest.mock import patch

from fastapi.testclient import TestClient

from server.app import app


def test_health_live_returns_process_check():
    client = TestClient(app)
    response = client.get("/health/live")
    assert response.status_code == HTTPStatus.OK
    payload = response.json()
    assert payload["ok"] is True
    assert payload["checks"] == {"process": True}
    assert payload["version"] == app.version


def test_health_ready_reports_dependencies():
    client = TestClient(app)
    response = client.get("/health/ready")
    assert response.status_code == HTTPStatus.OK
    payload = response.json()
    assert payload["ok"] is True
    assert payload["checks"]["database"] is True
    assert payload["checks"]["storage"] is True
    assert payload["version"] == app.version


def test_health_ready_returns_503_when_storage_fails():
    client = TestClient(app)
    with patch("server.app.ensure_root", side_effect=Exception("boom")):
        response = client.get("/health/ready")
    assert response.status_code == HTTPStatus.SERVICE_UNAVAILABLE
    payload = response.json()
    assert payload["ok"] is False
    assert payload["checks"]["storage"] is False
