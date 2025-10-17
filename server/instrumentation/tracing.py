"""OpenTelemetry tracing helpers."""

from __future__ import annotations

"""OpenTelemetry tracing instrumentation for Switchboard."""

import logging
import os
from typing import Dict
from weakref import WeakSet

from fastapi import FastAPI

_CONFIG_APPLIED = False
_PROVIDER_CONFIGURED = False
_PROCESSOR_INSTALLED = False
_INSTRUMENTED_APPS: "WeakSet[FastAPI]" = WeakSet()

__all__ = ["setup_tracing"]


def _truthy_env(name: str) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return False
    return raw.lower() in {"1", "true", "yes", "on"}


def _apply_config_file() -> None:
    global _CONFIG_APPLIED

    if _CONFIG_APPLIED:
        return

    config_path = os.getenv("SWITCHBOARD_OTEL_CONFIG")
    if not config_path:
        _CONFIG_APPLIED = True
        return

    if not os.path.exists(config_path):
        logging.getLogger(__name__).warning(
            "OTel config file %s not found", config_path
        )
        _CONFIG_APPLIED = True
        return

    try:
        import yaml  # type: ignore
    except Exception:  # pragma: no cover - optional dependency
        logging.getLogger(__name__).warning(
            "PyYAML is required to load %s but is not installed", config_path
        )
        _CONFIG_APPLIED = True
        return

    with open(config_path, "r", encoding="utf-8") as fh:
        data = yaml.safe_load(fh) or {}

    env_mapping = data.get("env", {})
    if isinstance(env_mapping, dict):
        for key, value in env_mapping.items():
            os.environ.setdefault(str(key), str(value))

    _CONFIG_APPLIED = True


def _parse_otlp_headers(raw: str | None) -> Dict[str, str]:
    headers: Dict[str, str] = {}
    if not raw:
        return headers
    for item in raw.split(","):
        if not item:
            continue
        if "=" not in item:
            continue
        key, value = item.split("=", 1)
        headers[key.strip()] = value.strip()
    return headers


def setup_tracing(app: FastAPI) -> bool:
    """Configure OpenTelemetry tracing when enabled via env vars."""

    global _PROVIDER_CONFIGURED, _PROCESSOR_INSTALLED

    if app in _INSTRUMENTED_APPS:
        return True

    _apply_config_file()

    if not _truthy_env("SWITCHBOARD_ENABLE_TRACING"):
        return False

    try:
        from opentelemetry import trace
        from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
        from opentelemetry.sdk.resources import Resource
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import (
            BatchSpanProcessor,
            ConsoleSpanExporter,
        )
        from opentelemetry.exporter.otlp.proto.http.trace_exporter import (
            OTLPSpanExporter,
        )
    except Exception:  # pragma: no cover - optional dependency
        logging.getLogger(__name__).warning(
            "Tracing requested but OpenTelemetry dependencies are unavailable."
        )
        return False

    resource = Resource.create(
        {"service.name": os.getenv("OTEL_SERVICE_NAME", "switchboard")}
    )

    if not _PROVIDER_CONFIGURED:
        provider = TracerProvider(resource=resource)
        trace.set_tracer_provider(provider)
        _PROVIDER_CONFIGURED = True
    else:
        provider = trace.get_tracer_provider()
        if not isinstance(provider, TracerProvider):
            provider = TracerProvider(resource=resource)
            trace.set_tracer_provider(provider)
            _PROVIDER_CONFIGURED = True

    exporter_kind = os.getenv("SWITCHBOARD_TRACING_EXPORTER", "console").lower()
    if exporter_kind == "otlp":
        headers = _parse_otlp_headers(os.getenv("OTEL_EXPORTER_OTLP_HEADERS"))
        endpoint = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT")
        exporter = OTLPSpanExporter(endpoint=endpoint, headers=headers or None)
    else:
        exporter = ConsoleSpanExporter()

    if not _PROCESSOR_INSTALLED:
        provider.add_span_processor(BatchSpanProcessor(exporter))
        _PROCESSOR_INSTALLED = True

    FastAPIInstrumentor.instrument_app(
        app,
        tracer_provider=provider,
        excluded_urls=os.getenv("SWITCHBOARD_TRACING_EXCLUDED_URLS", "/metrics"),
    )

    _INSTRUMENTED_APPS.add(app)
    return True
