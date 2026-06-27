import datetime as dt
from http import HTTPStatus

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete, select

from server.app import app
from server.db import AsyncSessionLocal
from server.models import Agent, Lease, Task, TaskDependency
from server.task_status import TaskStatus

pytestmark = pytest.mark.asyncio


async def _reset_database() -> None:
    async with AsyncSessionLocal() as session:
        await session.execute(delete(TaskDependency))
        await session.execute(delete(Lease))
        await session.execute(delete(Task))
        await session.execute(delete(Agent))
        await session.commit()


async def _get_lease(task_id: int) -> Lease | None:
    async with AsyncSessionLocal() as session:
        result = await session.execute(select(Lease).where(Lease.task_id == task_id))
        return result.scalar_one_or_none()


async def _force_expire(task_id: int) -> None:
    async with AsyncSessionLocal() as session:
        result = await session.execute(select(Lease).where(Lease.task_id == task_id))
        lease = result.scalar_one()
        lease.expires_at = dt.datetime.now(dt.timezone.utc).replace(
            tzinfo=None
        ) - dt.timedelta(seconds=1)
        await session.merge(lease)
        await session.commit()


async def _get_task(task_id: int) -> Task | None:
    async with AsyncSessionLocal() as session:
        return await session.get(Task, task_id)


async def register_agent(client: AsyncClient, agent_name: str) -> None:
    response = await client.post("/api/agents", json={"agent_name": agent_name})
    assert response.status_code == HTTPStatus.OK
    assert response.json()["ok"] is True


async def create_task(client: AsyncClient, title: str) -> int:
    response = await client.post(
        "/api/tasks", json={"title": title, "description": "", "depends_on": []}
    )
    assert response.status_code == HTTPStatus.OK
    return response.json()["id"]


def _client() -> AsyncClient:
    transport = ASGITransport(app=app)
    return AsyncClient(transport=transport, base_url="http://test")


async def test_checkout_heartbeat_expiry_and_recheckout():
    await _reset_database()
    try:
        async with _client() as client:
            await register_agent(client, "alpha")
            await register_agent(client, "beta")
            task_id = await create_task(client, "lifecycle")

            checkout = await client.post(
                "/api/tasks/checkout", params={"agent_id": "alpha"}
            )
            assert checkout.status_code == HTTPStatus.OK
            data = checkout.json()
            assert data["task"]["id"] == task_id

            lease_before = await _get_lease(task_id)
            assert lease_before is not None

            wrong_agent_heartbeat = await client.post(
                f"/api/tasks/{task_id}/heartbeat", params={"agent_id": "beta"}
            )
            assert wrong_agent_heartbeat.status_code == HTTPStatus.OK
            assert wrong_agent_heartbeat.json() == {"ok": False}

            heartbeat = await client.post(
                f"/api/tasks/{task_id}/heartbeat", params={"agent_id": "alpha"}
            )
            assert heartbeat.status_code == HTTPStatus.OK
            assert heartbeat.json() == {"ok": True}

            lease_after = await _get_lease(task_id)
            assert lease_after is not None
            assert lease_after.expires_at > lease_before.expires_at

            await _force_expire(task_id)

            expired_heartbeat = await client.post(
                f"/api/tasks/{task_id}/heartbeat", params={"agent_id": "alpha"}
            )
            assert expired_heartbeat.status_code == HTTPStatus.OK
            assert expired_heartbeat.json() == {"ok": False}

            recheckout = await client.post(
                "/api/tasks/checkout", params={"agent_id": "beta"}
            )
            assert recheckout.status_code == HTTPStatus.OK
            recheckout_data = recheckout.json()
            assert recheckout_data["task"]["id"] == task_id
    finally:
        await _reset_database()


async def test_abandon_releases_task_to_other_agent():
    await _reset_database()
    try:
        async with _client() as client:
            await register_agent(client, "alpha")
            await register_agent(client, "beta")
            task_id = await create_task(client, "abandonable")

            first_checkout = await client.post(
                "/api/tasks/checkout", params={"agent_id": "alpha"}
            )
            assert first_checkout.status_code == HTTPStatus.OK
            assert first_checkout.json()["task"]["id"] == task_id

            unavailable = await client.post(
                "/api/tasks/checkout", params={"agent_id": "beta"}
            )
            assert unavailable.status_code == HTTPStatus.OK
            assert unavailable.json()["task"] is None
            assert unavailable.json()["reason"] == "no_available_tasks"

            wrong_agent_abandon = await client.post(
                f"/api/tasks/{task_id}/abandon", params={"agent_id": "beta"}
            )
            assert wrong_agent_abandon.status_code == HTTPStatus.OK
            assert wrong_agent_abandon.json() == {"ok": False}

            abandon = await client.post(
                f"/api/tasks/{task_id}/abandon", params={"agent_id": "alpha"}
            )
            assert abandon.status_code == HTTPStatus.OK
            assert abandon.json() == {"ok": True}

            task_after_abandon = await _get_task(task_id)
            assert task_after_abandon is not None
            assert task_after_abandon.status == TaskStatus.PENDING

            second_checkout = await client.post(
                "/api/tasks/checkout", params={"agent_id": "beta"}
            )
            assert second_checkout.status_code == HTTPStatus.OK
            assert second_checkout.json()["task"]["id"] == task_id
    finally:
        await _reset_database()


async def test_completion_with_and_without_active_lease():
    await _reset_database()
    try:
        async with _client() as client:
            await register_agent(client, "alpha")
            await register_agent(client, "beta")

            no_lease_task = await create_task(client, "complete without lease")
            without_lease = await client.post(
                f"/api/tasks/{no_lease_task}/complete",
                params={"agent_id": "alpha"},
                json={"notes": "finishing without lease"},
            )
            assert without_lease.status_code == HTTPStatus.OK
            assert without_lease.json()["ok"] is True
            assert without_lease.json()["notes"] == "finishing without lease"

            task_record = await _get_task(no_lease_task)
            assert task_record is not None
            assert task_record.status == TaskStatus.COMPLETED
            assert task_record.completed_notes == "finishing without lease"

            task_list = await client.get("/api/tasks")
            assert task_list.status_code == HTTPStatus.OK
            noted_task = next(t for t in task_list.json() if t["id"] == no_lease_task)
            assert noted_task["completed_notes"] == "finishing without lease"

            with_lease_task = await create_task(client, "lease completion")

            checkout = await client.post(
                "/api/tasks/checkout", params={"agent_id": "alpha"}
            )
            assert checkout.status_code == HTTPStatus.OK
            assert checkout.json()["task"]["id"] == with_lease_task

            lease = await _get_lease(with_lease_task)
            assert lease is not None
            assert lease.agent_id == "alpha"

            wrong_agent_complete = await client.post(
                f"/api/tasks/{with_lease_task}/complete",
                params={"agent_id": "beta"},
                json={"notes": "should fail"},
            )
            assert wrong_agent_complete.status_code == HTTPStatus.OK
            assert wrong_agent_complete.json()["ok"] is False

            correct_agent_complete = await client.post(
                f"/api/tasks/{with_lease_task}/complete",
                params={"agent_id": "alpha"},
                json={"notes": "done"},
            )
            assert correct_agent_complete.status_code == HTTPStatus.OK
            assert correct_agent_complete.json()["ok"] is True
            assert correct_agent_complete.json()["notes"] == "done"

            final_lease = await _get_lease(with_lease_task)
            assert final_lease is None

            final_task = await _get_task(with_lease_task)
            assert final_task is not None
            assert final_task.status == TaskStatus.COMPLETED
            assert final_task.completed_notes == "done"
    finally:
        await _reset_database()
