from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from typing import Callable

from .entities import LeaseRecord, TaskRecord
from .task_status import TaskStatus


@dataclass(frozen=True, slots=True)
class TaskAvailabilityPolicy:
    """Evaluate whether a task can be checked out by an agent."""

    def is_available(
        self,
        task: TaskRecord,
        *,
        dependencies_completed: bool,
        lease: LeaseRecord | None,
        now: dt.datetime,
    ) -> bool:
        if task.status != TaskStatus.PENDING:
            return False
        if not dependencies_completed:
            return False
        return not (lease is not None and lease.expires_at > now)


@dataclass(frozen=True, slots=True)
class LeasePolicy:
    """Policies for issuing and validating task leases."""

    lease_duration_seconds: Callable[[], int]

    def issued_at(self, *, now: dt.datetime) -> dt.datetime:
        return now

    def deadline(self, *, now: dt.datetime) -> dt.datetime:
        return now + dt.timedelta(seconds=self.lease_duration_seconds())

    def can_heartbeat(self, lease: LeaseRecord | None, agent_id: str) -> bool:
        return lease is not None and lease.agent_id == agent_id

    def can_complete(
        self, lease: LeaseRecord | None, agent_id: str, *, now: dt.datetime
    ) -> bool:
        if lease is None:
            return True
        if lease.agent_id == agent_id:
            return True
        return lease.expires_at <= now

    def can_abandon(
        self, lease: LeaseRecord | None, agent_id: str, *, now: dt.datetime
    ) -> bool:
        if lease is None:
            return True
        if lease.agent_id == agent_id:
            return True
        return lease.expires_at <= now

    def refresh(self, lease: LeaseRecord, *, now: dt.datetime) -> LeaseRecord:
        return lease.refresh(expires_at=self.deadline(now=now))

    def new_lease(
        self, task_id: int, agent_id: str, *, now: dt.datetime
    ) -> LeaseRecord:
        return LeaseRecord(
            task_id=task_id,
            agent_id=agent_id,
            issued_at=self.issued_at(now=now),
            expires_at=self.deadline(now=now),
        )
