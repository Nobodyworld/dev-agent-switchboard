"""In-memory activity feed surfaced through observability endpoints."""

from __future__ import annotations

import asyncio
import os
from collections import deque
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from server.instrumentation.logging import get_request_id, get_trace_id

DEFAULT_LIMIT = 128
_MIN_LIMIT = 16
_MAX_LIMIT = 512


def _determine_limit(raw: str | None) -> int:
    try:
        value = int(raw or DEFAULT_LIMIT)
    except (TypeError, ValueError):
        return DEFAULT_LIMIT
    return max(_MIN_LIMIT, min(_MAX_LIMIT, value))


@dataclass(frozen=True)
class ActivityEvent:
    """Captured lifecycle event entry."""

    kind: str
    occurred_at: datetime
    agent_id: str | None = None
    task_id: int | str | None = None
    payload: Mapping[str, Any] = field(default_factory=dict)
    request_id: str | None = None
    trace_id: str | None = None

    def as_payload(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "occurred_at": self.occurred_at,
            "agent_id": self.agent_id,
            "task_id": self.task_id,
            "payload": dict(self.payload),
            "request_id": self.request_id,
            "trace_id": self.trace_id,
        }


class ActivityFeed:
    """Ring buffer storing recent :class:`ActivityEvent` entries."""

    def __init__(self, limit: int) -> None:
        self._events: deque[ActivityEvent] = deque(maxlen=limit)
        self._lock = asyncio.Lock()

    @property
    def limit(self) -> int:
        return self._events.maxlen or DEFAULT_LIMIT

    async def append(self, event: ActivityEvent) -> None:
        async with self._lock:
            self._events.append(event)

    async def snapshot(self) -> list[ActivityEvent]:
        async with self._lock:
            return list(self._events)


def _initial_limit() -> int:
    return _determine_limit(os.getenv("SWITCHBOARD_ACTIVITY_FEED_SIZE"))


_FEED = ActivityFeed(limit=_initial_limit())


async def record_event(
    kind: str,
    *,
    agent_id: str | None = None,
    task_id: int | str | None = None,
    payload: Mapping[str, Any] | None = None,
) -> None:
    """Append an event to the shared feed."""

    event = ActivityEvent(
        kind=kind,
        occurred_at=datetime.now(timezone.utc),
        agent_id=agent_id,
        task_id=task_id,
        payload=payload or {},
        request_id=get_request_id(),
        trace_id=get_trace_id(),
    )
    await _FEED.append(event)


async def get_activity_feed_snapshot(limit: int | None = None) -> list[dict[str, Any]]:
    """Return recent events as JSON-serialisable payloads."""

    events = await _FEED.snapshot()
    if limit is not None:
        events = events[-limit:]
    return [event.as_payload() for event in events]


def reset_activity_feed(limit: int | None = None) -> None:
    """Reset the global feed. Intended for tests and administrative tooling."""

    global _FEED  # noqa: PLW0603
    effective_limit = limit if limit is not None else _initial_limit()
    effective_limit = max(_MIN_LIMIT, min(_MAX_LIMIT, effective_limit))
    _FEED = ActivityFeed(limit=effective_limit)


__all__ = [
    "ActivityEvent",
    "ActivityFeed",
    "get_activity_feed_snapshot",
    "record_event",
    "reset_activity_feed",
]
