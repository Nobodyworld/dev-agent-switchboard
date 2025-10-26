"""Helpers for publishing task analytics metrics and describing their state."""

from __future__ import annotations

import math
import os
import time
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:  # pragma: no cover - typing imports only
    from server.domain import TaskAnalytics
else:  # pragma: no cover - runtime fallback keeps optional dependency optional
    TaskAnalytics = Any  # type: ignore[assignment]

try:  # pragma: no cover - dependency is optional in minimal installs
    from prometheus_client import Gauge  # type: ignore
except Exception:  # pragma: no cover - gracefully degrade when unavailable
    Gauge = None  # type: ignore[assignment]


@dataclass(frozen=True)
class _GaugeSpec:
    attr: str
    name: str
    description: str
    labels: tuple[str, ...] = ()


class _GaugeState:
    def __init__(self) -> None:
        self.status: Gauge | None = None
        self.readiness: Gauge | None = None
        self.dependency_count: Gauge | None = None
        self.dependency_edges: Gauge | None = None
        self.missing_dependencies: Gauge | None = None
        self.average_dependencies: Gauge | None = None
        self.updated_timestamp: Gauge | None = None
        self.last_updated: datetime | None = None


_STATE = _GaugeState()

_GAUGE_SPECS: tuple[_GaugeSpec, ...] = (
    _GaugeSpec(
        "status",
        "switchboard_task_status_total",
        "Number of tasks grouped by status.",
        ("status",),
    ),
    _GaugeSpec(
        "readiness",
        "switchboard_task_readiness_total",
        "Number of tasks grouped by readiness state.",
        ("state",),
    ),
    _GaugeSpec(
        "dependency_count",
        "switchboard_task_dependency_count_total",
        "Number of tasks grouped by dependency characteristics.",
        ("category",),
    ),
    _GaugeSpec(
        "dependency_edges",
        "switchboard_task_dependency_edges_total",
        "Total number of dependency edges across all tasks.",
    ),
    _GaugeSpec(
        "missing_dependencies",
        "switchboard_task_missing_dependency_total",
        "Missing dependencies grouped by entity type.",
        ("category",),
    ),
    _GaugeSpec(
        "average_dependencies",
        "switchboard_task_average_dependencies",
        "Average number of dependencies per task.",
    ),
    _GaugeSpec(
        "updated_timestamp",
        "switchboard_task_metrics_updated_timestamp",
        "Unix timestamp when analytics metrics were last refreshed.",
    ),
)

__all__ = [
    "describe_task_metrics",
    "record_task_analytics_metrics",
]


def _truthy_env(name: str) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return False
    return raw.lower() in {"1", "true", "yes", "on"}


def _ensure_gauges() -> bool:
    """Return ``True`` when Prometheus gauges are available for updates."""

    if Gauge is None:
        return False
    if not _truthy_env("SWITCHBOARD_ENABLE_METRICS"):
        return False
    if _STATE.status is not None:
        return True

    for spec in _GAUGE_SPECS:
        if spec.labels:
            gauge = Gauge(spec.name, spec.description, spec.labels)
        else:
            gauge = Gauge(spec.name, spec.description)
        setattr(_STATE, spec.attr, gauge)
    return True


def _set_labeled(
    gauge: Gauge | None, label_name: str, mapping: Mapping[str, float]
) -> None:
    if gauge is None:
        return
    for label, value in mapping.items():
        gauge.labels(**{label_name: label}).set(value)


def _set_value(gauge: Gauge | None, value: float) -> None:
    if gauge is None:
        return
    gauge.set(value)


def record_task_analytics_metrics(*, analytics: TaskAnalytics) -> bool:
    """Update Prometheus gauges with analytics data when metrics are enabled."""

    if not _ensure_gauges():
        return False

    status_mapping = {
        "total": float(analytics.total_tasks),
        "pending": float(analytics.pending_tasks),
        "in_progress": float(analytics.in_progress_tasks),
        "completed": float(analytics.completed_tasks),
    }
    readiness_mapping = {
        "ready": float(analytics.ready_tasks),
        "blocked": float(analytics.blocked_tasks),
    }
    dependency_mapping = {
        "with_dependencies": float(analytics.with_dependencies),
        "without_dependencies": float(analytics.without_dependencies),
    }
    missing_mapping = {
        "tasks": float(analytics.missing_dependency_tasks),
        "edges": float(analytics.missing_dependency_edges),
    }

    _set_labeled(_STATE.status, "status", status_mapping)
    _set_labeled(_STATE.readiness, "state", readiness_mapping)
    _set_labeled(_STATE.dependency_count, "category", dependency_mapping)
    _set_labeled(_STATE.missing_dependencies, "category", missing_mapping)
    _set_value(_STATE.dependency_edges, float(analytics.dependency_edges))
    average = analytics.average_dependencies
    if not math.isfinite(average):
        average = 0.0
    _set_value(_STATE.average_dependencies, float(average))
    now = time.time()
    _set_value(_STATE.updated_timestamp, now)

    _STATE.last_updated = datetime.fromtimestamp(now, tz=timezone.utc)
    return True


def _collect_samples(gauge: Gauge | None) -> dict[str, float]:
    if gauge is None:
        return {}
    samples: dict[str, float] = {}
    for metric in gauge.collect():
        for sample in metric.samples:
            if sample.name.endswith("_created"):
                continue
            label_value = ""
            if sample.labels:
                label_value = next(iter(sample.labels.values()), "")
            samples[label_value or "value"] = float(sample.value)
    return samples


def _scalar_from_samples(gauge: Gauge | None) -> float:
    samples = _collect_samples(gauge)
    return next(iter(samples.values()), 0.0)


def describe_task_metrics() -> dict[str, Any]:
    """Return metadata about analytics metrics for telemetry responses."""

    enabled = Gauge is not None and _truthy_env("SWITCHBOARD_ENABLE_METRICS")
    status = _collect_samples(_STATE.status) if enabled else {}
    readiness = _collect_samples(_STATE.readiness) if enabled else {}
    dependency = _collect_samples(_STATE.dependency_count) if enabled else {}
    missing = _collect_samples(_STATE.missing_dependencies) if enabled else {}
    last_updated = _STATE.last_updated
    return {
        "enabled": bool(enabled and _STATE.status is not None),
        "last_updated_at": last_updated,
        "status": status,
        "readiness": readiness,
        "dependency": dependency,
        "missing": missing,
        "dependency_edges": _scalar_from_samples(_STATE.dependency_edges),
        "average_dependencies": _scalar_from_samples(_STATE.average_dependencies),
        "updated_timestamp": _scalar_from_samples(_STATE.updated_timestamp),
    }


def _reset_for_testing() -> None:  # pragma: no cover - used in tests only
    _STATE.last_updated = None
