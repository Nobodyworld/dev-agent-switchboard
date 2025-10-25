"""Compatibility wrappers around :mod:`server.application.task_service`.

This module preserves the legacy ``server.task_logic`` interface while routing
all behavior through the layered domain/application/infrastructure stack. New
code should import :class:`server.application.TaskService` or
``server.application.build_task_service`` directly. The helpers here emit
``DeprecationWarning`` on use to encourage migrations while keeping existing
callers functional during the transition.
"""

from __future__ import annotations

import warnings
from collections.abc import Iterable
from datetime import datetime
from typing import Any, NamedTuple

from sqlalchemy.ext.asyncio import AsyncSession

from .application import build_task_service
from .domain import Agent, TaskAvailabilityPolicy, TaskRecord
from .infrastructure import (
    SqlAlchemyLeaseRepository,
    SqlAlchemyPlanVersionRepository,
    SqlAlchemyTaskRepository,
)
from .settings import get_lease_settings
from .time_utils import utcnow_naive

__all__ = [
    "PLAN_VERSION_ROW_ID",
    "CheckoutResult",
    "CompleteResult",
    "abandon",
    "checkout_task",
    "complete",
    "current_plan_version",
    "get_dependencies",
    "heartbeat",
    "increment_plan_version",
    "is_available",
    "lease_duration_seconds",
    "plan_version",
    "plan_version_counter",
    "plan_version_snapshot",
    "update_dependencies",
]

_DEPRECATION_MESSAGE = (
    "server.task_logic is deprecated; use server.application.TaskService "
    "and related helpers instead."
)

PLAN_VERSION_ROW_ID = SqlAlchemyPlanVersionRepository.PLAN_VERSION_ROW_ID
_AVAILABILITY_POLICY = TaskAvailabilityPolicy()


class CheckoutResult(NamedTuple):
    """Result wrapper mirroring the historic checkout contract."""

    task: TaskRecord | None
    reason: str | None
    message: str | None = None


class CompleteResult(NamedTuple):
    """Result wrapper mirroring the historic completion contract."""

    ok: bool
    notes: str | None


def _warn() -> None:
    warnings.warn(_DEPRECATION_MESSAGE, DeprecationWarning, stacklevel=2)


def _task_repo(session: AsyncSession) -> SqlAlchemyTaskRepository:
    return SqlAlchemyTaskRepository(session)


def _lease_repo(session: AsyncSession) -> SqlAlchemyLeaseRepository:
    return SqlAlchemyLeaseRepository(session)


def _plan_repo(session: AsyncSession) -> SqlAlchemyPlanVersionRepository:
    return SqlAlchemyPlanVersionRepository(session)


def lease_duration_seconds() -> int:
    """Return the configured task lease duration."""

    _warn()
    return get_lease_settings().duration_seconds


async def get_dependencies(session: AsyncSession, task_id: int) -> list[int]:
    """Return dependency identifiers for ``task_id``."""

    _warn()
    repo = _task_repo(session)
    return list(await repo.dependencies_of(task_id))


async def update_dependencies(
    session: AsyncSession, task_id: int, depends_on: Iterable[int]
) -> None:
    """Replace dependency edges for ``task_id`` with ``depends_on``."""

    _warn()
    repo = _task_repo(session)
    await repo.update(task_id, depends_on=tuple(depends_on))


async def is_available(session: AsyncSession, task: Any) -> bool:
    """Return ``True`` when ``task`` can be checked out."""

    _warn()
    repo = _task_repo(session)
    record = await repo.get(getattr(task, "id", task))
    if record is None:
        return False
    dependencies_completed = await repo.dependencies_completed(record.id)
    lease = await _lease_repo(session).for_task(record.id)
    return _AVAILABILITY_POLICY.is_available(
        record,
        dependencies_completed=dependencies_completed,
        lease=lease,
        now=utcnow_naive(),
    )


async def checkout_task(
    session: AsyncSession, agent_id: str, task_id: int | None = None
) -> CheckoutResult:
    """Return the next available task for ``agent_id``."""

    _warn()
    service = build_task_service(session)
    result = await service.checkout(Agent(agent_id=agent_id), task_id=task_id)
    if result.task is None:
        return CheckoutResult(task=None, reason=result.reason, message=result.message)
    return CheckoutResult(task=result.task, reason=None, message=None)


async def heartbeat(session: AsyncSession, agent_id: str, task_id: int) -> bool:
    """Extend the lease for ``task_id`` if held by ``agent_id``."""

    _warn()
    service = build_task_service(session)
    result = await service.heartbeat(agent_id, task_id)
    return result.ok


async def complete(
    session: AsyncSession,
    agent_id: str,
    task_id: int,
    notes: str | None = None,
) -> CompleteResult:
    """Mark ``task_id`` complete if permitted by the lease policy."""

    _warn()
    service = build_task_service(session)
    result = await service.complete(agent_id, task_id, notes=notes)
    return CompleteResult(ok=result.ok, notes=result.notes)


async def abandon(session: AsyncSession, agent_id: str, task_id: int) -> bool:
    """Release the lease for ``task_id`` when policy permits."""

    _warn()
    service = build_task_service(session)
    result = await service.abandon(agent_id, task_id)
    return result.ok


async def plan_version(session: AsyncSession) -> int:
    """Return the current plan version."""

    return await current_plan_version(session)


async def current_plan_version(session: AsyncSession) -> int:
    """Return the current plan version without mutation."""

    _warn()
    repo = _plan_repo(session)
    return await repo.current()


async def plan_version_snapshot(session: AsyncSession) -> tuple[int, datetime]:
    """Return the plan version and last updated timestamp."""

    _warn()
    repo = _plan_repo(session)
    snapshot = await repo.snapshot()
    return snapshot.value, snapshot.updated_at


async def increment_plan_version(session: AsyncSession) -> int:
    """Increment the plan version and return the new value."""

    _warn()
    repo = _plan_repo(session)
    return await repo.increment()


def plan_version_counter(session: AsyncSession):
    """Compatibility alias for :func:`current_plan_version`."""

    _warn()
    return current_plan_version(session)
