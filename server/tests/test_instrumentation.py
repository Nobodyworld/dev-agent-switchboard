import asyncio

import pytest
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

from server.instrumentation import configure_logging, setup_logging, setup_metrics, setup_tracing


@pytest.fixture(autouse=True)
def reset_flags(monkeypatch):
    # Ensure environment variables from other tests do not leak in.
    for key in [
        "SWITCHBOARD_ENABLE_STRUCTURED_LOGGING",
        "SWITCHBOARD_LOGGING_CONFIG",
        "SWITCHBOARD_ENABLE_METRICS",
        "SWITCHBOARD_METRICS_PATH",
        "SWITCHBOARD_ENABLE_TRACING",
        "SWITCHBOARD_TRACING_EXPORTER",
        "SWITCHBOARD_OTEL_CONFIG",
    ]:
        monkeypatch.delenv(key, raising=False)
    yield


def test_request_id_middleware_roundtrip():
    app = FastAPI()
    setup_logging(app)

    @app.get("/ping")
    async def ping(request: Request):
        return {"request_id": getattr(request.state, "request_id", None)}

    client = TestClient(app)
    request_id = "req-test"
    response = client.get("/ping", headers={"X-Request-ID": request_id})
    assert response.status_code == 200
    assert response.json()["request_id"] == request_id
    assert response.headers["X-Request-ID"] == request_id


def test_instrumentation_smoke(monkeypatch):
    pytest.importorskip(
        "prometheus_fastapi_instrumentator",
        reason="Prometheus instrumentation is not installed",
    )
    pytest.importorskip(
        "opentelemetry.instrumentation.fastapi",
        reason="OpenTelemetry FastAPI instrumentation is not installed",
    )

    monkeypatch.setenv("SWITCHBOARD_ENABLE_STRUCTURED_LOGGING", "1")
    monkeypatch.setenv("SWITCHBOARD_ENABLE_METRICS", "1")
    monkeypatch.setenv("SWITCHBOARD_ENABLE_TRACING", "1")
    monkeypatch.setenv("SWITCHBOARD_TRACING_EXPORTER", "console")

    configure_logging()

    app = FastAPI()

    setup_logging(app)
    setup_metrics(app)
    setup_tracing(app)

    @app.get("/ping")
    async def ping(request: Request):
        return {"request_id": getattr(request.state, "request_id", None)}

    client = TestClient(app)

    metrics_response = client.get("/metrics")
    assert metrics_response.status_code == 200

    request_id = "req-test"
    ping_response = client.get("/ping", headers={"X-Request-ID": request_id})
    assert ping_response.status_code == 200
    assert ping_response.json()["request_id"] == request_id
    assert ping_response.headers["X-Request-ID"] == request_id


def test_instrumentation_does_not_break_event_loop(monkeypatch):
    pytest.importorskip(
        "prometheus_fastapi_instrumentator",
        reason="Prometheus instrumentation is not installed",
    )
    monkeypatch.setenv("SWITCHBOARD_ENABLE_METRICS", "1")

    app = FastAPI()
    setup_metrics(app)

    async def call_metrics():
        from httpx import AsyncClient

        async with AsyncClient(app=app, base_url="http://test") as client:
            response = await client.get("/metrics")
            assert response.status_code == 200

    asyncio.run(call_metrics())
