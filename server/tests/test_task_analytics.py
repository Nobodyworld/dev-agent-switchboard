import pytest

from server.app import create_task, read_task_analytics, update_task
from server.application.factory import build_task_service
from server.db import AsyncSessionLocal
from server.models import TaskDependency
from server.schema import TaskIn, TaskUpdate
from server.task_status import TaskStatus


def _assert_analytics_counts(payload, expected_counts):
    for field, expected in expected_counts.items():
        assert getattr(payload, field) == expected


pytestmark = pytest.mark.asyncio


async def test_task_analytics_captures_status_and_dependency_breakdown():
    async with AsyncSessionLocal() as session:
        service = build_task_service(session)

        root = await create_task(
            TaskIn(title="Root", description="", depends_on=[]),
            service=service,
            session=session,
        )
        ready = await create_task(
            TaskIn(title="Ready", description="", depends_on=[root.id]),
            service=service,
            session=session,
        )
        await create_task(
            TaskIn(title="Blocked", description="", depends_on=[ready.id]),
            service=service,
            session=session,
        )
        await create_task(
            TaskIn(title="Standalone", description="", depends_on=[]),
            service=service,
            session=session,
        )
        in_progress = await create_task(
            TaskIn(title="In Progress", description="", depends_on=[]),
            service=service,
            session=session,
        )
        completed = await create_task(
            TaskIn(title="Completed", description="", depends_on=[]),
            service=service,
            session=session,
        )
        await session.commit()

        await update_task(
            root.id,
            TaskUpdate(status=TaskStatus.COMPLETED),
            service=service,
            session=session,
        )
        await update_task(
            in_progress.id,
            TaskUpdate(status=TaskStatus.IN_PROGRESS),
            service=service,
            session=session,
        )
        await update_task(
            completed.id,
            TaskUpdate(status=TaskStatus.COMPLETED),
            service=service,
            session=session,
        )
        await session.commit()

        analytics = await read_task_analytics(service=service, session=session)

        expected_counts = {
            "total_tasks": 6,
            "pending_tasks": 3,
            "in_progress_tasks": 1,
            "completed_tasks": 2,
            "with_dependencies": 2,
            "without_dependencies": 4,
            "dependency_edges": 2,
            "ready_tasks": 2,
            "blocked_tasks": 1,
            "missing_dependency_tasks": 0,
            "missing_dependency_edges": 0,
        }
        _assert_analytics_counts(analytics, expected_counts)
        expected_average = expected_counts["dependency_edges"] / expected_counts[
            "total_tasks"
        ]
        assert analytics.average_dependencies == pytest.approx(
            expected_average, rel=1e-6
        )


async def test_task_analytics_reports_missing_dependencies():
    async with AsyncSessionLocal() as session:
        service = build_task_service(session)

        parent = await create_task(
            TaskIn(title="Parent", description="", depends_on=[]),
            service=service,
            session=session,
        )
        child = await create_task(
            TaskIn(title="Child", description="", depends_on=[parent.id]),
            service=service,
            session=session,
        )
        await session.commit()

        await update_task(
            parent.id,
            TaskUpdate(status=TaskStatus.COMPLETED),
            service=service,
            session=session,
        )
        # Inject a dangling dependency edge to simulate data drift.
        session.add(TaskDependency(task_id=child.id, depends_on_task_id=9999))
        await session.commit()

        analytics = await read_task_analytics(service=service, session=session)

        expected_counts = {
            "total_tasks": 2,
            "pending_tasks": 1,
            "in_progress_tasks": 0,
            "completed_tasks": 1,
            "with_dependencies": 1,
            "without_dependencies": 1,
            "dependency_edges": 2,
            "ready_tasks": 0,
            "blocked_tasks": 1,
            "missing_dependency_tasks": 1,
            "missing_dependency_edges": 1,
        }
        _assert_analytics_counts(analytics, expected_counts)
        expected_average = expected_counts["dependency_edges"] / expected_counts[
            "total_tasks"
        ]
        assert analytics.average_dependencies == pytest.approx(
            expected_average, rel=1e-6
        )
