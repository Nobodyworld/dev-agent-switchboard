import asyncio
import datetime as dt
from http import HTTPStatus

import pytest
from fastapi import HTTPException
from sqlalchemy import select

from server.application.factory import build_task_service
from server.app import create_task, update_task
from server.db import AsyncSessionLocal
from server.models import Lease, Task, TaskDependency
from server.schema import TaskIn, TaskUpdate
from server.task_status import TaskStatus
from server.time_utils import utcnow_naive


def test_update_task_successful_edit_and_dependency_replacement():
    async def scenario():
        async with AsyncSessionLocal() as session:
            service = build_task_service(session)
            first_dep = await create_task(
                TaskIn(title="prep", description="", depends_on=[]),
                service=service,
                session=session,
            )
            original = await create_task(
                TaskIn(title="initial", description="", depends_on=[first_dep.id]),
                service=service,
                session=session,
            )
            second_dep = await create_task(
                TaskIn(title="follow", description="", depends_on=[]),
                service=service,
                session=session,
            )
            await session.commit()

            before_version = await service.plan_version()

            result = await update_task(
                original.id,
                TaskUpdate(
                    title="updated",
                    description="new description",
                    depends_on=[second_dep.id],
                ),
                service=service,
                session=session,
            )

            assert result.title == "updated"
            assert result.description == "new description"
            assert result.depends_on == [second_dep.id]

            after_version = await service.plan_version()
            assert after_version == before_version + 1

            deps = (
                (
                    await session.execute(
                        select(TaskDependency.depends_on_task_id).where(
                            TaskDependency.task_id == original.id
                        )
                    )
                )
                .scalars()
                .all()
            )
            assert deps == [second_dep.id]

    asyncio.run(scenario())


def test_update_task_missing_dependency_validation():
    async def scenario():
        async with AsyncSessionLocal() as session:
            service = build_task_service(session)
            task = await create_task(
                TaskIn(title="needs", description="", depends_on=[]),
                service=service,
                session=session,
            )
            await session.commit()

            with pytest.raises(HTTPException) as exc:
                await update_task(
                    task.id,
                    TaskUpdate(depends_on=[9999]),
                    service=service,
                    session=session,
                )
            assert exc.value.status_code == HTTPStatus.BAD_REQUEST

            await session.rollback()

    asyncio.run(scenario())


def test_update_task_self_dependency_validation():
    async def scenario():
        async with AsyncSessionLocal() as session:
            service = build_task_service(session)
            task = await create_task(
                TaskIn(title="solo", description="", depends_on=[]),
                service=service,
                session=session,
            )
            await session.commit()

            with pytest.raises(HTTPException) as exc:
                await update_task(
                    task.id,
                    TaskUpdate(depends_on=[task.id]),
                    service=service,
                    session=session,
                )
            assert exc.value.status_code == HTTPStatus.BAD_REQUEST

            await session.rollback()

    asyncio.run(scenario())


def test_update_task_status_resetting_leases_to_pending():
    async def scenario():
        async with AsyncSessionLocal() as session:
            service = build_task_service(session)
            created = await create_task(
                TaskIn(title="leased", description="", depends_on=[]),
                service=service,
                session=session,
            )
            await session.commit()

            task = await session.get(Task, created.id)
            assert task is not None
            task.status = TaskStatus.IN_PROGRESS
            await session.flush()

            session.add(
                Lease(
                    task_id=task.id,
                    agent_id="agent-a",
                    expires_at=utcnow_naive() + dt.timedelta(minutes=5),
                )
            )
            await session.commit()

            result = await update_task(
                task.id,
                TaskUpdate(status=TaskStatus.PENDING),
                service=service,
                session=session,
            )

            assert result.status == TaskStatus.PENDING
            leases = (
                (await session.execute(select(Lease).where(Lease.task_id == task.id)))
                .scalars()
                .all()
            )
            assert leases == []

    asyncio.run(scenario())


def test_update_task_status_resetting_leases_to_completed():
    async def scenario():
        async with AsyncSessionLocal() as session:
            service = build_task_service(session)
            created = await create_task(
                TaskIn(title="finishing", description="", depends_on=[]),
                service=service,
                session=session,
            )
            await session.commit()

            task = await session.get(Task, created.id)
            assert task is not None
            task.status = TaskStatus.IN_PROGRESS
            await session.flush()

            session.add(
                Lease(
                    task_id=task.id,
                    agent_id="agent-b",
                    expires_at=utcnow_naive() + dt.timedelta(minutes=5),
                )
            )
            await session.commit()

            result = await update_task(
                task.id,
                TaskUpdate(status=TaskStatus.COMPLETED),
                session=session,
            )

            assert result.status == TaskStatus.COMPLETED
            leases = (
                (await session.execute(select(Lease).where(Lease.task_id == task.id)))
                .scalars()
                .all()
            )
            assert leases == []

    asyncio.run(scenario())
