"""Aggregate observability metadata into a single operator-facing snapshot."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from server.extensions import get_extension_bundle, get_observability_registrations
from server.extensions.interfaces import ObservabilityHookRegistration
from server.observability.diagnostics import collect_diagnostics
from server.observability.metrics import describe_task_metrics
from server.observability.runtime import get_runtime_snapshot
from server.observability.telemetry import get_telemetry_report

from .health import build_liveness_payload, build_readiness_payload


@dataclass(frozen=True)
class ObservabilityOverview:
    """Rich observability snapshot combining telemetry, health, and extensions."""

    generated_at: datetime
    runtime: Mapping[str, Any]
    liveness: Mapping[str, Any]
    readiness: Mapping[str, Any]
    telemetry: Mapping[str, Any]
    diagnostics: Mapping[str, Any]
    metrics_catalog: Mapping[str, Any]
    extensions: Sequence[Mapping[str, Any]]
    observability_hooks: Sequence[Mapping[str, Any]]
    contract: Mapping[str, Any]
    correlation_hints: Mapping[str, Any] = field(default_factory=dict)

    def as_payload(self) -> dict[str, Any]:
        """Return a serialisable dictionary for API responses."""

        return {
            "generated_at": self.generated_at.isoformat(),
            "runtime": dict(self.runtime),
            "liveness": dict(self.liveness),
            "readiness": dict(self.readiness),
            "telemetry": dict(self.telemetry),
            "diagnostics": dict(self.diagnostics),
            "metrics_catalog": dict(self.metrics_catalog),
            "extensions": [dict(entry) for entry in self.extensions],
            "observability_hooks": [dict(entry) for entry in self.observability_hooks],
            "contract": dict(self.contract),
            "correlation_hints": dict(self.correlation_hints),
        }


def _serialize_extension(descriptor) -> Mapping[str, Any]:
    return {
        "name": descriptor.name,
        "capabilities": list(descriptor.capabilities),
        "version": descriptor.version,
        "description": descriptor.description,
        "config": descriptor.config or {},
    }


def _serialize_observability_hook(
    hook: ObservabilityHookRegistration,
    *,
    active: bool,
    payload: Mapping[str, Any] | None,
) -> Mapping[str, Any]:
    data: dict[str, Any] = {
        "extension": hook.extension,
        "description": hook.description,
        "capabilities": list(hook.capabilities),
        "outputs": list(hook.outputs),
        "active": active,
    }
    if payload is not None:
        data["registration"] = dict(payload)
    return data


async def collect_observability_overview(
    session: AsyncSession, *, app_version: str | None = None
) -> ObservabilityOverview:
    """Return a consolidated observability snapshot for operators and agents."""

    now = datetime.now(timezone.utc)
    liveness = build_liveness_payload(version=app_version)
    readiness = await build_readiness_payload(session, version=app_version)
    telemetry = get_telemetry_report(app_version=app_version, include_diagnostics=True)
    diagnostics = telemetry.get("diagnostics") or collect_diagnostics(
        app_version=app_version
    ).as_dict()
    metrics_catalog = describe_task_metrics()
    bundle = get_extension_bundle()
    runtime = get_runtime_snapshot(version=app_version).model_dump()

    snapshot = get_observability_registrations()
    registrations = {
        name: registration.as_payload()
        for name, registration in snapshot.registrations.items()
    }

    hooks = [
        _serialize_observability_hook(
            hook,
            active=hook.extension in registrations,
            payload=registrations.get(hook.extension),
        )
        for hook in bundle.observability_hooks
    ]

    correlation_hints = {
        "request_id_header": telemetry.get("request_id_header"),
        "health_endpoints": telemetry.get("health_endpoints", []),
        "observability_snapshot": snapshot.generated_at.isoformat(),
    }

    extensions = [_serialize_extension(descriptor) for descriptor in bundle.descriptors]
    contract = {
        "api_version": bundle.contract.api_version,
        "notes": list(bundle.contract.notes),
    }

    return ObservabilityOverview(
        generated_at=now,
        runtime=runtime,
        liveness=liveness,
        readiness=readiness,
        telemetry=telemetry,
        diagnostics=diagnostics,
        metrics_catalog=metrics_catalog,
        extensions=extensions,
        observability_hooks=hooks,
        contract=contract,
        correlation_hints=correlation_hints,
    )


__all__ = ["ObservabilityOverview", "collect_observability_overview"]
