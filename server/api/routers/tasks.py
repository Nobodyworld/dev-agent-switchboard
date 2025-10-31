"""Task lifecycle routes."""

from __future__ import annotations

from typing import Annotated, Literal

from fastapi import APIRouter, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from server.api.dependencies import (
    OptionalSessionDependency,
    OptionalTaskServiceDependency,
    resolve_task_service,
)
from server.api.plan import broadcast_plan
from server.api.utils import records_to_out, task_record_to_out
from server.application import TaskService
from server.application.exceptions import (
    MissingDependenciesError,
    SelfDependencyError,
    TaskNotFoundError,
)
from server.domain import Agent
from server.schema import (
    CheckoutFailureReason,
    CheckoutOut,
    CompleteIn,
    CompleteResponse,
    StatusResponse,
    TaskAnalyticsOut,
    TaskIn,
    TaskOut,
    TaskUpdate,
)
from server.task_status import TaskStatus

StatusFilter = Annotated[
    TaskStatus | Literal["all"] | None,
    Query(
        description="Filter by status (use 'all' to disable filtering).",
    ),
]

router = APIRouter()


def _require_session(
    session: OptionalSessionDependency | AsyncSession | None,
) -> AsyncSession:
    if isinstance(session, AsyncSession):
        return session
    raise RuntimeError("AsyncSession is required for task operations")


@router.get("/api/tasks", response_model=list[TaskOut])
async def list_tasks(
    service: OptionalTaskServiceDependency = None,
    session: OptionalSessionDependency = None,
    status: StatusFilter = None,
) -> list[TaskOut]:
    db_session = _require_session(session)
    resolved: TaskService = resolve_task_service(service, db_session)
    records = await resolved.list_tasks(status=status)
    return records_to_out(records)


@router.get("/api/tasks/analytics", response_model=TaskAnalyticsOut)
async def read_task_analytics(
    service: OptionalTaskServiceDependency = None,
    session: OptionalSessionDependency = None,
) -> TaskAnalyticsOut:
    db_session = _require_session(session)
    resolved: TaskService = resolve_task_service(service, db_session)
    analytics = await resolved.analytics()
    return TaskAnalyticsOut.model_validate(analytics)


@router.post("/api/tasks", response_model=TaskOut)
async def create_task(
    task: TaskIn,
    service: OptionalTaskServiceDependency = None,
    session: OptionalSessionDependency = None,
) -> TaskOut:
    db_session = _require_session(session)
    resolved: TaskService = resolve_task_service(service, db_session)
    try:
        record = await resolved.create_task(
            title=task.title,
            description=task.description,
            depends_on=task.depends_on,
            priority=task.priority,
        )
    except MissingDependenciesError as exc:
        raise HTTPException(
            status_code=400, detail={"missing_dependencies": list(exc.missing_ids)}
        ) from exc

    await db_session.flush()
    version = await resolved.increment_plan_version()
    await broadcast_plan(version=version, service=resolved, include_plan=True)
    await db_session.commit()
    return task_record_to_out(record)


@router.put("/api/tasks/{task_id}", response_model=TaskOut)
@router.patch("/api/tasks/{task_id}", response_model=TaskOut)
async def update_task(
    task_id: int,
    update: TaskUpdate,
    service: OptionalTaskServiceDependency = None,
    session: OptionalSessionDependency = None,
) -> TaskOut:
    db_session = _require_session(session)
    resolved: TaskService = resolve_task_service(service, db_session)
    update_payload = update.model_dump(exclude_unset=True)
    if not update_payload:
        raise HTTPException(status_code=400, detail="no_updates_provided")

    try:
        record = await resolved.update_task(
            task_id,
            title=update.title,
            description=update.description,
            status=update.status,
            depends_on=update.depends_on,
            priority=update.priority,
        )
    except SelfDependencyError as exc:
        raise HTTPException(
            status_code=400,
            detail="task_cannot_depend_on_itself",
        ) from exc
    except MissingDependenciesError as exc:
        raise HTTPException(
            status_code=400, detail={"missing_dependencies": list(exc.missing_ids)}
        ) from exc
    except TaskNotFoundError as exc:
        raise HTTPException(status_code=404, detail="task_not_found") from exc

    await db_session.flush()
    version = await resolved.increment_plan_version()
    await broadcast_plan(version=version, service=resolved)
    await db_session.commit()
    return task_record_to_out(record)


