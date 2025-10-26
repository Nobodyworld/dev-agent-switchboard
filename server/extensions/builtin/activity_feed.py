"""Builtin extension that records a rolling audit feed for observability."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from server.extensions.interfaces import ExtensionDescriptor, ExtensionRegistry
from server.observability import activity

LOGGER = logging.getLogger(__name__)

if TYPE_CHECKING:  # pragma: no cover - typing imports only
    from server.domain import (
        Agent,
        CheckoutResult,
        CompletionResult,
        HeartbeatResult,
        TaskAnalytics,
        TaskRecord,
    )
else:  # pragma: no cover - runtime fallbacks keep optional deps optional
    Agent = Any  # type: ignore[assignment]
    CheckoutResult = Any  # type: ignore[assignment]
    CompletionResult = Any  # type: ignore[assignment]
    HeartbeatResult = Any  # type: ignore[assignment]
    TaskAnalytics = Any  # type: ignore[assignment]
    TaskRecord = Any  # type: ignore[assignment]


async def _record(kind: str, **payload: Any) -> None:
    try:
        await activity.record_event(kind, **payload)
    except Exception:  # pragma: no cover - defensive logging
        LOGGER.exception("Failed to record %s event for activity feed", kind)


class ActivityFeedHook:
    """Task lifecycle hook that records audit events."""

    async def on_task_created(self, *, task: TaskRecord) -> None:
        await _record(
            "task.created",
            task_id=task.id,
            payload={"title": task.title, "status": getattr(task, "status", None)},
        )

    async def on_task_updated(self, *, task: TaskRecord) -> None:
        await _record(
            "task.updated",
            task_id=task.id,
            payload={"title": task.title, "status": getattr(task, "status", None)},
        )

    async def on_checkout(self, *, agent: Agent, result: CheckoutResult) -> None:
        await _record(
            "task.checkout",
            agent_id=getattr(agent, "agent_id", None),
            task_id=getattr(getattr(result, "task", None), "id", None),
            payload={"reason": getattr(result, "reason", None)},
        )

    async def on_complete(self, *, agent_id: str, result: CompletionResult) -> None:
        await _record(
            "task.complete",
            agent_id=agent_id,
            task_id=getattr(getattr(result, "task", None), "id", None),
            payload={"ok": getattr(result, "ok", None)},
        )

    async def on_abandon(self, *, agent_id: str, result: HeartbeatResult) -> None:
        await _record(
            "task.abandon",
            agent_id=agent_id,
            task_id=getattr(result, "task_id", None),
            payload={"ok": getattr(result, "ok", None)},
        )

    async def on_heartbeat(self, *, agent_id: str, result: HeartbeatResult) -> None:
        await _record(
            "task.heartbeat",
            agent_id=agent_id,
            task_id=getattr(result, "task_id", None),
            payload={"ok": getattr(result, "ok", None)},
        )


class ActivityPlanObserver:
    """Observer recording plan broadcasts for the audit feed."""

    async def on_plan_broadcast(
        self,
        *,
        version: int | None,
        plan: dict[str, Any] | None,
        delta: dict[str, Any] | None,
        analytics: TaskAnalytics | None,
    ) -> None:
        _ = plan
        payload: dict[str, Any] = {
            "version": version,
            "delta_keys": sorted(delta.keys()) if delta else [],
        }
        if analytics is not None:
            try:
                payload["analytics"] = {
                    "total_tasks": getattr(analytics, "total_tasks", None),
                    "ready_tasks": getattr(analytics, "ready_tasks", None),
                    "blocked_tasks": getattr(analytics, "blocked_tasks", None),
                }
            except Exception:  # pragma: no cover - guard against unexpected attrs
                payload["analytics"] = {}
        await _record("plan.broadcast", payload=payload)


async def _startup_hook(app) -> None:
    await _record("system.startup", payload={"version": getattr(app, "version", None)})


def register(registry: ExtensionRegistry) -> None:
    """Register the builtin activity feed extension."""

    registry.register_extension(
        ExtensionDescriptor(
            name="builtin.activity_feed",
            version="1.0.0",
            capabilities=("audit", "task_lifecycle", "plan_broadcast"),
            description=(
                "Maintains an in-memory audit feed exposed via "
                "/api/observability/audit-feed."
            ),
        )
    )
    registry.append_contract_note(
        "Activity feed retains up to "
        f"{activity.DEFAULT_LIMIT} events; override via "
        "SWITCHBOARD_ACTIVITY_FEED_SIZE.",
    )
    registry.register_task_hook(ActivityFeedHook())
    registry.register_plan_observer(ActivityPlanObserver())
    registry.register_startup_hook(_startup_hook)
