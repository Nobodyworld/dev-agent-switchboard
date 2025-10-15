import asyncio

import pytest
from starlette.requests import Request

from server.app import checkout, create_task, delete_task, get_plan, put_live_file, register_agent
from server.db import AsyncSessionLocal
from server.schema import AgentIn, TaskIn


async def _fetch_plan_version(session) -> int:
    return (await get_plan(session=session)).version


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
            await create_task(TaskIn(title="task", description="", depends_on=[]), session=session)
            await session.commit()
            after = await _fetch_plan_version(session)
            assert after > before

    asyncio.run(scenario())


def test_plan_version_increases_on_task_update():
    async def scenario():
        async with AsyncSessionLocal() as session:
            await create_task(TaskIn(title="task", description="", depends_on=[]), session=session)
            await session.commit()
            before = await _fetch_plan_version(session)
            await register_agent(AgentIn(agent_name="agent"), session=session)
            await session.commit()
            await asyncio.sleep(1.1)
            await checkout(agent_id="agent", session=session)
            await session.commit()
            after = await _fetch_plan_version(session)
            assert after > before

    asyncio.run(scenario())


@pytest.mark.xfail(reason="Plan version currently decreases after deletions", strict=True)
def test_plan_version_increases_on_task_delete():
    async def scenario():
        async with AsyncSessionLocal() as session:
            created = await create_task(TaskIn(title="task", description="", depends_on=[]), session=session)
            await session.commit()
            before = await _fetch_plan_version(session)
            await delete_task(created.id, session=session)
            await session.commit()
            after = await _fetch_plan_version(session)
            assert after > before

    asyncio.run(scenario())


@pytest.mark.xfail(reason="Plan version does not change when live files are updated", strict=True)
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
