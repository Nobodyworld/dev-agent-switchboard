"""Builtin extension that records plan broadcast intervals for observability."""

from __future__ import annotations

import os
import time
from collections.abc import Mapping
from typing import TYPE_CHECKING, Any

try:  # pragma: no cover - optional dependency
    from prometheus_client import Histogram  # type: ignore
except Exception:  # pragma: no cover - graceful degradation when missing
    Histogram = None  # type: ignore[assignment]

from fastapi import FastAPI

from server.extensions.interfaces import ExtensionDescriptor, ExtensionRegistry
from server.extensions.observability import ObservabilityRegistration

if TYPE_CHECKING:  # pragma: no cover - typing only
    from server.observability.telemetry import TelemetryState
else:  # pragma: no cover - runtime fallback avoids import cycles
    TelemetryState = Any  # type: ignore[assignment]

HISTOGRAM_BUCKETS: tuple[float, ...] = (
    0.5,
    1.0,
    2.0,
    5.0,
    10.0,
    30.0,
    60.0,
    120.0,
    300.0,
)
_HISTOGRAM_STATE: dict[str, Histogram | None] = {"value": None}


def _truthy_env(name: str) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return False
    return raw.lower() in {"1", "true", "yes", "on"}


def _ensure_histogram() -> Histogram | None:
    """Return the latency histogram when metrics instrumentation is enabled."""

    if Histogram is None:
        return None
    if not _truthy_env("SWITCHBOARD_ENABLE_METRICS"):
        return None
    histogram = _HISTOGRAM_STATE["value"]
    if histogram is None:
        histogram = Histogram(
            "switchboard_plan_broadcast_interval_seconds",
            "Seconds elapsed between plan broadcasts.",
            buckets=HISTOGRAM_BUCKETS,
        )
        _HISTOGRAM_STATE["value"] = histogram
    return histogram


class PlanLatencyObserver:
    """Track time elapsed between plan broadcasts."""

    def __init__(self) -> None:
        self._last_emitted: float | None = None

    async def on_plan_broadcast(
        self,
        *,
        version: int | None,
        plan: Mapping[str, Any] | None,
        delta: Mapping[str, Any] | None,
        analytics: Any | None,
    ) -> None:
        _ = (version, plan, delta, analytics)
        histogram = _ensure_histogram()
        if histogram is None:
            return
        now = time.perf_counter()
        if self._last_emitted is not None:
            interval = max(0.0, now - self._last_emitted)
            histogram.observe(interval)
        self._last_emitted = now


def _register_observability(
    _app: FastAPI, state: TelemetryState
) -> ObservabilityRegistration | None:
    histogram = _ensure_histogram()
    if histogram is None:
        return None
    return ObservabilityRegistration(
        details={
            "metric": histogram._name,  # type: ignore[attr-defined]
            "buckets": list(HISTOGRAM_BUCKETS),
            "enabled": state.metrics.enabled,
        },
        metrics=(
            {
                "name": histogram._name,  # type: ignore[attr-defined]
                "description": histogram._documentation,  # type: ignore[attr-defined]
                "type": "histogram",
                "buckets": list(HISTOGRAM_BUCKETS),
            },
        ),
        notes=(
            "Records seconds between successive plan broadcasts; alerts operators"
            " to stale plans."
        ),
    )


def register(registry: ExtensionRegistry) -> None:
    """Register the builtin plan latency observer and observability hook."""

    registry.register_extension(
        ExtensionDescriptor(
            name="builtin.plan_latency",
            capabilities=("plan_observer", "metrics"),
            version="1.0.0",
            description=(
                "Adds a Prometheus histogram measuring plan broadcast intervals."
            ),
            config={"requires_metrics": True},
        )
    )
    registry.append_contract_note(
        "Plan latency observer emits histogram metrics when "
        "SWITCHBOARD_ENABLE_METRICS=1."
    )
    registry.register_plan_observer(PlanLatencyObserver())
    registry.register_observability_hook(
        "builtin.plan_latency",
        _register_observability,
        description="Installs histogram metrics for plan broadcast intervals.",
        capabilities=("metrics", "plan_observer"),
        outputs=("metrics",),
    )


register_extension = register
