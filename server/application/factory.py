"""Factory helpers for constructing application-layer services."""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from ..domain import LeasePolicy, TaskAvailabilityPolicy
from ..infrastructure import (
    SqlAlchemyAgentRepository,
    SqlAlchemyLeaseRepository,
    SqlAlchemyPlanVersionRepository,
    SqlAlchemyTaskRepository,
)
from ..settings import get_lease_settings
from ..time_utils import utcnow_naive
from .task_service import TaskService

__all__ = ["build_task_service"]


def build_task_service(session: AsyncSession) -> TaskService:
    """Return a :class:`TaskService` wired to SQLAlchemy repositories."""

    lease_policy = LeasePolicy(lambda: get_lease_settings().duration_seconds)
    availability = TaskAvailabilityPolicy()
    return TaskService(
        agents=SqlAlchemyAgentRepository(session),
        tasks=SqlAlchemyTaskRepository(session),
        leases=SqlAlchemyLeaseRepository(session),
        plans=SqlAlchemyPlanVersionRepository(session),
        availability_policy=availability,
        lease_policy=lease_policy,
        clock=utcnow_naive,
    )
