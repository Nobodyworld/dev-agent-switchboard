"""Observability helpers exposing runtime metadata for Switchboard."""

from .diagnostics import (
    DiagnosticsReport,
    PackageStatus,
    clear_required_versions_cache,
    collect_diagnostics,
)
from .runtime import RuntimeSnapshot, get_runtime_snapshot, register_runtime_metadata
from .telemetry import (
    TelemetryState,
    TelemetrySubsystemState,
    bootstrap_observability,
    get_telemetry_report,
    get_telemetry_state,
)

__all__ = [
    "DiagnosticsReport",
    "PackageStatus",
    "RuntimeSnapshot",
    "TelemetryState",
    "TelemetrySubsystemState",
    "bootstrap_observability",
    "clear_required_versions_cache",
    "collect_diagnostics",
    "get_runtime_snapshot",
    "get_telemetry_report",
    "get_telemetry_state",
    "register_runtime_metadata",
]
