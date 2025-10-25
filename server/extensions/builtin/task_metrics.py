"""Builtin extension that records Prometheus counters for task lifecycle events."""

from __future__ import annotations

import logging

from server.extensions.interfaces import ExtensionDescriptor, ExtensionRegistry

LOGGER = logging.getLogger(__name__)

try:  # pragma: no cover - optional dependency may be absent in minimal installs
    from prometheus_client import Counter  # type: ignore
except Exception:  # pragma: no cover - dependency handled gracefully
    Counter = None  # type: ignore[assignment]


_CHECKOUT_COUNTER = None
_COMPLETION_COUNTER = None
_HEARTBEAT_COUNTER = None
_MUTATION_COUNTER = None

if Counter is not None:  # pragma: no branch - defined during module import
    _CHECKOUT_COUNTER = Counter(
        "switchboard_task_checkout_total",
        "Number of task checkout attempts grouped by outcome.",
        ("outcome",),
    )
    _COMPLETION_COUNTER = Counter(
        "switchboard_task_completion_total",
        "Number of task completion attempts grouped by outcome.",
        ("outcome",),
    )
    _HEARTBEAT_COUNTER = Counter(
        "switchboard_task_heartbeat_total",
        "Number of heartbeat/abandon requests grouped by outcome.",
        ("event", "outcome"),
    )
    _MUTATION_COUNTER = Counter(
        "switchboard_task_mutation_total",
        "Number of task creation/update calls grouped by action.",
        ("action",),
    )


class TaskMetricsHook:
    """Hook implementation that records Prometheus counters."""

    async def on_checkout(self, *, agent, result) -> None:  # pragma: no cover - exercised via tests
        if _CHECKOUT_COUNTER is None:
            return
        outcome = "granted" if result.task is not None else f"skipped:{result.reason or 'unknown'}"
        _CHECKOUT_COUNTER.labels(outcome=outcome).inc()

    async def on_complete(self, *, agent_id, result) -> None:  # pragma: no cover - exercised via tests
        if _COMPLETION_COUNTER is None:
            return
        outcome = "completed" if result.ok else "rejected"
        _COMPLETION_COUNTER.labels(outcome=outcome).inc()

    async def on_heartbeat(self, *, agent_id, result) -> None:  # pragma: no cover - exercised via tests
        if _HEARTBEAT_COUNTER is None:
            return
        event = "heartbeat"
        outcome = "accepted" if result.ok else "rejected"
        _HEARTBEAT_COUNTER.labels(event=event, outcome=outcome).inc()

    async def on_abandon(self, *, agent_id, result) -> None:  # pragma: no cover - exercised via tests
        if _HEARTBEAT_COUNTER is None:
            return
        _HEARTBEAT_COUNTER.labels(event="abandon", outcome="accepted" if result.ok else "rejected").inc()

    async def on_task_created(self, *, task) -> None:  # pragma: no cover - exercised via tests
        if _MUTATION_COUNTER is None:
            return
        _MUTATION_COUNTER.labels(action="create").inc()

    async def on_task_updated(self, *, task) -> None:  # pragma: no cover - exercised via tests
        if _MUTATION_COUNTER is None:
            return
        _MUTATION_COUNTER.labels(action="update").inc()


def register(registry: ExtensionRegistry) -> None:
    """Register the builtin metrics hook with ``registry``."""

    registry.register_extension(
        ExtensionDescriptor(
            name="builtin.task_metrics",
            version="1.0.0",
            capabilities=("metrics", "task_lifecycle"),
            description="Records Prometheus counters for task lifecycle events.",
        )
    )
    if Counter is None:
        LOGGER.warning(
            "Prometheus client library unavailable; builtin task metrics extension is inactive"
        )
        return
    registry.register_task_hook(TaskMetricsHook())
