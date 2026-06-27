from __future__ import annotations

import datetime as dt
from collections.abc import Callable, Iterable, Mapping, Sequence
from typing import Literal

from server.application.exceptions import (
    MissingDependenciesError,
    SelfDependencyError,
    TaskNotFoundError,
)
from server.domain import (
    Agent,
    CheckoutResult,
    CompletionResult,
    HeartbeatResult,
    LeasePolicy,
    PlanVersionSnapshot,
    TaskAnalytics,
    TaskAvailabilityPolicy,
    TaskRecord,
)
from server.domain.repositories import (
    AgentRepository,
    LeaseRepository,
    PlanVersionRepository,
    SystemStateRepository,
    TaskRepository,
)
from server.domain.task_status import TaskStatus
from server.extensions import ExtensionBundle


class TaskService:
    """Coordinate task lifecycle, plan versions, and dependency management."""

    def __init__(  # noqa: PLR0913 - orchestrator requires repository and policy collaborators
        self,
        *,
        agents: AgentRepository,
        tasks: TaskRepository,
        leases: LeaseRepository,
        plans: PlanVersionRepository,
        system_state: SystemStateRepository | None = None,
        availability_policy: TaskAvailabilityPolicy,
        lease_policy: LeasePolicy,
        clock: Callable[[], dt.datetime],
        extensions: ExtensionBundle | None = None,
    ) -> None:
        self._agents = agents
        self._tasks = tasks
        self._leases = leases
        self._plans = plans
        self._system_state = system_state
        self._availability = availability_policy
        self._lease_policy = lease_policy
        self._clock = clock
        self._extensions = extensions

    async def _notify(self, event: str, **payload) -> None:
        if self._extensions is None:
            return
        await self._extensions.emit(event, **payload)

    async def ensure_agent(self, agent: Agent) -> Agent:
        """Persist the agent if necessary and return the normalized entity."""

        return await self._agents.ensure(agent.normalized())

    async def checkout(
        self, agent: Agent, *, task_id: int | None = None
    ) -> CheckoutResult:
        """Return the next available task for ``agent``."""

        if self._system_state is not None:
            state = await self._system_state.get_state()
            if state.maintenance_mode:
                result = CheckoutResult(
                    task=None,
                    lease=None,
                    reason="maintenance_mode",
                    message=state.message,
                )
                await self._notify("on_checkout", agent=agent, result=result)
                return result
        now = self._clock()
        await self._agents.ensure(agent.normalized())
        expired_ids = await self._leases.expire_stale(now=now)
        for expired_task_id in expired_ids:
            task = await self._tasks.get(expired_task_id)
            if task is not None and task.status != TaskStatus.PENDING:
                await self._tasks.save(task.with_status(TaskStatus.PENDING))
        candidates = await self._tasks.list_candidates(task_id)
        status_lookup: Mapping[int, TaskStatus] | None = None
        if task_id is None:
            status_lookup = {task.id: task.status for task in candidates}

        for task in candidates:
            deps_completed = None
            if status_lookup is not None:
                deps_completed = self._dependencies_completed_from_records(
                    task, status_lookup
                )
            if deps_completed is None:
                deps_completed = await self._tasks.dependencies_completed(task.id)
            lease = await self._leases.for_task(task.id)
            if self._availability.is_available(
                task,
                dependencies_completed=deps_completed,
                lease=lease,
                now=now,
            ):
                saved = await self._tasks.claim_pending(task.id)
                if saved is None:
                    if task_id is not None:
                        break
                    continue
                await self._leases.delete(task.id)
                new_lease = self._lease_policy.new_lease(
                    task_id=task.id, agent_id=agent.agent_id, now=now
                )
                persisted = await self._leases.save(new_lease)
                result = CheckoutResult(task=saved, lease=persisted, reason=None)
                await self._notify("on_checkout", agent=agent, result=result)
                return result
            if task_id is not None:
                break
        reason = "task_not_available" if task_id is not None else "no_available_tasks"
        result = CheckoutResult(task=None, lease=None, reason=reason)
        await self._notify("on_checkout", agent=agent, result=result)
        return result

    async def heartbeat(self, agent_id: str, task_id: int) -> HeartbeatResult:
        """Extend the lease deadline if the agent currently holds it."""

        now = self._clock()
        lease = await self._leases.for_task(task_id)
        if not self._lease_policy.can_heartbeat(lease, agent_id, now=now):
            result = HeartbeatResult(ok=False, task_id=task_id)
            await self._notify("on_heartbeat", agent_id=agent_id, result=result)
            return result
        if lease is None:  # defensive type narrowing; policy rejects this case
            result = HeartbeatResult(ok=False, task_id=task_id)
            await self._notify("on_heartbeat", agent_id=agent_id, result=result)
            return result
        refreshed = self._lease_policy.refresh(lease, now=now)
        await self._leases.save(refreshed)
        result = HeartbeatResult(ok=True, task_id=task_id)
        await self._notify("on_heartbeat", agent_id=agent_id, result=result)
        return result

    async def complete(
        self, agent_id: str, task_id: int, *, notes: str | None = None
    ) -> CompletionResult:
        """Mark the task as completed if permitted by the lease policy."""

        now = self._clock()
        lease = await self._leases.for_task(task_id)
        if not self._lease_policy.can_complete(lease, agent_id, now=now):
            result = CompletionResult(ok=False, task=None, notes=None)
            await self._notify("on_complete", agent_id=agent_id, result=result)
            return result
        task = await self._tasks.get(task_id)
        if task is None:
            result = CompletionResult(ok=False, task=None, notes=None)
            await self._notify("on_complete", agent_id=agent_id, result=result)
            return result
        normalized_notes = notes or None
        saved = await self._tasks.save(
            task.with_status(TaskStatus.COMPLETED, completed_notes=normalized_notes)
        )
        await self._leases.delete(task_id)
        result = CompletionResult(ok=True, task=saved, notes=saved.completed_notes)
        await self._notify("on_complete", agent_id=agent_id, result=result)
        return result

    async def abandon(self, agent_id: str, task_id: int) -> HeartbeatResult:
        """Release a lease and return the task to the pending queue."""

        now = self._clock()
        lease = await self._leases.for_task(task_id)
        if not self._lease_policy.can_abandon(lease, agent_id, now=now):
            result = HeartbeatResult(ok=False, task_id=task_id)
            await self._notify("on_abandon", agent_id=agent_id, result=result)
            return result
        task = await self._tasks.get(task_id)
        if task is None:
            result = HeartbeatResult(ok=False, task_id=task_id)
            await self._notify("on_abandon", agent_id=agent_id, result=result)
            return result
        await self._tasks.save(task.with_status(TaskStatus.PENDING))
        await self._leases.delete(task_id)
        result = HeartbeatResult(ok=True, task_id=task_id)
        await self._notify("on_abandon", agent_id=agent_id, result=result)
        return result

    async def create_task(
        self,
        *,
        title: str,
        description: str,
        depends_on: Iterable[int],
        priority: int = 0,
    ) -> TaskRecord:
        """Create a new task after validating dependency integrity."""

        normalized_deps = self._normalize_dependencies(depends_on)
        await self._ensure_dependencies_exist(normalized_deps)
        task = await self._tasks.create(
            title=title,
            description=description,
            depends_on=normalized_deps,
            priority=priority,
        )
        await self._notify("on_task_created", task=task)
        return task

    async def update_task(  # noqa: PLR0913 - mirrors repository update signature
        self,
        task_id: int,
        *,
        title: str | None = None,
        description: str | None = None,
        status: TaskStatus | None = None,
        depends_on: Iterable[int] | None = None,
        completed_notes: str | None = None,
        priority: int | None = None,
    ) -> TaskRecord:
        """Apply updates to the requested task, validating dependencies."""

        if depends_on is not None and task_id in depends_on:
            raise SelfDependencyError()
        task = await self._tasks.get(task_id)
        if task is None:
            raise TaskNotFoundError()
        normalized_deps = None
        if depends_on is not None:
            normalized_deps = self._normalize_dependencies(depends_on)
            await self._ensure_dependencies_exist(normalized_deps)
        updated = await self._tasks.update(
            task_id,
            title=title,
            description=description,
            status=status,
            depends_on=normalized_deps,
            completed_notes=completed_notes,
            priority=priority,
        )
        if updated is None:
            raise TaskNotFoundError()
        if status in {TaskStatus.PENDING, TaskStatus.COMPLETED}:
            await self._leases.delete(task_id)
        await self._notify("on_task_updated", task=updated)
        return updated

    async def delete_task(self, task_id: int) -> bool:
        """Delete the task and any associated lease."""

        deleted = await self._tasks.delete(task_id)
        await self._leases.delete(task_id)
        return deleted

    async def get_task(self, task_id: int) -> TaskRecord | None:
        """Return the task identified by ``task_id``."""

        return await self._tasks.get(task_id)

    async def list_tasks(
        self, status: TaskStatus | Literal["all"] | None = None
    ) -> Sequence[TaskRecord]:
        """Return tasks ordered by identifier, optionally filtered by status."""

        tasks = await self._tasks.list_candidates(None)
        if status and status != "all":
            return [task for task in tasks if task.status == status]
        return tasks

    async def analytics(self) -> TaskAnalytics:
        """Return aggregated analytics describing task and dependency health."""

        return await self._tasks.analytics()

    async def dependencies_of(self, task_id: int) -> tuple[int, ...]:
        """Return dependency identifiers for the task."""

        return await self._tasks.dependencies_of(task_id)

    async def plan_version(self) -> int:
        """Return the current plan version."""

        return await self._plans.current()

    async def plan_version_snapshot(self) -> PlanVersionSnapshot:
        """Return the plan version and last updated timestamp."""

        return await self._plans.snapshot()

    async def increment_plan_version(self) -> int:
        """Increment and return the plan version."""

        return await self._plans.increment()

    async def _ensure_dependencies_exist(self, depends_on: tuple[int, ...]) -> None:
        if not depends_on:
            return
        existing = await self._tasks.existing_ids(depends_on)
        missing = sorted(set(depends_on) - existing)
        if missing:
            raise MissingDependenciesError(tuple(missing))

    @staticmethod
    def _normalize_dependencies(depends_on: Iterable[int]) -> tuple[int, ...]:
        unique_dependencies = {dep_id for dep_id in depends_on if dep_id is not None}
        return tuple(sorted(unique_dependencies))

    @staticmethod
    def _dependencies_completed_from_records(
        task: TaskRecord, statuses: Mapping[int, TaskStatus]
    ) -> bool | None:
        """Return True/False when dependency statuses are known, else ``None``."""

        if not task.depends_on:
            return True
        try:
            return all(
                statuses[dep_id] == TaskStatus.COMPLETED for dep_id in task.depends_on
            )
        except KeyError:
            return None
