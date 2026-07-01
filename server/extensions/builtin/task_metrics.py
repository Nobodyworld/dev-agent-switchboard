"""Builtin extension that records Prometheus counters for task lifecycle events."""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import TYPE_CHECKING, Protocol, Self, cast

from server.extensions.interfaces import ExtensionDescriptor, ExtensionRegistry

LOGGER = logging.getLogger(__name__)

if TYPE_CHECKING:  # pragma: no cover - imported for typing only
    from server.domain import (
        Agent,
        CheckoutResult,
        CompletionResult,
        HeartbeatResult,
        TaskRecord,
    )


class CounterLike(Protocol):
    """Protocol describing the subset of Prometheus counter APIs we exercise."""

    def labels(self, **labels: str) -> Self: ...

    def inc(self) -> None: ...


CounterFactory = Callable[[str, str, tuple[str, ...]], CounterLike]
Counter: CounterFactory | None

try:  # pragma: no cover - optional dependency may be absent in minimal installs
    from prometheus_client import Counter as _ImportedCounter
except Exception:  # pragma: no cover - dependency handled gracefully
    Counter = None
    _COUNTER_FACTORY: CounterFactory | None = None
else:
    Counter = cast(CounterFactory, _ImportedCounter)
    _COUNTER_FACTORY = Counter


_CHECKOUT_COUNTER: CounterLike | None = None
_COMPLETION_COUNTER: CounterLike | None = None
_HEARTBEAT_COUNTER: CounterLike | None = None
_MUTATION_COUNTER: CounterLike | None = None

if _COUNTER_FACTORY is not None:  # pragma: no branch - defined during module import
    _CHECKOUT_COUNTER = _COUNTER_FACTORY(
        "switchboard_task_checkout_total",
        "Number of task checkout attempts grouped by outcome.",
        ("outcome",),
    )
    _COMPLETION_COUNTER = _COUNTER_FACTORY(
        "switchboard_task_completion_total",
        "Number of task completion attempts grouped by outcome.",
        ("outcome",),
    )
    _HEARTBEAT_COUNTER = _COUNTER_FACTORY(
        "switchboard_task_heartbeat_total",
        "Number of heartbeat/abandon requests grouped by outcome.",
        ("event", "outcome"),
    )
    _MUTATION_COUNTER = _COUNTER_FACTORY(
        "switchboard_task_mutation_total",
        "Number of task creation/update calls grouped by action.",
        ("action",),
    )


class TaskMetricsHook:
    """Hook implementation that records Prometheus counters."""

    async def on_checkout(
        self,
        *,
        agent: Agent,
        result: CheckoutResult,
    ) -> None:  # pragma: no cover - exercised via tests
        if _CHECKOUT_COUNTER is None:
            return
        _ = agent
        outcome = (
            "granted"
            if result.task is not None
            else f"skipped:{result.reason or 'unknown'}"
        )
        _CHECKOUT_COUNTER.labels(outcome=outcome).inc()

    async def on_complete(
        self,
        *,
        agent_id: str,
        result: CompletionResult,
    ) -> None:  # pragma: no cover - exercised via tests
        if _COMPLETION_COUNTER is None:
            return
        _ = agent_id
        outcome = "completed" if result.ok else "rejected"
        _COMPLETION_COUNTER.labels(outcome=outcome).inc()

    async def on_heartbeat(
        self,
        *,
        agent_id: str,
        result: HeartbeatResult,
    ) -> None:  # pragma: no cover - exercised via tests
        if _HEARTBEAT_COUNTER is None:
            return
        _ = agent_id
        event = "heartbeat"
        outcome = "accepted" if result.ok else "rejected"
        _HEARTBEAT_COUNTER.labels(event=event, outcome=outcome).inc()

    async def on_abandon(
        self,
        *,
        agent_id: str,
        result: HeartbeatResult,
    ) -> None:  # pragma: no cover - exercised via tests
        if _HEARTBEAT_COUNTER is None:
            return
        _ = agent_id
        outcome = "accepted" if result.ok else "rejected"
        _HEARTBEAT_COUNTER.labels(event="abandon", outcome=outcome).inc()

    async def on_task_created(
        self,
        *,
        task: TaskRecord,
    ) -> None:  # pragma: no cover - exercised via tests
        if _MUTATION_COUNTER is None:
            return
        _ = task
        _MUTATION_COUNTER.labels(action="create").inc()

    async def on_task_updated(
        self,
        *,
        task: TaskRecord,
    ) -> None:  # pragma: no cover - exercised via tests
        if _MUTATION_COUNTER is None:
            return
        _ = task
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
    if _COUNTER_FACTORY is None:
        LOGGER.warning(
            "Prometheus client library unavailable; builtin task metrics "
            "extension is inactive",
        )
        return
    registry.register_task_hook(TaskMetricsHook())
