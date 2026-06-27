"""Concurrency guarantees for task checkout."""

from __future__ import annotations

import asyncio
from http import HTTPStatus

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import func, select

from server.app import app
from server.db import AsyncSessionLocal
from server.models import Lease, Task
from server.task_status import TaskStatus

pytestmark = pytest.mark.asyncio


async def _checkout(agent_id: str) -> dict[str, object]:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/api/tasks/checkout",
            params={"agent_id": agent_id},
        )
    assert response.status_code == HTTPStatus.OK
    return response.json()


async def test_concurrent_checkout_issues_exactly_one_lease() -> None:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        for agent_id in ("agent-race-a", "agent-race-b"):
            response = await client.post(
                "/api/agents",
                json={"agent_name": agent_id},
            )
            assert response.status_code == HTTPStatus.OK

        created = await client.post(
            "/api/tasks",
            json={
                "title": "single-owner task",
                "description": "",
                "depends_on": [],
            },
        )
        assert created.status_code == HTTPStatus.OK
        task_id = created.json()["id"]

    results = await asyncio.gather(
        _checkout("agent-race-a"),
        _checkout("agent-race-b"),
    )

    winners = [result for result in results if result["task"] is not None]
    losers = [result for result in results if result["task"] is None]
    assert len(winners) == 1
    assert len(losers) == 1
    assert winners[0]["task"]["id"] == task_id
    assert losers[0]["reason"] == "no_available_tasks"

    async with AsyncSessionLocal() as session:
        lease_count = await session.scalar(
            select(func.count()).select_from(Lease).where(Lease.task_id == task_id)
        )
        task = await session.get(Task, task_id)

    assert lease_count == 1
    assert task is not None
    assert task.status == TaskStatus.IN_PROGRESS
