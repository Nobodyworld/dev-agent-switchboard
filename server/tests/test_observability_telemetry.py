from fastapi import FastAPI

from server.instrumentation.logging import DEFAULT_REQUEST_ID_HEADER
from server.observability import telemetry


def test_bootstrap_observability_tracks_enabled_subsystems(monkeypatch):
    monkeypatch.setenv("SWITCHBOARD_ENABLE_METRICS", "1")
    monkeypatch.setenv("SWITCHBOARD_ENABLE_TRACING", "1")
    monkeypatch.setenv("SWITCHBOARD_ENABLE_STRUCTURED_LOGGING", "1")

    monkeypatch.setattr(telemetry, "configure_logging", lambda: True)
    monkeypatch.setattr(
        telemetry, "setup_logging", lambda app, header_name=None: header_name == DEFAULT_REQUEST_ID_HEADER
    )
    monkeypatch.setattr(
        telemetry,
        "setup_metrics",
        lambda app, endpoint=None, registry=None, instrumentator=None: True,
    )
    monkeypatch.setattr(telemetry, "setup_tracing", lambda app: True)

    app = FastAPI()
    state = telemetry.bootstrap_observability(app)
    assert state.logging.enabled is True
    assert state.metrics.enabled is True
    assert state.tracing.enabled is True

    payload = telemetry.get_telemetry_report(app_version="1.2.3")
    assert payload["runtime"]["version"] == "1.2.3"
    assert payload["metrics"]["details"]["endpoint"].endswith("/metrics")
    assert payload["metrics"]["details"]["plan_observers"] >= 1
    assert "task_analytics" in payload["metrics"]["details"]
    assert payload["logging"]["warnings"] == []


def test_telemetry_report_surfaces_warnings(monkeypatch):
    for key in [
        "SWITCHBOARD_ENABLE_METRICS",
        "SWITCHBOARD_ENABLE_TRACING",
        "SWITCHBOARD_ENABLE_STRUCTURED_LOGGING",
    ]:
        monkeypatch.delenv(key, raising=False)

    monkeypatch.setattr(telemetry, "configure_logging", lambda: False)
    monkeypatch.setattr(telemetry, "setup_logging", lambda app, header_name=None: False)
    monkeypatch.setattr(telemetry, "setup_metrics", lambda *args, **kwargs: False)
    monkeypatch.setattr(telemetry, "setup_tracing", lambda *args, **kwargs: False)

    app = FastAPI()
    telemetry.bootstrap_observability(app)
    payload = telemetry.get_telemetry_report(app_version=None)

    assert payload["metrics"]["enabled"] is False
    assert any("Prometheus" in warning for warning in payload["metrics"]["warnings"])
    assert payload["tracing"]["enabled"] is False
    assert any("OpenTelemetry" in warning for warning in payload["tracing"]["warnings"])
    assert payload["logging"]["warnings"], "Logging warnings should surface when not configured"
