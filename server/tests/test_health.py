import asyncio
from http import HTTPStatus
from unittest.mock import patch

from fastapi.testclient import TestClient

from server.app import app
from server.observability import activity
from server.observability.health import (
    Gauge as ReadinessGauge,
    _reset_readiness_metrics_for_testing,
    describe_readiness_metrics,
)

import pytest


def test_health_live_returns_process_check():
    client = TestClient(app)
    response = client.get("/health/live")
    assert response.status_code == HTTPStatus.OK
    payload = response.json()
    assert payload["ok"] is True
    assert payload["checks"] == {"process": True}
    assert payload["version"] == app.version
    assert "started_at" in payload
    assert payload["uptime_seconds"] >= 0
    assert payload["pid"] > 0
    assert payload["observations"]


def test_health_ready_reports_dependencies():
    client = TestClient(app)
    response = client.get("/health/ready")
    assert response.status_code == HTTPStatus.OK
    payload = response.json()
    assert payload["ok"] is True
    assert payload["checks"]["database"] is True
    assert payload["checks"]["storage"] is True
    assert payload["version"] == app.version
    assert "started_at" in payload
    assert payload["uptime_seconds"] >= 0
    assert payload["pid"] > 0
    assert any(obs["name"] == "database" for obs in payload["observations"])


@pytest.mark.skipif(
    ReadinessGauge is None, reason="prometheus_client not installed"
)
def test_health_ready_updates_metrics_when_enabled(monkeypatch):
    monkeypatch.setenv("SWITCHBOARD_ENABLE_METRICS", "1")
    _reset_readiness_metrics_for_testing()
    client = TestClient(app)

    before = describe_readiness_metrics()
    before_ok = before["probe_totals"].get("database", {}).get("ok", 0.0)

    response = client.get("/health/ready")
    assert response.status_code == HTTPStatus.OK

    after = describe_readiness_metrics()
    assert after["enabled"] is True
    assert after["overall_status"] == pytest.approx(1.0)
    database_ok = after["probe_totals"].get("database", {}).get("ok", 0.0)
    assert database_ok == pytest.approx(before_ok + 1.0)
    assert after["probe_status"]["database"] == pytest.approx(1.0)
    assert after["probe_duration_ms"]["database"] >= 0.0

    _reset_readiness_metrics_for_testing()


def test_health_ready_returns_503_when_storage_fails():
    client = TestClient(app)
    with patch(
        "server.observability.health.ensure_root",
        side_effect=Exception("boom"),
    ):
        response = client.get("/health/ready")
    assert response.status_code == HTTPStatus.SERVICE_UNAVAILABLE
    payload = response.json()
    assert payload["ok"] is False
    assert payload["checks"]["storage"] is False
    assert payload["uptime_seconds"] >= 0
    failing = next(
        (obs for obs in payload["observations"] if obs["name"] == "storage"),
        None,
    )
    assert failing is not None
    assert failing["ok"] is False


def test_observability_health_endpoint_returns_combined_payload():
    client = TestClient(app)
    response = client.get("/api/observability/health")
    assert response.status_code == HTTPStatus.OK
    payload = response.json()
    assert payload["liveness"]["checks"]["process"] is True
    assert payload["readiness"]["checks"]["database"] is True
    assert payload["telemetry"]
    assert payload["probes"]


def test_activity_feed_endpoint_reports_events():
    activity.reset_activity_feed(limit=32)
    client = TestClient(app)
    asyncio.run(activity.record_event("test.event", payload={"example": True}))
    response = client.get("/api/observability/audit-feed")
    assert response.status_code == HTTPStatus.OK
    payload = response.json()
    assert payload["events"]
    assert payload["events"][0]["kind"] == "test.event"


def test_combined_health_endpoint_reports_status():
    client = TestClient(app)
    response = client.get("/api/health")
    assert response.status_code == HTTPStatus.OK
    payload = response.json()
    assert payload["ok"] is True
    assert "liveness" in payload
    assert "readiness" in payload


def test_observability_telemetry_endpoint_returns_subsystems():
    client = TestClient(app)
    response = client.get("/api/observability/telemetry")
    assert response.status_code == HTTPStatus.OK
    payload = response.json()
    assert payload["logging"]["enabled"] in {True, False}
    assert payload["metrics"]["details"]
    assert payload["tracing"]["configured"] in {True, False}
    assert payload["runtime"]


def test_observability_metrics_endpoint_returns_catalog():
    client = TestClient(app)
    response = client.get("/api/observability/metrics")
    assert response.status_code == HTTPStatus.OK
    payload = response.json()
    assert "generated_at" in payload
    allowed_keys = {"value", "total", "pending", "in_progress", "completed"}
    assert set(payload["status"].keys()) <= allowed_keys
