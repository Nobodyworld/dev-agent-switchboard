from __future__ import annotations

import datetime as dt
from collections import defaultdict
from collections.abc import Iterable, Sequence

from sqlalchemy import delete, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..domain.entities import Agent, LeaseRecord, PlanVersionSnapshot, TaskRecord
from ..domain.repositories import (
    AgentRepository,
    LeaseRepository,
    PlanVersionRepository,
    TaskRepository,
)
from ..domain.task_status import TaskStatus
from ..models import Agent as AgentModel, Lease as LeaseModel, PlanVersion, Task, TaskDependency
from ..time_utils import utcnow_naive

__all__ = [
    "SqlAlchemyAgentRepository",
    "SqlAlchemyTaskRepository",
    "SqlAlchemyLeaseRepository",
    "SqlAlchemyPlanVersionRepository",
]


class SqlAlchemyAgentRepository(AgentRepository):
    """Persist agents using SQLAlchemy models."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def ensure(self, agent: Agent) -> Agent:
        exists = (
            await self._session.execute(
                select(AgentModel).where(AgentModel.agent_id == agent.agent_id)
            )
        ).scalar_one_or_none()
        if exists is None:
            self._session.add(AgentModel(agent_id=agent.agent_id))
            await self._session.flush()
        return agent


class SqlAlchemyTaskRepository(TaskRepository):
    """Task persistence adapter backed by SQLAlchemy."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def list_candidates(self, task_id: int | None = None) -> Sequence[TaskRecord]:
        if task_id is not None:
            task = await self._session.get(Task, task_id)
            if task is None:
                return []
            dependency_map = await self._dependency_map((task.id,))
            return [self._to_record(task, dependency_map.get(task.id, ()))]

        result = await self._session.execute(select(Task).order_by(Task.id))
        tasks = result.scalars().all()
        if not tasks:
            return []

        dependency_map = await self._dependency_map(task.id for task in tasks)
        return [
            self._to_record(task, dependency_map.get(task.id, ()))
            for task in tasks
        ]

    async def get(self, task_id: int) -> TaskRecord | None:
        task = await self._session.get(Task, task_id)
        if task is None:
            return None
        dependency_map = await self._dependency_map((task_id,))
        return self._to_record(task, dependency_map.get(task_id, ()))

    async def save(self, task: TaskRecord) -> TaskRecord:
        instance = await self._session.get(Task, task.id)
        if instance is None:
            raise RuntimeError(f"Task {task.id} does not exist")
        instance.title = task.title
        instance.description = task.description
        instance.status = task.status
        instance.completed_notes = task.completed_notes
        await self._session.merge(instance)
        await self._session.flush()
        dependency_map = await self._dependency_map((task.id,))
        return self._to_record(instance, dependency_map.get(task.id, ()))

    async def create(
        self,
        *,
        title: str,
        description: str,
        depends_on: Iterable[int] = (),
    ) -> TaskRecord:
        instance = Task(title=title, description=description)
        self._session.add(instance)
        await self._session.flush()
        normalized = tuple(sorted({dep for dep in depends_on}))
        for dep_id in normalized:
            self._session.add(
                TaskDependency(task_id=instance.id, depends_on_task_id=dep_id)
            )
        await self._session.flush()
        return self._to_record(instance, normalized)

    async def update(
        self,
        task_id: int,
        *,
        title: str | None = None,
        description: str | None = None,
        status: TaskStatus | None = None,
        depends_on: Iterable[int] | None = None,
        completed_notes: str | None = None,
    ) -> TaskRecord | None:
        instance = await self._session.get(Task, task_id)
        if instance is None:
            return None
        if title is not None:
            instance.title = title
        if description is not None:
            instance.description = description
        if status is not None:
            instance.status = status
        if completed_notes is not None or status == TaskStatus.COMPLETED:
            instance.completed_notes = completed_notes
        if depends_on is not None:
            await self._session.execute(
                delete(TaskDependency).where(TaskDependency.task_id == task_id)
            )
            normalized = tuple(sorted({dep for dep in depends_on}))
            for dep_id in normalized:
                self._session.add(
                    TaskDependency(task_id=task_id, depends_on_task_id=dep_id)
                )
        await self._session.merge(instance)
        await self._session.flush()
        dependency_map = await self._dependency_map((task_id,))
        return self._to_record(instance, dependency_map.get(task_id, ()))

    async def delete(self, task_id: int) -> bool:
        await self._session.execute(
            delete(TaskDependency).where(
                or_(
                    TaskDependency.task_id == task_id,
                    TaskDependency.depends_on_task_id == task_id,
                )
            )
        )
        instance = await self._session.get(Task, task_id)
        if instance is None:
            return False
        await self._session.delete(instance)
        await self._session.flush()
        return True

    async def dependencies_of(self, task_id: int) -> tuple[int, ...]:
        dependency_map = await self._dependency_map((task_id,))
        return dependency_map.get(task_id, ())

    async def dependencies_completed(self, task_id: int) -> bool:
        deps = await self.dependencies_of(task_id)
        if not deps:
            return True
        rows = (
            await self._session.execute(select(Task.status).where(Task.id.in_(deps)))
        ).all()
        return all(TaskStatus(row[0]) == TaskStatus.COMPLETED for row in rows)

    async def existing_ids(self, task_ids: Iterable[int]) -> set[int]:
        ids = {task_id for task_id in task_ids}
        if not ids:
            return set()
        rows = (
            await self._session.execute(select(Task.id).where(Task.id.in_(ids)))
        ).all()
        return {row[0] for row in rows}

    def _to_record(self, task: Task, depends_on: Iterable[int] = ()) -> TaskRecord:
        dependencies = tuple(sorted(depends_on))
        updated_at = task.updated_at
        return TaskRecord(
            id=task.id,
            title=task.title,
            description=task.description,
            status=task.status
            if isinstance(task.status, TaskStatus)
            else TaskStatus(task.status),
            depends_on=dependencies,
            completed_notes=task.completed_notes,
            updated_at=updated_at,
        )

    async def _dependency_map(
        self, task_ids: Iterable[int]
    ) -> dict[int, tuple[int, ...]]:
        unique_ids = list(dict.fromkeys(task_ids))
        if not unique_ids:
            return {}

        rows = (
            await self._session.execute(
                select(
                    TaskDependency.task_id,
                    TaskDependency.depends_on_task_id,
                ).where(TaskDependency.task_id.in_(unique_ids))
            )
        ).all()

        collected: dict[int, set[int]] = defaultdict(set)
        for task_id, depends_on in rows:
            collected[task_id].add(depends_on)

        return {
            task_id: tuple(sorted(collected.get(task_id, ())))
            for task_id in unique_ids
        }


