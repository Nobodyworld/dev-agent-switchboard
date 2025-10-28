"""Builtin extension that records plan broadcast snapshots for operators."""

from __future__ import annotations

import datetime as dt
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from server.extensions.contracts import PlanBroadcastContext
from server.extensions.interfaces import ExtensionDescriptor, ExtensionRegistry
from server.extensions.observability import ObservabilityRegistration
from server.observability.runtime import register_runtime_metadata


@dataclass(slots=True)
class _PlanSnapshot:
    version: int | None = None
    ready_tasks: int | None = None
    blocked_tasks: int | None = None
    captured_at: dt.datetime | None = None

    def as_payload(self) -> Mapping[str, Any]:
        return {
            "version": self.version,
            "ready_tasks": self.ready_tasks,
            "blocked_tasks": self.blocked_tasks,
            "captured_at": self.captured_at.isoformat() if self.captured_at else None,
        }


_SNAPSHOT = _PlanSnapshot()


def _update_snapshot(context: PlanBroadcastContext) -> None:
    analytics = context.analytics_as_dict() or {}
    _SNAPSHOT.version = context.version
    _SNAPSHOT.ready_tasks = context.ready_tasks or analytics.get("ready_tasks")
    _SNAPSHOT.blocked_tasks = context.blocked_tasks or analytics.get("blocked_tasks")
    _SNAPSHOT.captured_at = context.generated_at
    register_runtime_metadata(plan_snapshot=_SNAPSHOT.as_payload())


class PlanSnapshotObserver:
    """Observer that records task analytics during plan broadcasts."""

    async def on_plan_broadcast(
        self,
        *,
        version: int | None,
        analytics: Any | None,
        context: PlanBroadcastContext | None = None,
        **_: Any,
    ) -> None:
        ctx = context or PlanBroadcastContext(
            version=version,
            plan=None,
            delta=None,
            analytics=analytics,
        )
        _update_snapshot(ctx)


def _register_observability(_app, _state) -> ObservabilityRegistration | None:
    payload = _SNAPSHOT.as_payload()
    details = {
        "ready_tasks": payload["ready_tasks"],
        "blocked_tasks": payload["blocked_tasks"],
        "last_plan_version": payload["version"],
        "captured_at": payload["captured_at"],
    }
    notes = (
        "Snapshots capture the latest broadcast analytics and support incident triage.",
    )
    return ObservabilityRegistration(details=details, notes=notes)


def register(registry: ExtensionRegistry) -> None:
    """Register the builtin plan snapshot extension."""

    registry.register_extension(
        ExtensionDescriptor(
            name="builtin.plan_snapshot",
            version="1.0.0",
            capabilities=("plan_broadcast", "analytics", "observability"),
            description=(
                "Captures plan broadcast analytics and exposes them via runtime "
                "metadata and observability hooks."
            ),
        )
    )
    registry.append_contract_note(
        "Plan snapshot observer exposes plan analytics via runtime metadata for "
        "dashboards."
    )
    registry.register_plan_observer(PlanSnapshotObserver())
    registry.register_observability_hook(
        "builtin.plan_snapshot",
        _register_observability,
        description="Reports the most recent plan analytics snapshot.",
        capabilities=("analytics", "runtime-metadata"),
        outputs=("runtime.plan_snapshot",),
    )
