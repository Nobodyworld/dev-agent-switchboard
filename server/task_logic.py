"""Domain logic shared by the Switchboard FastAPI endpoints."""

from __future__ import annotations

import datetime as dt
from collections.abc import Iterable
from typing import NamedTuple

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from .models import Lease, PlanVersion, Task, TaskDependency
from .settings import get_lease_settings
from .task_status import TaskStatus
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
    "plan_version",
    "plan_version_snapshot",
    "update_dependencies",
    "lease_duration_seconds",
]


class CheckoutResult(NamedTuple):
    """Result wrapper returned by :func:`checkout_task`."""

    task: Task | None
    reason: str | None


class CompleteResult(NamedTuple):
    """Result wrapper returned by :func:`complete`."""

    ok: bool
    notes: str | None

PLAN_VERSION_ROW_ID = 1


def lease_duration_seconds() -> int:
    """Return the configured task lease duration in seconds.

    Returns
    -------
    int
        Number of seconds a lease remains valid without a heartbeat.
    """

    # The settings helper caches results, so repeated lookups are cheap while
    # still allowing tests to override the value via ``reload_lease_settings``.
    return get_lease_settings().duration_seconds


def _lease_deadline(now: dt.datetime | None = None) -> dt.datetime:
    """Return the lease expiration timestamp using the configured window.

    Parameters
    ----------
    now:
        Optional base timestamp; defaults to :func:`utcnow_naive`.

    Returns
    -------
    datetime.datetime
        Calculated expiration time when the lease should lapse.
    """

    base = now or utcnow_naive()
    return base + dt.timedelta(seconds=lease_duration_seconds())


async def get_dependencies(session: AsyncSession, task_id: int) -> list[int]:
    """Return task identifiers that ``task_id`` depends on.

    Parameters
    ----------
    session:
        Database session used to query dependency edges.
    task_id:
        Identifier of the task whose dependencies should be returned.

    Returns
    -------
    list[int]
        Sorted list of dependency task identifiers.
    """

    rows = (
        await session.execute(
            select(TaskDependency.depends_on_task_id).where(
                TaskDependency.task_id == task_id
            )
        )
    ).all()
    return [r[0] for r in rows]


async def update_dependencies(
    session: AsyncSession, task_id: int, depends_on: Iterable[int]
) -> None:
    """Replace the dependency edges for ``task_id`` with ``depends_on`` safely.

    Parameters
    ----------
    session:
        Database session used to mutate dependency edges.
    task_id:
        Identifier of the task being updated.
    depends_on:
        Iterable of dependency identifiers that should replace existing edges.
    """

    await session.execute(
        delete(TaskDependency).where(TaskDependency.task_id == task_id)
    )
    seen: set[int] = set()
    for dep_id in depends_on:
        if dep_id in seen:
            continue
        seen.add(dep_id)
        session.add(TaskDependency(task_id=task_id, depends_on_task_id=dep_id))
    await session.flush()


async def is_available(session: AsyncSession, task: Task) -> bool:
    """Return ``True`` when ``task`` can be checked out for work.

    Parameters
    ----------
    session:
        Database session used to inspect leases and dependencies.
    task:
        Task candidate whose availability should be determined.

    Returns
    -------
    bool
        ``True`` when the task may be leased, ``False`` otherwise.
    """

    if task.status == TaskStatus.COMPLETED:
        return False
    # Dependencies must be completed
    deps = await get_dependencies(session, task.id)
    if deps:
        rows = (
            await session.execute(select(Task.id, Task.status).where(Task.id.in_(deps)))
        ).all()
        if any(r[1] != TaskStatus.COMPLETED for r in rows):
            return False
    # No active lease
    lease = (
        await session.execute(select(Lease).where(Lease.task_id == task.id))
    ).scalar_one_or_none()
    if lease:
        now = utcnow_naive()
        if lease.expires_at > now:
            return False
    return True


async def checkout_task(
    session: AsyncSession,
    agent_id: str,
    task_id: int | None = None,
) -> CheckoutResult:
    """Return the next available task for ``agent_id`` or a failure reason.

    Parameters
    ----------
    session:
        Database session used to query and mutate leases.
    agent_id:
        Identifier of the agent requesting work.
    task_id:
        Optional explicit task identifier to request.

    Returns
    -------
    CheckoutResult
        Named tuple containing the leased task or the failure reason.
    """

    # expire old leases
    now = utcnow_naive()
    await session.execute(delete(Lease).where(Lease.expires_at < now))
    # find available task
    if task_id is not None:
        task = await session.get(Task, task_id)
        if task is None:
            return CheckoutResult(None, "task_not_found")
        tasks = [task]
    else:
        tasks = (await session.execute(select(Task).order_by(Task.id))).scalars().all()
    # TODO - Prioritize tasks using explicit ordering (e.g., status or dependencies)
    # instead of raw iteration.
    for t in tasks:
        if await is_available(session, t):
            # set status and lease
            t.status = TaskStatus.IN_PROGRESS
            expires = _lease_deadline()
            await session.merge(t)
            await session.flush()
            await session.execute(delete(Lease).where(Lease.task_id == t.id))
            session.add(Lease(task_id=t.id, agent_id=agent_id, expires_at=expires))
            await session.flush()
            return CheckoutResult(t, None)
        if task_id is not None:
            return CheckoutResult(None, "task_not_available")
    return CheckoutResult(None, "no_available_tasks")


