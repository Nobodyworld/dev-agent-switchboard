"""Aggregated health probe utilities for Switchboard."""

from __future__ import annotations

import inspect
import logging
import math
import time
from collections.abc import Awaitable, Sequence
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Callable

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
]
