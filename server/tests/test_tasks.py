from http import HTTPStatus

import pytest
from fastapi import HTTPException
from sqlalchemy import select

from server.app import (
    checkout,
    create_task,
    delete_task,
    health,
    list_tasks,
    mutate_system_state,
    read_system_state,
    register_agent,
    update_task,
)
from server.db import AsyncSessionLocal
from server.models import Task, TaskDependency
from server.schema import (
    AgentIn,
    CheckoutFailureReason,
    SystemStateUpdateIn,
    TaskIn,
    TaskUpdate,
)
from server.task_status import TaskStatus

pytestmark = pytest.mark.asyncio


async def test_health() -> None:
    assert await health() == "OK"


async def test_create_and_checkout() -> None:
    async with AsyncSessionLocal() as session:
        first = await create_task(
            TaskIn(title="t1", description="a", depends_on=[]), session=session
        )
        await create_task(
            TaskIn(title="t2", description="b", depends_on=[first.id]),
            session=session,
        )
        await session.commit()

        await register_agent(AgentIn(agent_name="bot1"), session=session)
        await session.commit()

        checkout_result = await checkout(agent_id="bot1", session=session)
        assert checkout_result.task is not None
        assert checkout_result.task.id == first.id


async def test_targeted_checkout_respects_availability() -> None:
    async with AsyncSessionLocal() as session:
        first = await create_task(
            TaskIn(title="t1", description="a", depends_on=[]),
            session=session,
        )
        second = await create_task(
            TaskIn(title="t2", description="b", depends_on=[first.id]),
            session=session,
        )
        await session.commit()

        await register_agent(AgentIn(agent_name="admin"), session=session)
        await session.commit()

        unavailable = await checkout(
            agent_id="admin", task_id=second.id, session=session
        )
        assert unavailable.task is None
        assert unavailable.reason == CheckoutFailureReason.TASK_NOT_AVAILABLE

        first_checkout = await checkout(
            agent_id="admin", task_id=first.id, session=session
        )
        assert first_checkout.task is not None
        assert first_checkout.task.id == first.id


async def test_delete_prerequisite_cleans_dependencies() -> None:
    async with AsyncSessionLocal() as session:
        prerequisite = await create_task(
            TaskIn(title="prep", description="", depends_on=[]),
            session=session,
        )
        dependent = await create_task(
            TaskIn(title="follow", description="", depends_on=[prerequisite.id]),
            session=session,
        )
        await session.commit()

        await delete_task(prerequisite.id, session=session)
        await session.commit()

        remaining_task = (
            await session.execute(select(Task).where(Task.id == dependent.id))
        ).scalar_one()
        assert remaining_task.status == TaskStatus.PENDING

        outbound_deps = (
            (
                await session.execute(
                    select(TaskDependency).where(
                        TaskDependency.task_id == dependent.id
                    )
                )
            )
            .scalars()
            .all()
        )
        assert outbound_deps == []

        inbound_deps = (
            (
                await session.execute(
                    select(TaskDependency).where(
                        TaskDependency.depends_on_task_id == prerequisite.id
                    )
                )
            )
            .scalars()
            .all()
        )
        assert inbound_deps == []


async def test_create_task_rejects_missing_dependencies() -> None:
    async with AsyncSessionLocal() as session:
        with pytest.raises(HTTPException) as exc_info:
            await create_task(
                TaskIn(title="orphan", description="", depends_on=[9999]),
                session=session,
            )
        assert exc_info.value.status_code == HTTPStatus.BAD_REQUEST
        assert exc_info.value.detail == {"missing_dependencies": [9999]}


async def test_create_task_deduplicates_dependencies() -> None:
    async with AsyncSessionLocal() as session:
        base = await create_task(
            TaskIn(title="base", description="", depends_on=[]),
            session=session,
        )
        dependent = await create_task(
            TaskIn(
                title="dependent",
                description="",
                depends_on=[base.id, base.id],
            ),
            session=session,
        )
        await session.commit()

        deps = (
            (
                await session.execute(
                    select(TaskDependency.depends_on_task_id).where(
                        TaskDependency.task_id == dependent.id
                    )
                )
            )
            .scalars()
            .all()
        )
        assert deps == [base.id]


async def test_list_tasks_filters_by_status() -> None:
    async with AsyncSessionLocal() as session:
        pending = await create_task(
            TaskIn(title="pending", description="", depends_on=[]),
            session=session,
        )
        completed = await create_task(
            TaskIn(title="done", description="", depends_on=[]),
            session=session,
        )
        await update_task(
            completed.id,
            TaskUpdate(status=TaskStatus.COMPLETED),
            session=session,
        )

        pending_only = await list_tasks(status=TaskStatus.PENDING, session=session)
        completed_only = await list_tasks(
            status=TaskStatus.COMPLETED, session=session
        )

        assert {task.id for task in pending_only} == {pending.id}
        assert {task.id for task in completed_only} == {completed.id}


async def test_system_state_endpoints_toggle_and_detect_conflicts() -> None:
    async with AsyncSessionLocal() as session:
        initial = await read_system_state(session=session)
        assert initial.maintenance_mode is False

        updated = await mutate_system_state(
            SystemStateUpdateIn(maintenance_mode=True, message=""),
            session=session,
        )
        assert updated.maintenance_mode is True
        assert isinstance(updated.version, int)

        latest = await read_system_state(session=session)
        assert latest.maintenance_mode is True

        await register_agent(AgentIn(agent_name="maintenance-bot"), session=session)
        checkout_result = await checkout(agent_id="maintenance-bot", session=session)
        assert checkout_result.reason == CheckoutFailureReason.MAINTENANCE_MODE
        assert checkout_result.message is None

        with pytest.raises(HTTPException) as exc_info:
            await mutate_system_state(
                SystemStateUpdateIn(
                    maintenance_mode=False,
                    message="",
                    expected_version=updated.version - 1 if updated.version else 0,
                ),
                session=session,
            )
        assert exc_info.value.status_code == HTTPStatus.CONFLICT
