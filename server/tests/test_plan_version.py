import asyncio

from starlette.requests import Request

from server.app import (
    abandon,
    checkout,
    complete,
    create_task,
    delete_task,
    get_plan,
    put_live_file,
    register_agent,
)
from server.db import AsyncSessionLocal
from server.schema import AgentIn, CompleteIn, TaskIn


async def _fetch_plan_version(session) -> int:
    return (await get_plan(session=session)).version


async def _fetch_plan(session):
    return await get_plan(session=session)


def _make_request(body: bytes) -> Request:
    payload = body

    async def receive() -> dict:
        nonlocal payload
        if payload is None:
            return {"type": "http.request", "body": b"", "more_body": False}
        chunk = payload
        payload = None
        return {"type": "http.request", "body": chunk, "more_body": False}

    scope = {
        "type": "http",
        "method": "PUT",
        "path": "/api/files/test.txt",
        "headers": [],
        "query_string": b"",
        "scheme": "http",
        "client": ("test", 1234),
        "server": ("testserver", 80),
    }
    return Request(scope, receive)


def test_plan_version_increases_on_task_create():
    async def scenario():
        async with AsyncSessionLocal() as session:
            before = await _fetch_plan_version(session)
            await create_task(
                TaskIn(title="task", description="", depends_on=[]), session=session
            )
            await session.commit()
            after = await _fetch_plan_version(session)
            assert after > before

    asyncio.run(scenario())


def test_plan_version_increases_on_task_update():
    async def scenario():
        async with AsyncSessionLocal() as session:
            await create_task(
                TaskIn(title="task", description="", depends_on=[]), session=session
            )
            await session.commit()
            before = await _fetch_plan_version(session)
            await register_agent(AgentIn(agent_name="agent"), session=session)
            await session.commit()
            await checkout(agent_id="agent", session=session)
            await session.commit()
            after = await _fetch_plan_version(session)
            assert after > before

    asyncio.run(scenario())


def test_plan_version_increases_on_task_delete():
    async def scenario():
        async with AsyncSessionLocal() as session:
            created = await create_task(
                TaskIn(title="task", description="", depends_on=[]), session=session
            )
            await session.commit()
            before = await _fetch_plan_version(session)
            await delete_task(created.id, session=session)
            await session.commit()
            after = await _fetch_plan_version(session)
            assert after > before

    asyncio.run(scenario())


def test_plan_version_increases_on_live_file_put():
    async def scenario():
        async with AsyncSessionLocal() as session:
            before = await _fetch_plan_version(session)
            request = _make_request(b"hello")
            await put_live_file("docs/test.txt", request=request, session=session)
            await session.commit()
            after = await _fetch_plan_version(session)
            assert after > before

    asyncio.run(scenario())


def test_plan_version_increases_on_repeated_task_updates():
    async def scenario():
        async with AsyncSessionLocal() as session:
            await create_task(
                TaskIn(title="task", description="", depends_on=[]),
                session=session,
            )
            await session.commit()

            await register_agent(AgentIn(agent_name="agent"), session=session)
            await session.commit()

            base_version = await _fetch_plan_version(session)

            checkout_result = await checkout(agent_id="agent", session=session)
            await session.commit()
            after_checkout = await _fetch_plan_version(session)
            assert after_checkout > base_version

            assert checkout_result.task is not None
            await abandon(
                task_id=checkout_result.task.id, agent_id="agent", session=session
            )
            await session.commit()
            after_abandon = await _fetch_plan_version(session)
            assert after_abandon > after_checkout

    asyncio.run(scenario())


def test_plan_metadata_includes_timestamp():
    async def scenario():
        async with AsyncSessionLocal() as session:
            plan = await _fetch_plan(session)
            assert plan.updated_at is not None
            before = plan.updated_at

            await create_task(
                TaskIn(title="another", description="", depends_on=[]),
                session=session,
            )
            await session.commit()

            after_plan = await _fetch_plan(session)
            assert after_plan.updated_at >= before
            assert after_plan.version >= plan.version

    asyncio.run(scenario())


def test_plan_returns_completion_notes():
    async def scenario():
        async with AsyncSessionLocal() as session:
            created = await create_task(
                TaskIn(title="task", description="", depends_on=[]),
                session=session,
            )
            await session.commit()

            await register_agent(AgentIn(agent_name="agent"), session=session)
            await session.commit()

            await checkout(agent_id="agent", session=session)
            await session.commit()

            await complete(
                task_id=created.id,
                agent_id="agent",
                body=CompleteIn(notes="documented"),
                session=session,
            )
            await session.commit()

            plan = await get_plan(session=session)
            noted_task = next(t for t in plan.tasks if t.id == created.id)
            assert noted_task.completed_notes == "documented"

    asyncio.run(scenario())
