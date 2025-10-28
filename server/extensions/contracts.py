"""Stable dataclasses describing extension hook contexts."""

from __future__ import annotations

import dataclasses
import datetime as dt
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any


def _utc_now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def _maybe_getattr(obj: Any, name: str) -> Any:
    if obj is None:
        return None
    return getattr(obj, name, None)


@dataclass(frozen=True, slots=True)
class TaskHookContext:
    """Envelope describing a task lifecycle hook invocation."""

    event: str
    payload: Mapping[str, Any]
    generated_at: dt.datetime = field(default_factory=_utc_now)

    @property
    def agent_id(self) -> str | None:
        """Return the agent identifier associated with the event, if any."""

        if "agent_id" in self.payload:
            candidate = self.payload["agent_id"]
            if isinstance(candidate, str):
                return candidate
        agent = self.payload.get("agent")
        candidate = _maybe_getattr(agent, "agent_id")
        if isinstance(candidate, str):
            return candidate
        result = self.payload.get("result")
        candidate = _maybe_getattr(result, "agent_id")
        if isinstance(candidate, str):
            return candidate
        return None

    @property
    def task_id(self) -> int | None:
        """Return the task identifier associated with the event, if any."""

        if "task_id" in self.payload:
            candidate = self.payload["task_id"]
            if isinstance(candidate, int):
                return candidate
        task = self.payload.get("task")
        candidate = _maybe_getattr(task, "id")
        if isinstance(candidate, int):
            return candidate
        result = self.payload.get("result")
        candidate = _maybe_getattr(result, "task_id")
        if isinstance(candidate, int):
            return candidate
        task = _maybe_getattr(result, "task")
        candidate = _maybe_getattr(task, "id")
        if isinstance(candidate, int):
            return candidate
        return None

    def as_payload(self) -> dict[str, Any]:
        """Return a JSON-serialisable representation of the context."""

        return {
            "event": self.event,
            "generated_at": self.generated_at,
            "agent_id": self.agent_id,
            "task_id": self.task_id,
        }


@dataclass(frozen=True, slots=True)
class PlanBroadcastContext:
    """Envelope describing a plan broadcast notification."""

    version: int | None
    plan: Mapping[str, Any] | None
    delta: Mapping[str, Any] | None
    analytics: Any | None
    generated_at: dt.datetime = field(default_factory=_utc_now)

    def analytics_as_dict(self) -> dict[str, Any] | None:
        """Return the analytics payload as a dictionary when possible."""

        if self.analytics is None:
            return None
        if dataclasses.is_dataclass(self.analytics):
            return dataclasses.asdict(self.analytics)
        if isinstance(self.analytics, Mapping):
            return dict(self.analytics)
        return None

    @property
    def ready_tasks(self) -> int | None:
        """Return the ready task count when analytics are available."""

        value = _maybe_getattr(self.analytics, "ready_tasks")
        return int(value) if isinstance(value, int) else None

    @property
    def blocked_tasks(self) -> int | None:
        """Return the blocked task count when analytics are available."""

        value = _maybe_getattr(self.analytics, "blocked_tasks")
        return int(value) if isinstance(value, int) else None

    def as_payload(self) -> dict[str, Any]:
        """Return a JSON-serialisable representation of the context."""

        payload: dict[str, Any] = {
            "version": self.version,
            "generated_at": self.generated_at,
        }
        if self.plan is not None:
            payload["plan_keys"] = sorted(self.plan.keys())
        if self.delta is not None:
            payload["delta_keys"] = sorted(self.delta.keys())
        analytics = self.analytics_as_dict()
        if analytics is not None:
            payload["analytics"] = analytics
        return payload


__all__ = ["PlanBroadcastContext", "TaskHookContext"]
