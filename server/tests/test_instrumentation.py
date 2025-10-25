import asyncio
import json
import logging
import sys
from http import HTTPStatus
from types import SimpleNamespace
from typing import ClassVar
from weakref import WeakKeyDictionary, WeakSet

import pytest
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

from server.instrumentation import (
    configure_logging,
    logging as logging_module,
    metrics as metrics_module,
    setup_logging,
    setup_metrics,
    setup_tracing,
)
from server.instrumentation.logging import RequestIdFilter


@pytest.fixture(autouse=True)
def reset_flags(monkeypatch):
    # Ensure environment variables from other tests do not leak in.
    for key in [
        "SWITCHBOARD_ENABLE_STRUCTURED_LOGGING",
        "SWITCHBOARD_LOGGING_CONFIG",
        "SWITCHBOARD_LOGGING_DICT",
        "SWITCHBOARD_ENABLE_METRICS",
        "SWITCHBOARD_METRICS_PATH",
        "SWITCHBOARD_ENABLE_TRACING",
        "SWITCHBOARD_TRACING_EXPORTER",
        "SWITCHBOARD_OTEL_CONFIG",
    ]:
        monkeypatch.delenv(key, raising=False)

    logging_module._STATE.configured = False  # type: ignore[attr-defined]
    logging_module._STATE.initialized = False  # type: ignore[attr-defined]
    logging_module._STATE.request_filter_installed = False  # type: ignore[attr-defined]
    monkeypatch.setattr(metrics_module, "_INSTRUMENTED_APPS", WeakSet())
    monkeypatch.setattr(metrics_module, "_APP_INSTRUMENTATORS", WeakKeyDictionary())

    root = logging.getLogger()
    for existing in list(root.filters):
        if isinstance(existing, RequestIdFilter):
            root.removeFilter(existing)
    root.handlers.clear()
    root.setLevel(logging.NOTSET)
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
    assert response.status_code == HTTPStatus.OK
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
    assert metrics_response.status_code == HTTPStatus.OK

    request_id = "req-test"
    ping_response = client.get("/ping", headers={"X-Request-ID": request_id})
    assert ping_response.status_code == HTTPStatus.OK
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
        httpx = pytest.importorskip("httpx")

        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport, base_url="http://test"
        ) as client:
            response = await client.get("/metrics")
            assert response.status_code == HTTPStatus.OK

    asyncio.run(call_metrics())


def test_configure_logging_accepts_dict(monkeypatch):
    config = {
        "version": 1,
        "disable_existing_loggers": False,
        "handlers": {
            "console": {
                "class": "logging.StreamHandler",
                "level": "INFO",
            }
        },
        "root": {
            "handlers": ["console"],
            "level": "WARNING",
        },
    }
    monkeypatch.setenv("SWITCHBOARD_LOGGING_DICT", json.dumps(config))
    configured = configure_logging()
    assert configured is True
    root = logging.getLogger()
    assert root.level == logging.WARNING
    assert any(isinstance(filt, RequestIdFilter) for filt in root.filters)


def test_configure_logging_retries_when_dependencies_arrive(monkeypatch):
    monkeypatch.setenv("SWITCHBOARD_ENABLE_STRUCTURED_LOGGING", "1")
    monkeypatch.setattr(logging_module, "jsonlogger", None, raising=False)

    first = configure_logging()
    assert first is True  # Request ID filter installation counts as configuration.
    assert logging_module._STATE.configured is False  # type: ignore[attr-defined]

    dummy = SimpleNamespace(JsonFormatter=lambda fmt: logging.Formatter(fmt))
    monkeypatch.setattr(logging_module, "jsonlogger", dummy, raising=False)

    second = configure_logging()
    assert second is True
    assert logging_module._STATE.configured is True  # type: ignore[attr-defined]
    root = logging.getLogger()
    assert root.handlers, "Structured logging should install a handler"


def test_setup_metrics_uses_custom_registry(monkeypatch):
    monkeypatch.setenv("SWITCHBOARD_ENABLE_METRICS", "1")

    class FakeInstrumentator:
        instances: ClassVar[list["FakeInstrumentator"]] = []

        def __init__(self, registry=None):
            self.__class__.instances.append(self)
            self.registry = registry
            self.instrumented_app = None
            self.exposed = None

        def instrument(self, app):
            self.instrumented_app = app
            return self

        def expose(self, app, endpoint, include_in_schema, should_gzip):
            self.exposed = (app, endpoint, include_in_schema, should_gzip)
            return self

    monkeypatch.setitem(
        sys.modules,
        "prometheus_fastapi_instrumentator",
        SimpleNamespace(Instrumentator=FakeInstrumentator),
    )
    monkeypatch.setattr(
        metrics_module, "Instrumentator", FakeInstrumentator, raising=False
    )

    app = FastAPI()
    registry = object()
    activated = setup_metrics(app, endpoint="/custom-metrics", registry=registry)
    assert activated is True
    assert FakeInstrumentator.instances[0].registry is registry
    assert FakeInstrumentator.instances[0].exposed[1] == "/custom-metrics"

    # Second invocation should be a no-op and not create a new instrumentator
    setup_metrics(app, registry=object())
    assert len(FakeInstrumentator.instances) == 1
