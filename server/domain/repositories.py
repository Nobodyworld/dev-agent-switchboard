from __future__ import annotations

import datetime as dt
from collections.abc import Iterable, Sequence
from typing import Protocol

from .entities import (
    Agent,
    LeaseRecord,
    PlanVersionSnapshot,
    SystemState,
    TaskAnalytics,
    TaskRecord,
)
from .task_status import TaskStatus


class AgentRepository(Protocol):
    """Persistence abstraction for agent metadata."""

    async def ensure(self, agent: Agent) -> Agent: ...


class TaskRepository(Protocol):
    """Persistence abstraction for tasks and dependency metadata."""

    async def list_candidates(
        self, task_id: int | None = None
    ) -> Sequence[TaskRecord]: ...

    async def get(self, task_id: int) -> TaskRecord | None: ...

    async def claim_pending(self, task_id: int) -> TaskRecord | None:
        """Atomically move a pending task to in progress when still available."""
        ...

    async def save(self, task: TaskRecord) -> TaskRecord: ...

    async def create(
        self,
        *,
        title: str,
        description: str,
        depends_on: Iterable[int] = (),
        priority: int = 0,
    ) -> TaskRecord: ...

    async def update(  # noqa: PLR0913 - protocol mirrors repository override signature
        self,
        task_id: int,
        *,
        title: str | None = None,
        description: str | None = None,
        status: TaskStatus | None = None,
        depends_on: Iterable[int] | None = None,
        completed_notes: str | None = None,
        priority: int | None = None,
    ) -> TaskRecord | None: ...

    async def delete(self, task_id: int) -> bool: ...

    async def dependencies_of(self, task_id: int) -> tuple[int, ...]: ...

    async def dependencies_completed(self, task_id: int) -> bool: ...

    async def existing_ids(self, task_ids: Iterable[int]) -> set[int]: ...

    async def analytics(self) -> TaskAnalytics: ...


class LeaseRepository(Protocol):
    """Persistence abstraction for task leases."""

    async def expire_stale(self, *, now: dt.datetime) -> tuple[int, ...]: ...

    async def for_task(self, task_id: int) -> LeaseRecord | None: ...

    async def save(self, lease: LeaseRecord) -> LeaseRecord: ...

    async def delete(self, task_id: int) -> None: ...


class PlanVersionRepository(Protocol):
    """Persistence abstraction for plan version counters."""

    async def current(self) -> int: ...

    async def increment(self) -> int: ...

    async def snapshot(self) -> PlanVersionSnapshot: ...


class SystemStateRepository(Protocol):
    """Persistence abstraction for global maintenance state."""

    async def get_state(self) -> SystemState: ...

    async def update_state(
        self,
        *,
        maintenance_mode: bool,
        message: str | None,
        expected_version: int | None,
    ) -> SystemState: ...
