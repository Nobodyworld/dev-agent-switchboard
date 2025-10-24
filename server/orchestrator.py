"""High-level orchestration helpers bridging HTTP routes and task logic."""

from __future__ import annotations

import datetime as dt

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .interfaces import (
    AgentDescriptor,
    CheckoutOutcome,
    CompletionOutcome,
    HeartbeatOutcome,
    QueueDescriptor,
    TaskEnvelope,
    TaskLease,
    TaskPayload,
)
from .models import Agent, Lease, Task
from .task_logic import (
    CheckoutResult,
    CompleteResult,
    abandon as abandon_task,
    checkout_task as checkout_task_logic,
    complete as complete_task_logic,
    get_dependencies,
    heartbeat as heartbeat_logic,
)
from .task_status import TaskStatus

__all__ = [
    "DEFAULT_QUEUE",
    "abandon",
    "checkout",
    "complete",
    "ensure_agent",
    "heartbeat",
]

DEFAULT_QUEUE = QueueDescriptor(
    name="default",
    kind="task",
    metadata={"version": "v1"},
)


async def ensure_agent(session: AsyncSession, descriptor: AgentDescriptor) -> AgentDescriptor:
    """Persist a new agent if necessary and return the descriptor.

    Parameters
    ----------
    session:
        Database session used for persistence.
    descriptor:
        Agent metadata submitted by the caller.

    Returns
    -------
    AgentDescriptor
        Normalized agent descriptor suitable for downstream operations.
    """

    exists = (
        await session.execute(select(Agent).where(Agent.agent_id == descriptor.agent_id))
    ).scalar_one_or_none()
    if exists is None:
        session.add(Agent(agent_id=descriptor.agent_id))
        await session.flush()
    return descriptor


async def checkout(
    session: AsyncSession,
    descriptor: AgentDescriptor,
    *,
    task_id: int | None = None,
) -> CheckoutOutcome:
    """Return the next available task envelope for ``descriptor``.

    Parameters
    ----------
    session:
        Active database session used to query tasks and leases.
    descriptor:
        Agent information for which checkout should occur.
    task_id:
        Optional explicit task identifier to request.

    Returns
    -------
    CheckoutOutcome
        Envelope describing the leased task or the reason checkout failed.
    """

    result: CheckoutResult = await checkout_task_logic(
        session, agent_id=descriptor.agent_id, task_id=task_id
    )
    if result.task is None:
        return CheckoutOutcome(envelope=None, reason=result.reason)
    envelope = await _build_envelope(session, result.task)
    return CheckoutOutcome(envelope=envelope, reason=None)


async def heartbeat(
    session: AsyncSession,
    descriptor: AgentDescriptor,
    task_id: int,
) -> HeartbeatOutcome:
    """Extend the lease for ``task_id`` if owned by ``descriptor``.

    Parameters
    ----------
    session:
        Database session used to update the lease.
    descriptor:
        Agent attempting to renew the lease.
    task_id:
        Identifier of the task targeted by the heartbeat.

    Returns
    -------
    HeartbeatOutcome
        Outcome containing the operation status.
    """

    ok = await heartbeat_logic(session, agent_id=descriptor.agent_id, task_id=task_id)
    return HeartbeatOutcome(ok=ok, task_id=task_id)


async def complete(
    session: AsyncSession,
    descriptor: AgentDescriptor,
    task_id: int,
    *,
    notes: str | None = None,
) -> CompletionOutcome:
    """Mark ``task_id`` as complete if the lease permits it.

    Parameters
    ----------
    session:
        Database session used to persist the lifecycle transition.
    descriptor:
        Agent requesting completion.
    task_id:
        Identifier of the task being completed.
    notes:
        Optional completion notes supplied by the agent.

    Returns
    -------
    CompletionOutcome
        Outcome describing success, stored notes, and refreshed envelope.
    """

    result: CompleteResult = await complete_task_logic(
        session, agent_id=descriptor.agent_id, task_id=task_id, notes=notes
    )
    envelope: TaskEnvelope | None = None
    if result.ok:
        task = await session.get(Task, task_id)
        if task is not None:
            envelope = await _build_envelope(session, task)
    return CompletionOutcome(ok=result.ok, notes=result.notes, envelope=envelope)


async def abandon(
    session: AsyncSession,
    descriptor: AgentDescriptor,
    task_id: int,
) -> HeartbeatOutcome:
    """Release an active lease and revert a task to ``pending``.

    Parameters
    ----------
    session:
        Database session used to release the lease.
    descriptor:
        Agent relinquishing the lease.
    task_id:
        Identifier of the task that should be released.

    Returns
    -------
    HeartbeatOutcome
        Outcome describing whether the abandonment succeeded.
    """

    ok = await abandon_task(session, agent_id=descriptor.agent_id, task_id=task_id)
    return HeartbeatOutcome(ok=ok, task_id=task_id)


async def _build_envelope(session: AsyncSession, task: Task) -> TaskEnvelope:
    """Construct a :class:`TaskEnvelope` with the current lease state.

    Parameters
    ----------
    session:
        Database session used to fetch lease metadata.
    task:
        ORM task instance to convert.

    Returns
    -------
    TaskEnvelope
        Structured representation combining payload, queue, and lease info.
    """

    payload = await _build_payload(session, task)
    lease_row = (
        await session.execute(select(Lease).where(Lease.task_id == task.id))
    ).scalar_one_or_none()
    lease: TaskLease | None = None
    if lease_row is not None:
        issued_at = lease_row.created_at or dt.datetime.utcnow()
        lease = TaskLease(
            task_id=lease_row.task_id,
            agent_id=lease_row.agent_id,
            issued_at=issued_at,
            expires_at=lease_row.expires_at,
        )
    return TaskEnvelope(task=payload, queue=DEFAULT_QUEUE, lease=lease)


async def _build_payload(session: AsyncSession, task: Task) -> TaskPayload:
    """Create a normalized :class:`TaskPayload` from an ORM instance.

    Parameters
    ----------
    session:
        Database session used to load dependency edges.
    task:
        ORM task model slated for serialization.

    Returns
    -------
    TaskPayload
        Immutable payload ready for API transport.
    """

    dependencies = await get_dependencies(session, task.id)
    metadata: dict[str, object] = {}
    if task.completed_notes:
        metadata["completed_notes"] = task.completed_notes
    if task.updated_at:
        metadata["updated_at"] = task.updated_at.isoformat()
    return TaskPayload(
        id=task.id,
        title=task.title,
        description=task.description,
        status=task.status if isinstance(task.status, TaskStatus) else TaskStatus(task.status),
        depends_on=tuple(sorted(dependencies)),
        metadata=metadata or None,
    )