async def heartbeat(session: AsyncSession, agent_id: str, task_id: int) -> bool:
    """Extend the lease for ``task_id`` if it belongs to ``agent_id``.

    Parameters
    ----------
    session:
        Database session used to update the lease deadline.
    agent_id:
        Identifier of the agent attempting the heartbeat.
    task_id:
        Identifier of the leased task.

    Returns
    -------
    bool
        ``True`` when the lease was renewed, ``False`` otherwise.
    """

    lease = (
        await session.execute(select(Lease).where(Lease.task_id == task_id))
    ).scalar_one_or_none()
    if lease is None or lease.agent_id != agent_id:
        return False
    lease.expires_at = _lease_deadline()
    await session.merge(lease)
    return True


async def complete(
    session: AsyncSession,
    agent_id: str,
    task_id: int,
    notes: str | None = None,
) -> CompleteResult:
    """Mark ``task_id`` complete if ``agent_id`` holds the lease.

    Parameters
    ----------
    session:
        Database session used to persist the lifecycle transition.
    agent_id:
        Identifier of the agent attempting completion.
    task_id:
        Identifier of the task being completed.
    notes:
        Optional completion notes supplied by the agent.

    Returns
    -------
    CompleteResult
        Named tuple describing success and normalized completion notes.
    """
    lease = (
        await session.execute(select(Lease).where(Lease.task_id == task_id))
    ).scalar_one_or_none()
    task = (
        await session.execute(select(Task).where(Task.id == task_id))
    ).scalar_one_or_none()
    if task is None:
        return CompleteResult(False, None)
    # allow completion if no conflicting lease (expired or owned)
    if lease and lease.agent_id != agent_id:
        now = utcnow_naive()
        if lease.expires_at > now:
            return CompleteResult(False, None)
    task.status = TaskStatus.COMPLETED
    normalized_notes = notes if notes else None
    task.completed_notes = normalized_notes
    await session.merge(task)
    await session.execute(delete(Lease).where(Lease.task_id == task_id))
    return CompleteResult(True, task.completed_notes)


async def abandon(session: AsyncSession, agent_id: str, task_id: int) -> bool:
    """Release an active lease and reset the task to ``pending`` if allowed.

    Parameters
    ----------
    session:
        Database session used to clear the lease and reset the task.
    agent_id:
        Identifier of the agent releasing the task.
    task_id:
        Identifier of the task to reset.

    Returns
    -------
    bool
        ``True`` when the task was reset successfully, ``False`` otherwise.
    """

    lease = (
        await session.execute(select(Lease).where(Lease.task_id == task_id))
    ).scalar_one_or_none()
    task = (
        await session.execute(select(Task).where(Task.id == task_id))
    ).scalar_one_or_none()
    if task is None:
        return False
    if lease and lease.agent_id != agent_id:
        now = utcnow_naive()
        if lease.expires_at > now:
            return False
    task.status = TaskStatus.PENDING
    await session.merge(task)
    await session.execute(delete(Lease).where(Lease.task_id == task_id))
    return True


async def plan_version(session: AsyncSession) -> int:
    """Return the current plan version without updating it."""

    return await current_plan_version(session)


async def plan_version_snapshot(session: AsyncSession) -> tuple[int, dt.datetime]:
    """Return the current plan version and last updated timestamp."""

    row = await _ensure_plan_version_row(session)
    # `updated_at` may be None immediately after creation prior to flush;
    # ensure defaults apply.
    if row.updated_at is None:
        await session.flush()
        await session.refresh(row)
    return row.value, row.updated_at


async def _ensure_plan_version_row(session: AsyncSession) -> PlanVersion:
    """Ensure the singleton plan-version row exists and return it."""

    row = await session.get(PlanVersion, PLAN_VERSION_ROW_ID)
    if row is None:
        row = PlanVersion(id=PLAN_VERSION_ROW_ID, value=0)
        session.add(row)
        await session.flush()
    return row


async def increment_plan_version(session: AsyncSession) -> int:
    """Increment and return the plan version."""

    await _ensure_plan_version_row(session)
    row = (
        await session.execute(
            select(PlanVersion)
            .where(PlanVersion.id == PLAN_VERSION_ROW_ID)
            .with_for_update()
        )
    ).scalar_one()
    row.value += 1
    await session.flush()
    return row.value


async def current_plan_version(session: AsyncSession) -> int:
    """Return the current plan version without mutating it."""

    row = await _ensure_plan_version_row(session)
    return row.value


def plan_version_counter(session: AsyncSession):
    return current_plan_version(session)
