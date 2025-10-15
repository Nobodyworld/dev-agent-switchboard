
import datetime as dt
from typing import List, Tuple, Optional
from sqlalchemy import select, delete, update
from sqlalchemy.ext.asyncio import AsyncSession
from .models import Task, TaskDependency, Lease
LEASE_SECONDS = 300

async def get_dependencies(session: AsyncSession, task_id: int) -> List[int]:
    rows = (await session.execute(select(TaskDependency.depends_on_task_id).where(TaskDependency.task_id == task_id))).all()
    return [r[0] for r in rows]

async def is_available(session: AsyncSession, task: Task) -> bool:
    if task.status == "completed":
        return False
    # Dependencies must be completed
    deps = await get_dependencies(session, task.id)
    if deps:
        rows = (await session.execute(select(Task.id, Task.status).where(Task.id.in_(deps)))).all()
        if any(r[1] != "completed" for r in rows):
            return False
    # No active lease
    lease = (await session.execute(select(Lease).where(Lease.task_id == task.id))).scalar_one_or_none()
    if lease and lease.expires_at > dt.datetime.utcnow():
        return False
    return True

async def checkout_task(session: AsyncSession, agent_id: str) -> Tuple[Optional[Task], Optional[str]]:
    # expire old leases
    await session.execute(delete(Lease).where(Lease.expires_at < dt.datetime.utcnow()))
    # find available task
    tasks = (await session.execute(select(Task).order_by(Task.id))).scalars().all()
    for t in tasks:
        if await is_available(session, t):
            # set status and lease
            t.status = "in_progress"
            expires = dt.datetime.utcnow() + dt.timedelta(seconds=LEASE_SECONDS)
            await session.merge(t)
            await session.flush()
            await session.execute(delete(Lease).where(Lease.task_id == t.id))
            session.add(Lease(task_id=t.id, agent_id=agent_id, expires_at=expires))
            await session.flush()
            return t, None
    return None, "no_available_tasks"

async def heartbeat(session: AsyncSession, agent_id: str, task_id: int) -> bool:
    lease = (await session.execute(select(Lease).where(Lease.task_id == task_id))).scalar_one_or_none()
    if lease is None or lease.agent_id != agent_id:
        return False
    lease.expires_at = dt.datetime.utcnow() + dt.timedelta(seconds=LEASE_SECONDS)
    await session.merge(lease)
    return True

async def complete(session: AsyncSession, agent_id: str, task_id: int) -> bool:
    lease = (await session.execute(select(Lease).where(Lease.task_id == task_id))).scalar_one_or_none()
    task = (await session.execute(select(Task).where(Task.id == task_id))).scalar_one_or_none()
    if task is None:
        return False
    # allow completion if no conflicting lease (expired or owned)
    if lease and lease.agent_id != agent_id and lease.expires_at > dt.datetime.utcnow():
        return False
    task.status = "completed"
    await session.merge(task)
    await session.execute(delete(Lease).where(Lease.task_id == task_id))
    return True

async def abandon(session: AsyncSession, agent_id: str, task_id: int) -> bool:
    lease = (await session.execute(select(Lease).where(Lease.task_id == task_id))).scalar_one_or_none()
    task = (await session.execute(select(Task).where(Task.id == task_id))).scalar_one_or_none()
    if task is None:
        return False
    if lease and lease.agent_id != agent_id and lease.expires_at > dt.datetime.utcnow():
        return False
    task.status = "pending"
    await session.merge(task)
    await session.execute(delete(Lease).where(Lease.task_id == task_id))
    return True

async def plan_version(session: AsyncSession) -> int:
    # simple version: sum of task updated_at timestamps
    res = (await session.execute(select(Task.updated_at))).all()
    total = sum(int(r[0].timestamp()) for r in res) if res else 0
    return total
