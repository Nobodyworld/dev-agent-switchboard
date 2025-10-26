"""Observability bootstrap helpers and telemetry state reporting."""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from fastapi import FastAPI

from server.instrumentation import (
    configure_logging,
    setup_logging,
    setup_metrics,
    setup_tracing,
)
from server.instrumentation.logging import DEFAULT_REQUEST_ID_HEADER

from .diagnostics import DiagnosticsReport, collect_diagnostics
from .runtime import get_runtime_snapshot, register_runtime_metadata


@dataclass(frozen=True)
class TelemetrySubsystemState:
    """Describe the enablement and configuration of a telemetry subsystem."""

    enabled: bool
    configured: bool
    details: Mapping[str, Any] = field(default_factory=dict)
    warnings: tuple[str, ...] = ()


@dataclass(frozen=True)
class TelemetryState:
    """Aggregated view of logging, metrics, and tracing status."""

    generated_at: datetime
    logging: TelemetrySubsystemState
    metrics: TelemetrySubsystemState
    tracing: TelemetrySubsystemState
    request_id_header: str
    health_endpoints: tuple[str, ...] = ("/health/live", "/health/ready", "/health")

    def as_payload(self, *, app_version: str | None = None) -> dict[str, Any]:
        """Return a serialisable payload suitable for API responses."""

        runtime = get_runtime_snapshot(version=app_version).model_dump()
        return {
            "generated_at": self.generated_at,
            "logging": {
                "enabled": self.logging.enabled,
                "configured": self.logging.configured,
                "details": dict(self.logging.details),
                "warnings": list(self.logging.warnings),
            },
            "metrics": {
                "enabled": self.metrics.enabled,
                "configured": self.metrics.configured,
                "details": dict(self.metrics.details),
                "warnings": list(self.metrics.warnings),
            },
            "tracing": {
                "enabled": self.tracing.enabled,
                "configured": self.tracing.configured,
                "details": dict(self.tracing.details),
                "warnings": list(self.tracing.warnings),
            },
            "request_id_header": self.request_id_header,
            "health_endpoints": list(self.health_endpoints),
            "runtime": runtime,
        }


_STATE: TelemetryState | None = None


def _truthy_env(name: str) -> bool:
    value = os.getenv(name)
    if value is None:
        return False
    return value.lower() in {"1", "true", "yes", "on"}


def _parse_headers(raw: str | None) -> Mapping[str, str]:
    headers: dict[str, str] = {}
    if not raw:
        return headers
    for pair in raw.split(","):
        if not pair:
            continue
        if "=" not in pair:
            continue
        key, value = pair.split("=", 1)
        headers[key.strip()] = value.strip()
    return headers


def bootstrap_observability(app: FastAPI) -> TelemetryState:
    """Configure logging, metrics, and tracing for ``app`` and record state."""

    configured_logging = configure_logging()

    request_id_header = os.getenv("SWITCHBOARD_REQUEST_ID_HEADER", DEFAULT_REQUEST_ID_HEADER)
    request_id_enabled = setup_logging(app, header_name=request_id_header)

    metrics_path = os.getenv("SWITCHBOARD_METRICS_PATH", "/metrics")
    metrics_enabled = setup_metrics(app, endpoint=metrics_path)
    metrics_configured = metrics_enabled and _truthy_env("SWITCHBOARD_ENABLE_METRICS")

    tracing_enabled = setup_tracing(app)
    tracing_configured = tracing_enabled and _truthy_env("SWITCHBOARD_ENABLE_TRACING")

    state = TelemetryState(
        generated_at=datetime.now(timezone.utc),
        logging=TelemetrySubsystemState(
            enabled=request_id_enabled or configured_logging,
            configured=configured_logging,
            details={
                "request_id_header": request_id_header,
                "structured": _truthy_env("SWITCHBOARD_ENABLE_STRUCTURED_LOGGING"),
                "config_file": os.getenv("SWITCHBOARD_LOGGING_CONFIG"),
                "dict_config": bool(os.getenv("SWITCHBOARD_LOGGING_DICT")),
            },
            warnings=tuple(
                warning
                for warning in [
                    None
                    if configured_logging or request_id_enabled
                    else "Logging left at Python defaults; install SWITCHBOARD_ENABLE_STRUCTURED_LOGGING to improve parity."
                ]
                if warning
            ),
        ),
        metrics=TelemetrySubsystemState(
            enabled=metrics_enabled,
            configured=metrics_configured,
            details={
                "endpoint": metrics_path,
                "headers": dict(_parse_headers(os.getenv("SWITCHBOARD_METRICS_HEADERS"))),
            },
            warnings=tuple(
                warning
                for warning in [
                    None
                    if metrics_enabled
                    else "Prometheus instrumentation disabled; set SWITCHBOARD_ENABLE_METRICS=1 to expose /metrics."
                ]
                if warning
            ),
        ),
        tracing=TelemetrySubsystemState(
            enabled=tracing_enabled,
            configured=tracing_configured,
            details={
                "exporter": os.getenv("SWITCHBOARD_TRACING_EXPORTER", "console"),
                "otlp_endpoint": os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT"),
            },
            warnings=tuple(
                warning
                for warning in [
                    None
                    if tracing_enabled
                    else "OpenTelemetry instrumentation disabled; set SWITCHBOARD_ENABLE_TRACING=1 for distributed tracing."
                ]
                if warning
            ),
        ),
        request_id_header=request_id_header,
    )

    register_runtime_metadata(
        observability={
            "logging": {
                "configured": state.logging.configured,
                "request_id_header": request_id_header,
            },
            "metrics": {
                "enabled": state.metrics.enabled,
                "endpoint": metrics_path if state.metrics.enabled else None,
            },
            "tracing": {
                "enabled": state.tracing.enabled,
                "exporter": state.tracing.details.get("exporter"),
            },
        }
    )

    global _STATE
    _STATE = state
    return state


def get_telemetry_state() -> TelemetryState:
    """Return the last recorded telemetry state."""

    if _STATE is None:  # pragma: no cover - guarded by bootstrap_observability()
        raise RuntimeError("Observability has not been bootstrapped")
    return _STATE


def get_telemetry_report(
    *, app_version: str | None = None, include_diagnostics: bool = False
) -> dict[str, Any]:
    """Return a serialisable telemetry report for API consumers."""

    state = get_telemetry_state()
    payload = state.as_payload(app_version=app_version)
    if include_diagnostics:
        diagnostics: DiagnosticsReport = collect_diagnostics(app_version=app_version)
        payload["diagnostics"] = diagnostics.as_dict()
    return payload


__all__ = [
    "TelemetryState",
    "TelemetrySubsystemState",
    "bootstrap_observability",
    "get_telemetry_report",
    "get_telemetry_state",
]
