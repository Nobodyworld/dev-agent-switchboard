"""Exercise the application-layer :class:`TaskService` end to end."""

import asyncio

from sqlalchemy import select

from server.application.factory import build_task_service
from server.db import AsyncSessionLocal
from server.domain import Agent
from server.models import Lease, Task
from server.task_status import TaskStatus


def test_checkout_skips_blocked_tasks_until_dependencies_complete() -> None:
    async def scenario() -> None:
        async with AsyncSessionLocal() as session:
            service = build_task_service(session)

            root = await service.create_task(
                title="bootstrap", description="", depends_on=()
            )
            blocked = await service.create_task(
                title="blocked", description="", depends_on=(root.id,)
            )
            await service.update_task(root.id, status=TaskStatus.IN_PROGRESS)
            await session.commit()

            first = await service.checkout(Agent(agent_id="agent-a"))
            assert first.task is None
            assert first.reason == "no_available_tasks"

            await service.update_task(root.id, status=TaskStatus.COMPLETED)
            await session.commit()

            second = await service.checkout(Agent(agent_id="agent-a"))
            assert second.task is not None
            assert second.task.id == blocked.id
            assert second.task.status == TaskStatus.IN_PROGRESS

    asyncio.run(scenario())


def test_checkout_assigns_task_and_persists_lease() -> None:
    async def scenario() -> None:
        async with AsyncSessionLocal() as session:
            service = build_task_service(session)
            task = await service.create_task(
                title="available", description="", depends_on=()
            )
            await session.commit()

            result = await service.checkout(Agent(agent_id="agent-b"))

            assert result.task is not None
            assert result.task.id == task.id
            assert result.task.status == TaskStatus.IN_PROGRESS
            assert result.lease is not None
            assert result.lease.agent_id == "agent-b"

            lease_row = (
                await session.execute(select(Lease).where(Lease.task_id == task.id))
            ).scalar_one()
            assert lease_row.agent_id == "agent-b"

    asyncio.run(scenario())


def test_complete_releases_lease_and_records_notes() -> None:
    async def scenario() -> None:
        async with AsyncSessionLocal() as session:
            service = build_task_service(session)
            task = await service.create_task(
                title="done", description="", depends_on=()
            )
            await session.commit()

            checkout = await service.checkout(Agent(agent_id="agent-c"))
            assert checkout.task is not None

            result = await service.complete("agent-c", checkout.task.id, notes="ok")
            assert result.ok is True
            assert result.task is not None
            assert result.task.status == TaskStatus.COMPLETED
            assert result.notes == "ok"

            lease_count = (
                await session.execute(select(Lease).where(Lease.task_id == task.id))
            ).scalars().all()
            assert lease_count == []

            persisted = await session.get(Task, task.id)
            assert persisted is not None
            assert persisted.status == TaskStatus.COMPLETED
            assert persisted.completed_notes == "ok"

    asyncio.run(scenario())


def test_abandon_returns_task_to_pending_and_clears_lease() -> None:
    async def scenario() -> None:
        async with AsyncSessionLocal() as session:
            service = build_task_service(session)
            task = await service.create_task(
                title="abandon", description="", depends_on=()
            )
            await session.commit()

            checkout = await service.checkout(Agent(agent_id="agent-d"))
            assert checkout.task is not None

            response = await service.abandon("agent-d", checkout.task.id)
            assert response.ok is True

            lease_rows = (
                await session.execute(select(Lease).where(Lease.task_id == task.id))
            ).scalars().all()
            assert lease_rows == []

            persisted = await session.get(Task, task.id)
            assert persisted is not None
            assert persisted.status == TaskStatus.PENDING

    asyncio.run(scenario())
