import asyncio
import datetime as dt

import pytest
from fastapi.testclient import TestClient

# TODO - Port these integration tests to async clients so we exercise the real middleware stack end-to-end.
from sqlalchemy import delete, select

from server.app import app
from server.db import AsyncSessionLocal
from server.models import Agent, Lease, Task, TaskDependency

client = TestClient(app)


async def _reset_database():
    async with AsyncSessionLocal() as session:
        await session.execute(delete(TaskDependency))
        await session.execute(delete(Lease))
        await session.execute(delete(Task))
        await session.execute(delete(Agent))
        await session.commit()


def run_async(coro):
    return asyncio.run(coro)


@pytest.fixture(autouse=True)
def clean_database():
    run_async(_reset_database())
    yield
    run_async(_reset_database())


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


def register_agent(agent_name: str) -> None:
    response = client.post("/api/agents", json={"agent_name": agent_name})
    assert response.status_code == 200
    assert response.json()["ok"] is True


def create_task(title: str) -> int:
    response = client.post(
        "/api/tasks", json={"title": title, "description": "", "depends_on": []}
    )
    assert response.status_code == 200
    return response.json()["id"]


def test_checkout_heartbeat_expiry_and_recheckout():
    register_agent("alpha")
    register_agent("beta")
    task_id = create_task("lifecycle")

    checkout = client.post("/api/tasks/checkout", params={"agent_id": "alpha"})
    assert checkout.status_code == 200
    data = checkout.json()
    assert data["task"]["id"] == task_id

    lease_before = run_async(_get_lease(task_id))
    assert lease_before is not None

    heartbeat = client.post(
        f"/api/tasks/{task_id}/heartbeat", params={"agent_id": "alpha"}
    )
    assert heartbeat.status_code == 200
    assert heartbeat.json() == {"ok": True}

    lease_after = run_async(_get_lease(task_id))
    assert lease_after is not None
    assert lease_after.expires_at > lease_before.expires_at

    run_async(_force_expire(task_id))

    recheckout = client.post("/api/tasks/checkout", params={"agent_id": "beta"})
    assert recheckout.status_code == 200
    recheckout_data = recheckout.json()
    assert recheckout_data["task"]["id"] == task_id


def test_abandon_releases_task_to_other_agent():
    register_agent("alpha")
    register_agent("beta")
    task_id = create_task("abandonable")

    first_checkout = client.post("/api/tasks/checkout", params={"agent_id": "alpha"})
    assert first_checkout.status_code == 200
    assert first_checkout.json()["task"]["id"] == task_id

    unavailable = client.post("/api/tasks/checkout", params={"agent_id": "beta"})
    assert unavailable.status_code == 200
    assert unavailable.json()["task"] is None
    assert unavailable.json()["reason"] == "no_available_tasks"

    abandon = client.post(f"/api/tasks/{task_id}/abandon", params={"agent_id": "alpha"})
    assert abandon.status_code == 200
    assert abandon.json() == {"ok": True}

    task_after_abandon = run_async(_get_task(task_id))
    assert task_after_abandon is not None
    assert task_after_abandon.status == "pending"

    second_checkout = client.post("/api/tasks/checkout", params={"agent_id": "beta"})
    assert second_checkout.status_code == 200
    assert second_checkout.json()["task"]["id"] == task_id


def test_completion_with_and_without_active_lease():
    register_agent("alpha")
    register_agent("beta")

    no_lease_task = create_task("complete without lease")
    without_lease = client.post(
        f"/api/tasks/{no_lease_task}/complete",
        params={"agent_id": "alpha"},
        json={"notes": "finishing without lease"},
    )
    assert without_lease.status_code == 200
    assert without_lease.json()["ok"] is True
    assert without_lease.json()["notes"] == "finishing without lease"

    task_record = run_async(_get_task(no_lease_task))
    assert task_record is not None
    assert task_record.status == "completed"
    assert task_record.completed_notes == "finishing without lease"

    task_list = client.get("/api/tasks")
    assert task_list.status_code == 200
    noted_task = next(t for t in task_list.json() if t["id"] == no_lease_task)
    assert noted_task["completed_notes"] == "finishing without lease"

    with_lease_task = create_task("lease completion")

    checkout = client.post("/api/tasks/checkout", params={"agent_id": "alpha"})
    assert checkout.status_code == 200
    assert checkout.json()["task"]["id"] == with_lease_task

    lease = run_async(_get_lease(with_lease_task))
    assert lease is not None
    assert lease.agent_id == "alpha"

    wrong_agent_complete = client.post(
        f"/api/tasks/{with_lease_task}/complete",
        params={"agent_id": "beta"},
        json={"notes": "should fail"},
    )
    assert wrong_agent_complete.status_code == 200
    assert wrong_agent_complete.json()["ok"] is False

    correct_agent_complete = client.post(
        f"/api/tasks/{with_lease_task}/complete",
        params={"agent_id": "alpha"},
        json={"notes": "done"},
    )
    assert correct_agent_complete.status_code == 200
    assert correct_agent_complete.json()["ok"] is True
    assert correct_agent_complete.json()["notes"] == "done"

    final_lease = run_async(_get_lease(with_lease_task))
    assert final_lease is None

    final_task = run_async(_get_task(with_lease_task))
    assert final_task is not None
    assert final_task.status == "completed"
    assert final_task.completed_notes == "done"