@router.delete("/api/tasks/{task_id}", response_model=StatusResponse)
async def delete_task(
    task_id: int,
    service: OptionalTaskServiceDependency = None,
    session: OptionalSessionDependency = None,
) -> StatusResponse:
    db_session = _require_session(session)
    resolved: TaskService = resolve_task_service(service, db_session)
    deleted = await resolved.delete_task(task_id)
    await db_session.flush()
    if deleted:
        version = await resolved.increment_plan_version()
        await broadcast_plan(version=version, service=resolved, include_plan=True)
    await db_session.commit()
    return StatusResponse(ok=True)


@router.post("/api/tasks/checkout", response_model=CheckoutOut)
async def checkout(
    agent_id: str,
    service: OptionalTaskServiceDependency = None,
    session: OptionalSessionDependency = None,
    task_id: int | None = None,
) -> CheckoutOut:
    db_session = _require_session(session)
    resolved: TaskService = resolve_task_service(service, db_session)
    result = await resolved.checkout(Agent(agent_id=agent_id), task_id=task_id)
    await db_session.flush()
    if result.task is not None:
        version = await resolved.increment_plan_version()
        await broadcast_plan(version=version, service=resolved, include_plan=True)
        await db_session.commit()
        return CheckoutOut(task=task_record_to_out(result.task))
    await db_session.commit()
    reason = result.reason
    reason_enum = CheckoutFailureReason(reason) if reason else None
    return CheckoutOut(task=None, reason=reason_enum, message=result.message)


@router.post("/api/tasks/{task_id}/heartbeat", response_model=StatusResponse)
async def heartbeat(
    task_id: int,
    agent_id: str,
    service: OptionalTaskServiceDependency = None,
    session: OptionalSessionDependency = None,
) -> StatusResponse:
    db_session = _require_session(session)
    resolved: TaskService = resolve_task_service(service, db_session)
    result = await resolved.heartbeat(agent_id, task_id)
    await db_session.flush()
    await db_session.commit()
    return StatusResponse(ok=result.ok)


@router.post("/api/tasks/{task_id}/complete", response_model=CompleteResponse)
async def complete(
    task_id: int,
    agent_id: str,
    body: CompleteIn,
    service: OptionalTaskServiceDependency = None,
    session: OptionalSessionDependency = None,
) -> CompleteResponse:
    db_session = _require_session(session)
    resolved: TaskService = resolve_task_service(service, db_session)
    result = await resolved.complete(agent_id, task_id, notes=body.notes)
    await db_session.flush()
    if result.ok:
        version = await resolved.increment_plan_version()
        await broadcast_plan(version=version, service=resolved, include_plan=True)
    await db_session.commit()
    return CompleteResponse(ok=result.ok, notes=result.notes)


@router.post("/api/tasks/{task_id}/abandon", response_model=StatusResponse)
async def abandon(
    task_id: int,
    agent_id: str,
    service: OptionalTaskServiceDependency = None,
    session: OptionalSessionDependency = None,
) -> StatusResponse:
    db_session = _require_session(session)
    resolved: TaskService = resolve_task_service(service, db_session)
    result = await resolved.abandon(agent_id, task_id)
    await db_session.flush()
    if result.ok:
        version = await resolved.increment_plan_version()
        await broadcast_plan(version=version, service=resolved, include_plan=True)
    await db_session.commit()
    return StatusResponse(ok=result.ok)