class SqlAlchemyLeaseRepository(LeaseRepository):
    """Lease persistence implemented with SQLAlchemy."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def expire_stale(self, *, now: dt.datetime) -> None:
        await self._session.execute(delete(LeaseModel).where(LeaseModel.expires_at < now))

    async def for_task(self, task_id: int) -> LeaseRecord | None:
        row = (
            await self._session.execute(
                select(LeaseModel).where(LeaseModel.task_id == task_id)
            )
        ).scalar_one_or_none()
        if row is None:
            return None
        issued_at = row.created_at or utcnow_naive()
        return LeaseRecord(
            task_id=row.task_id,
            agent_id=row.agent_id,
            issued_at=issued_at,
            expires_at=row.expires_at,
        )

    async def save(self, lease: LeaseRecord) -> LeaseRecord:
        existing = (
            await self._session.execute(
                select(LeaseModel).where(LeaseModel.task_id == lease.task_id)
            )
        ).scalar_one_or_none()
        if existing is None:
            model = LeaseModel(
                task_id=lease.task_id,
                agent_id=lease.agent_id,
                expires_at=lease.expires_at,
            )
            self._session.add(model)
        else:
            existing.agent_id = lease.agent_id
            existing.expires_at = lease.expires_at
            model = existing
        await self._session.flush()
        issued_at = model.created_at or utcnow_naive()
        return LeaseRecord(
            task_id=model.task_id,
            agent_id=model.agent_id,
            issued_at=issued_at,
            expires_at=model.expires_at,
        )

    async def delete(self, task_id: int) -> None:
        await self._session.execute(delete(LeaseModel).where(LeaseModel.task_id == task_id))


class SqlAlchemyPlanVersionRepository(PlanVersionRepository):
    """Plan version persistence implemented with SQLAlchemy."""

    PLAN_VERSION_ROW_ID = 1

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def current(self) -> int:
        row = await self._ensure_row()
        return row.value

    async def increment(self) -> int:
        await self._ensure_row()
        row = (
            await self._session.execute(
                select(PlanVersion)
                .where(PlanVersion.id == self.PLAN_VERSION_ROW_ID)
                .with_for_update()
            )
        ).scalar_one()
        row.value += 1
        await self._session.flush()
        return row.value

    async def snapshot(self) -> PlanVersionSnapshot:
        row = await self._ensure_row()
        if row.updated_at is None:
            await self._session.flush()
            await self._session.refresh(row)
        assert row.updated_at is not None
        return PlanVersionSnapshot(value=row.value, updated_at=row.updated_at)

    async def _ensure_row(self) -> PlanVersion:
        row = await self._session.get(PlanVersion, self.PLAN_VERSION_ROW_ID)
        if row is None:
            row = PlanVersion(id=self.PLAN_VERSION_ROW_ID, value=0)
            self._session.add(row)
            await self._session.flush()
        return row
