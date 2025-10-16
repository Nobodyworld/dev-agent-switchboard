import asyncio

import pytest
from fastapi import HTTPException
from sqlalchemy import select

from server.app import create_task, update_task
from server.db import AsyncSessionLocal
from server.models import TaskDependency
from server.schema import TaskIn, TaskUpdate
from server.task_logic import plan_version


def test_update_task_successful_edit_and_dependency_replacement():
    async def scenario():
        async with AsyncSessionLocal() as session:
            first_dep = await create_task(
                TaskIn(title="prep", description="", depends_on=[]),
                session=session,
            )
            original = await create_task(
                TaskIn(title="initial", description="", depends_on=[first_dep.id]),
                session=session,
            )
            second_dep = await create_task(
                TaskIn(title="follow", description="", depends_on=[]),
                session=session,
            )
            await session.commit()

            before_version = await plan_version(session)

            result = await update_task(
                original.id,
                TaskUpdate(
                    title="updated",
                    description="new description",
                    depends_on=[second_dep.id],
                ),
                session=session,
            )

            assert result.title == "updated"
            assert result.description == "new description"
            assert result.depends_on == [second_dep.id]

            after_version = await plan_version(session)
            assert after_version == before_version + 1

            deps = (
                await session.execute(
                    select(TaskDependency.depends_on_task_id).where(
                        TaskDependency.task_id == original.id
                    )
                )
            ).scalars().all()
            assert deps == [second_dep.id]

    asyncio.run(scenario())


def test_update_task_missing_dependency_validation():
    async def scenario():
        async with AsyncSessionLocal() as session:
            task = await create_task(
                TaskIn(title="needs", description="", depends_on=[]),
                session=session,
            )
            await session.commit()

            with pytest.raises(HTTPException) as exc:
                await update_task(
                    task.id,
                    TaskUpdate(depends_on=[9999]),
                    session=session,
                )
            assert exc.value.status_code == 400

            await session.rollback()

    asyncio.run(scenario())


def test_update_task_self_dependency_validation():
    async def scenario():
        async with AsyncSessionLocal() as session:
            task = await create_task(
                TaskIn(title="solo", description="", depends_on=[]),
                session=session,
            )
            await session.commit()

            with pytest.raises(HTTPException) as exc:
                await update_task(
                    task.id,
                    TaskUpdate(depends_on=[task.id]),
                    session=session,
                )
            assert exc.value.status_code == 400

            await session.rollback()

    asyncio.run(scenario())
