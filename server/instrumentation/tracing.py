"""OpenTelemetry tracing instrumentation for Switchboard."""

from __future__ import annotations

import logging
import os
from weakref import WeakSet

from fastapi import FastAPI

_STATE = {
    "config_applied": False,
    "provider_configured": False,
    "processor_installed": False,
}
_INSTRUMENTED_APPS: WeakSet[FastAPI] = WeakSet()

__all__ = ["setup_tracing"]


def _truthy_env(name: str) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return False
    return raw.lower() in {"1", "true", "yes", "on"}


def _apply_config_file() -> None:
    if _STATE["config_applied"]:
        return

    config_path = os.getenv("SWITCHBOARD_OTEL_CONFIG")
    if not config_path:
        _STATE["config_applied"] = True
        return

    if not os.path.exists(config_path):
        logging.getLogger(__name__).warning(
            "OTel config file %s not found", config_path
        )
        _STATE["config_applied"] = True
        return

    try:
        import yaml  # type: ignore  # noqa: PLC0415 - optional dependency
    except Exception:  # pragma: no cover - optional dependency
        logging.getLogger(__name__).warning(
            "PyYAML is required to load %s but is not installed", config_path
        )
        _STATE["config_applied"] = True
        return

    with open(config_path, encoding="utf-8") as fh:
        data = yaml.safe_load(fh) or {}

    env_mapping = data.get("env", {})
    if isinstance(env_mapping, dict):
        for key, value in env_mapping.items():
            os.environ.setdefault(str(key), str(value))

    _STATE["config_applied"] = True


def _parse_otlp_headers(raw: str | None) -> dict[str, str]:
    headers: dict[str, str] = {}
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

    if app in _INSTRUMENTED_APPS:
        return True

    _apply_config_file()

    if not _truthy_env("SWITCHBOARD_ENABLE_TRACING"):
        return False

    try:
        from opentelemetry import trace  # noqa: PLC0415
        from opentelemetry.exporter.otlp.proto.http.trace_exporter import (  # noqa: PLC0415
            OTLPSpanExporter,
        )
        from opentelemetry.instrumentation.fastapi import (  # noqa: PLC0415
            FastAPIInstrumentor,
        )
        from opentelemetry.sdk.resources import Resource  # noqa: PLC0415
        from opentelemetry.sdk.trace import TracerProvider  # noqa: PLC0415
        from opentelemetry.sdk.trace.export import (  # noqa: PLC0415
            BatchSpanProcessor,
            ConsoleSpanExporter,
        )
    except Exception:  # pragma: no cover - optional dependency
        logging.getLogger(__name__).warning(
            "Tracing requested but OpenTelemetry dependencies are unavailable."
        )
        return False

    resource = Resource.create(
        {"service.name": os.getenv("OTEL_SERVICE_NAME", "switchboard")}
    )

    if not _STATE["provider_configured"]:
        provider = TracerProvider(resource=resource)
        trace.set_tracer_provider(provider)
        _STATE["provider_configured"] = True
    else:
        provider = trace.get_tracer_provider()
        if not isinstance(provider, TracerProvider):
            provider = TracerProvider(resource=resource)
            trace.set_tracer_provider(provider)
            _STATE["provider_configured"] = True

    exporter_kind = os.getenv("SWITCHBOARD_TRACING_EXPORTER", "console").lower()
    if exporter_kind == "otlp":
        headers = _parse_otlp_headers(os.getenv("OTEL_EXPORTER_OTLP_HEADERS"))
        endpoint = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT")
        exporter = OTLPSpanExporter(endpoint=endpoint, headers=headers or None)
    else:
        exporter = ConsoleSpanExporter()

    if not _STATE["processor_installed"]:
        provider.add_span_processor(BatchSpanProcessor(exporter))
        _STATE["processor_installed"] = True

    FastAPIInstrumentor.instrument_app(
        app,
        tracer_provider=provider,
        excluded_urls=os.getenv("SWITCHBOARD_TRACING_EXCLUDED_URLS", "/metrics"),
    )

    _INSTRUMENTED_APPS.add(app)
    return True
