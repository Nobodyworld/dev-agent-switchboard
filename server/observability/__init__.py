"""Observability helpers exposing runtime metadata for Switchboard."""

from .diagnostics import (
    DiagnosticsReport,
    PackageStatus,
    clear_required_versions_cache,
    collect_diagnostics,
)
from .health import (
    build_liveness_payload,
    build_readiness_payload,
    collect_observability_health,
)
from .metrics import describe_task_metrics, record_task_analytics_metrics
from .overview import ObservabilityOverview, collect_observability_overview
from .runtime import RuntimeSnapshot, get_runtime_snapshot, register_runtime_metadata
from .telemetry import (
    TelemetryState,
    TelemetrySubsystemState,
    bootstrap_observability,
    get_telemetry_report,
    get_telemetry_state,
)
from .tracing import span

__all__ = [
    "DiagnosticsReport",
    "ObservabilityOverview",
    "PackageStatus",
    "RuntimeSnapshot",
    "TelemetryState",
    "TelemetrySubsystemState",
    "bootstrap_observability",
    "build_liveness_payload",
    "build_readiness_payload",
    "clear_required_versions_cache",
    "collect_diagnostics",
    "collect_observability_health",
    "collect_observability_overview",
    "describe_task_metrics",
    "get_runtime_snapshot",
    "get_telemetry_report",
    "get_telemetry_state",
    "record_task_analytics_metrics",
    "register_runtime_metadata",
    "span",
]
