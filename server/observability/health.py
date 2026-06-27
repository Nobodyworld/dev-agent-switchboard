"""Aggregated health probe utilities for Switchboard."""

from __future__ import annotations

import inspect
import logging
import math
import os
import time
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

try:  # pragma: no cover - optional dependency for metrics exposure
    from prometheus_client import Counter, Gauge  # type: ignore
except Exception:  # pragma: no cover - gracefully degrade when unavailable
    Counter = None  # type: ignore[assignment]
    Gauge = None  # type: ignore[assignment]

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from server.file_store import ensure_root
from server.observability.runtime import get_runtime_snapshot
from server.observability.telemetry import get_telemetry_report

LOGGER = logging.getLogger(__name__)

ProbeCallable = Callable[[], Awaitable[bool] | bool]


@dataclass(frozen=True)
class ProbeDefinition:
    """Describe a health probe that can be executed for readiness checks."""

    name: str
    callback: ProbeCallable
    critical: bool = True
    failure_detail: str | None = None


@dataclass(frozen=True)
class ProbeObservation:
    """Observation emitted after running a probe."""

    name: str
    ok: bool
    critical: bool
    observed_at: datetime
    duration_ms: float
    detail: str | None = None

    def as_payload(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "name": self.name,
            "ok": self.ok,
            "critical": self.critical,
            "observed_at": self.observed_at.isoformat(),
            "duration_ms": self.duration_ms,
        }
        if self.detail:
            payload["detail"] = self.detail
        return payload


@dataclass
class _ReadinessMetricsState:
    overall_status: Gauge | None = None
    last_checked_timestamp: Gauge | None = None
    probe_status: Gauge | None = None
    probe_duration: Gauge | None = None
    probe_total: Counter | None = None
    last_checked_at: datetime | None = None


_READINESS_METRICS = _ReadinessMetricsState()
_METRICS_ENV_FLAG = "SWITCHBOARD_ENABLE_METRICS"


def _truthy_env(name: str) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return False
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _ensure_readiness_metrics() -> bool:
    if Gauge is None or Counter is None:
        return False
    if not _truthy_env(_METRICS_ENV_FLAG):
        return False
    if _READINESS_METRICS.overall_status is not None:
        return True

    _READINESS_METRICS.overall_status = Gauge(
        "switchboard_readiness_ok",
        "Overall readiness status (1=ready, 0=not ready).",
    )
    _READINESS_METRICS.last_checked_timestamp = Gauge(
        "switchboard_readiness_last_checked_timestamp",
        "Unix timestamp when readiness was last evaluated.",
    )
    _READINESS_METRICS.probe_status = Gauge(
        "switchboard_readiness_probe_status",
        "Latest readiness probe outcome (1=ok, 0=failed).",
        ("probe",),
    )
    _READINESS_METRICS.probe_duration = Gauge(
        "switchboard_readiness_probe_duration_ms",
        "Duration of readiness probes in milliseconds.",
        ("probe",),
    )
    _READINESS_METRICS.probe_total = Counter(
        "switchboard_readiness_probe_total",
        "Total readiness probe executions grouped by result.",
        ("probe", "result"),
    )
    return True


def _record_readiness_metrics(
    observations: Sequence[ProbeObservation], overall_ok: bool
) -> None:
    if not _ensure_readiness_metrics():
        return

    timestamp = time.time()
    state = _READINESS_METRICS
    if state.overall_status is not None:
        state.overall_status.set(1.0 if overall_ok else 0.0)
    if state.last_checked_timestamp is not None:
        state.last_checked_timestamp.set(timestamp)
    state.last_checked_at = datetime.fromtimestamp(timestamp, tz=timezone.utc)

    for observation in observations:
        if state.probe_status is not None:
            state.probe_status.labels(probe=observation.name).set(
                1.0 if observation.ok else 0.0
            )
        if state.probe_duration is not None:
            state.probe_duration.labels(probe=observation.name).set(
                observation.duration_ms
            )
        if state.probe_total is not None:
            state.probe_total.labels(
                probe=observation.name,
                result="ok" if observation.ok else "failed",
            ).inc()


def _collect_samples(metric: Any) -> list[tuple[dict[str, str], float]]:
    if metric is None:
        return []
    collected: list[tuple[dict[str, str], float]] = []
    for family in metric.collect():
        for sample in family.samples:
            if sample.name.endswith("_created"):
                continue
            labels = dict(sample.labels or {})
            collected.append((labels, float(sample.value)))
    return collected


