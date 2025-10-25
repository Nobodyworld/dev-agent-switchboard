"""Factory helpers for constructing application-layer services."""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from server.application.system_state_service import SystemStateService
from server.application.task_service import TaskService
from server.domain import LeasePolicy, TaskAvailabilityPolicy
from server.extensions import get_extension_bundle
from server.infrastructure import (
    SqlAlchemyAgentRepository,
    SqlAlchemyLeaseRepository,
    SqlAlchemyPlanVersionRepository,
    SqlAlchemySystemStateRepository,
    SqlAlchemyTaskRepository,
)
from server.settings import get_lease_settings
from server.time_utils import utcnow_naive

__all__ = ["build_system_state_service", "build_task_service"]


def build_task_service(session: AsyncSession) -> TaskService:
    """Return a :class:`TaskService` wired to SQLAlchemy repositories."""

    lease_policy = LeasePolicy(lambda: get_lease_settings().duration_seconds)
    availability = TaskAvailabilityPolicy()
    return TaskService(
        agents=SqlAlchemyAgentRepository(session),
        tasks=SqlAlchemyTaskRepository(session),
        leases=SqlAlchemyLeaseRepository(session),
        plans=SqlAlchemyPlanVersionRepository(session),
        system_state=SqlAlchemySystemStateRepository(session),
        availability_policy=availability,
        lease_policy=lease_policy,
        clock=utcnow_naive,
        extensions=get_extension_bundle(),
    )


def build_system_state_service(session: AsyncSession) -> SystemStateService:
    """Return a :class:`SystemStateService` backed by SQLAlchemy."""

    repository = SqlAlchemySystemStateRepository(session)
    return SystemStateService(repository=repository)
