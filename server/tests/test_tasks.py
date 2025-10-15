import asyncio

from sqlalchemy import select

from server.app import checkout, create_task, delete_task, health, register_agent
from server.db import AsyncSessionLocal
from server.models import Task, TaskDependency
from server.schema import AgentIn, TaskIn


def test_health():
    assert asyncio.run(health()) == "OK"


def test_create_and_checkout():
    async def scenario():
        async with AsyncSessionLocal() as session:
            first = await create_task(TaskIn(title="t1", description="a", depends_on=[]), session=session)
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

    asyncio.run(scenario())


def test_delete_prerequisite_cleans_dependencies():
    async def scenario():
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
            assert remaining_task.status == "pending"

            outbound_deps = (
                await session.execute(
                    select(TaskDependency).where(TaskDependency.task_id == dependent.id)
                )
            ).scalars().all()
            assert outbound_deps == []

            inbound_deps = (
                await session.execute(
                    select(TaskDependency).where(
                        TaskDependency.depends_on_task_id == prerequisite.id
                    )
                )
            ).scalars().all()
            assert inbound_deps == []

    asyncio.run(scenario())
