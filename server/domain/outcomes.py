from __future__ import annotations

from dataclasses import dataclass

from .entities import LeaseRecord, TaskRecord


@dataclass(frozen=True, slots=True)
class CheckoutResult:
    """Result emitted when attempting to checkout a task."""

    task: TaskRecord | None
    lease: LeaseRecord | None
    reason: str | None = None


@dataclass(frozen=True, slots=True)
class CompletionResult:
    """Result emitted when attempting to complete a task."""

    ok: bool
    task: TaskRecord | None
    notes: str | None


@dataclass(frozen=True, slots=True)
class HeartbeatResult:
    """Result emitted when mutating a lease."""

    ok: bool
    task_id: int