def describe_readiness_metrics() -> dict[str, Any]:
    """Return a snapshot of readiness metrics for diagnostics."""

    enabled = (
        _READINESS_METRICS.overall_status is not None
        and _truthy_env(_METRICS_ENV_FLAG)
        and Gauge is not None
        and Counter is not None
    )
    status = None
    last_checked = None
    if enabled:
        for _, value in _collect_samples(_READINESS_METRICS.overall_status):
            status = value
        for _, value in _collect_samples(
            _READINESS_METRICS.last_checked_timestamp
        ):
            last_checked = value

    probe_status: dict[str, float] = {}
    probe_duration: dict[str, float] = {}
    probe_totals: dict[str, dict[str, float]] = {}
    if enabled:
        for labels, value in _collect_samples(_READINESS_METRICS.probe_status):
            key = labels.get("probe", "")
            probe_status[key] = value
        for labels, value in _collect_samples(_READINESS_METRICS.probe_duration):
            key = labels.get("probe", "")
            probe_duration[key] = value
        for labels, value in _collect_samples(_READINESS_METRICS.probe_total):
            probe = labels.get("probe", "")
            result = labels.get("result", "") or "value"
            bucket = probe_totals.setdefault(probe, {})
            bucket[result] = value

    return {
        "enabled": bool(enabled),
        "overall_status": status,
        "last_checked_timestamp": last_checked,
        "last_checked_at": _READINESS_METRICS.last_checked_at,
        "probe_status": probe_status,
        "probe_duration_ms": probe_duration,
        "probe_totals": probe_totals,
    }


def _reset_readiness_metrics_for_testing() -> None:  # pragma: no cover - tests only
    state = _READINESS_METRICS
    if state.probe_status is not None:
        state.probe_status.clear()
    if state.probe_duration is not None:
        state.probe_duration.clear()
    if state.probe_total is not None:
        state.probe_total.clear()
    if state.overall_status is not None:
        state.overall_status.set(0.0)
    if state.last_checked_timestamp is not None:
        state.last_checked_timestamp.set(0.0)
    state.last_checked_at = None


async def _run_probe(definition: ProbeDefinition) -> ProbeObservation:
    """Execute ``definition`` and return an observation."""

    observed_at = datetime.now(timezone.utc)
    started = time.perf_counter()
    detail: str | None = None
    ok = True
    try:
        result = definition.callback()
        if inspect.isawaitable(result):
            result = await result  # type: ignore[assignment]
        ok = bool(result)
    except Exception as exc:  # pragma: no cover - surfaced via observation payload
        ok = False
        detail = definition.failure_detail or str(exc)
        LOGGER.warning("Probe %s failed", definition.name, exc_info=True)
    duration_ms = (time.perf_counter() - started) * 1000
    if math.isnan(duration_ms) or math.isinf(duration_ms):
        duration_ms = 0.0
    return ProbeObservation(
        name=definition.name,
        ok=ok,
        critical=definition.critical,
        observed_at=observed_at,
        duration_ms=duration_ms,
        detail=detail,
    )


async def _probe_database(session: AsyncSession) -> bool:
    await session.execute(select(1))
    return True


async def _probe_storage() -> bool:
    ensure_root()
    return True


def _aggregate_checks(
    observations: Sequence[ProbeObservation],
) -> tuple[dict[str, bool], bool]:
    checks: dict[str, bool] = {}
    overall_ok = True
    for observation in observations:
        checks[observation.name] = observation.ok
        if observation.critical:
            overall_ok = overall_ok and observation.ok
    return checks, overall_ok


def build_liveness_payload(*, version: str | None = None) -> dict[str, Any]:
    """Return payload for ``/health/live`` including runtime metadata."""

    runtime = get_runtime_snapshot(version=version)
    observation = ProbeObservation(
        name="process",
        ok=True,
        critical=True,
        observed_at=datetime.now(timezone.utc),
        duration_ms=0.0,
    )
    payload: dict[str, Any] = {
        "ok": True,
        "checks": {"process": True},
        "observations": [observation.as_payload()],
    }
    payload.update(runtime.model_dump())
    return payload


async def build_readiness_payload(
    session: AsyncSession,
    *,
    version: str | None = None,
) -> dict[str, Any]:
    """Return payload for ``/health/ready`` including dependency probes."""

    probes = (
        ProbeDefinition(
            name="database",
            callback=lambda: _probe_database(session),
            failure_detail="Database connectivity check failed.",
        ),
        ProbeDefinition(
            name="storage",
            callback=_probe_storage,
            failure_detail="Storage root is inaccessible.",
        ),
    )
    observations = [await _run_probe(probe) for probe in probes]
    checks, overall_ok = _aggregate_checks(observations)
    runtime = get_runtime_snapshot(version=version)
    payload: dict[str, Any] = {
        "ok": overall_ok,
        "checks": checks,
        "observations": [obs.as_payload() for obs in observations],
    }
    payload.update(runtime.model_dump())
    _record_readiness_metrics(observations, overall_ok)
    return payload


async def collect_observability_health(
    session: AsyncSession,
    *,
    version: str | None = None,
) -> dict[str, Any]:
    """Return an aggregated observability payload for the public API."""

    readiness = await build_readiness_payload(session, version=version)
    liveness = build_liveness_payload(version=version)
    telemetry = get_telemetry_report(app_version=version)
    return {
        "generated_at": datetime.now(timezone.utc),
        "liveness": liveness,
        "readiness": readiness,
        "telemetry": telemetry,
        "probes": readiness.get("observations", []),
    }


__all__ = [
    "ProbeDefinition",
    "ProbeObservation",
    "build_liveness_payload",
    "build_readiness_payload",
    "collect_observability_health",
    "describe_readiness_metrics",
]
