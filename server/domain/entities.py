from __future__ import annotations

import datetime as dt
from collections.abc import Mapping
from dataclasses import dataclass, replace

from .task_status import TaskStatus


@dataclass(frozen=True, slots=True)
class Agent:
    """Description of an agent interacting with Switchboard."""

    agent_id: str
    label: str | None = None
    capabilities: tuple[str, ...] = ()
    metadata: Mapping[str, str] | None = None

    def normalized(self) -> Agent:
        """Return a copy with tuple-backed attributes normalized."""

        return replace(self, capabilities=tuple(self.capabilities))


@dataclass(frozen=True, slots=True)
class TaskRecord:
    """Domain representation of a task with dependency metadata."""

    id: int
    title: str
    description: str
    status: TaskStatus
    depends_on: tuple[int, ...] = ()
    completed_notes: str | None = None
    updated_at: dt.datetime | None = None

    def with_status(
        self, status: TaskStatus, *, completed_notes: str | None = None
    ) -> TaskRecord:
        """Return a copy of the task with an updated status and notes."""

        return replace(self, status=status, completed_notes=completed_notes)


@dataclass(frozen=True, slots=True)
class TaskAnalytics:
    """Aggregated statistics describing the current task portfolio."""

    total_tasks: int
    pending_tasks: int
    in_progress_tasks: int
    completed_tasks: int
    ready_tasks: int
    blocked_tasks: int
    with_dependencies: int
    without_dependencies: int
    dependency_edges: int
    missing_dependency_tasks: int
    missing_dependency_edges: int
    average_dependencies: float


@dataclass(frozen=True, slots=True)
class LeaseRecord:
    """Domain representation of an active or historical lease."""

    task_id: int
    agent_id: str
    issued_at: dt.datetime
    expires_at: dt.datetime

    def refresh(self, *, expires_at: dt.datetime) -> LeaseRecord:
        """Return a copy of the lease with an updated expiry timestamp."""

        return replace(self, expires_at=expires_at)


@dataclass(frozen=True, slots=True)
class PlanVersionSnapshot:
    """Immutable view of the plan version counter."""

    value: int
    updated_at: dt.datetime


@dataclass(frozen=True, slots=True)
class SystemState:
    """Global orchestration state flags persisted by the service."""

    maintenance_mode: bool
    message: str | None
    updated_at: dt.datetime
    version: int
