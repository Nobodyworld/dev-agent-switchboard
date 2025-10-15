import asyncio

from server.app import checkout, create_task, health, register_agent
from server.db import AsyncSessionLocal
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
