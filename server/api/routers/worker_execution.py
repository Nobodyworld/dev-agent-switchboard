"""Deny-by-default worker lifecycle routes, separate from administrator routes."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query
from sqlalchemy import select

from server.api.dependencies import (
    ExecutionServiceDependency,
    SessionDependency,
    WorkerPrincipalDependency,
)
from server.api.routers import execution
from server.execution.schemas import (
    CheckoutIn,
    CheckoutOut,
    CommandManifestOut,
    ExecutionCompletionIn,
    ExecutionRunOut,
    ReuseCandidateOut,
    ReuseCandidateRequestIn,
    RunHeartbeatIn,
    WorkerHeartbeatIn,
    WorkerOut,
    WorkerRegistrationIn,
    WorkOrderOut,
)
from server.models import ExecutionRun, ExecutionWorkOrder

router = APIRouter(prefix="/api/execution/worker")


def _identity(expected: str, supplied: str) -> None:
    if expected != supplied:
        raise HTTPException(status_code=403, detail="worker_scope_denied")


async def _owned_run(
    session: SessionDependency, worker_id: str, run_id: int
) -> ExecutionRun:
    run = await session.get(ExecutionRun, run_id, populate_existing=True)
    if run is None or run.worker_id != worker_id:
        raise HTTPException(status_code=403, detail="worker_scope_denied")
    return run


@router.post("/workers", response_model=WorkerOut)
async def register_worker(
    body: WorkerRegistrationIn,
    principal: WorkerPrincipalDependency,
    service: ExecutionServiceDependency,
    session: SessionDependency,
) -> WorkerOut:
    _identity(principal.worker_id, body.worker_id)
    return await execution.register_worker(body, service, session)


@router.post("/workers/{worker_id}/heartbeat", response_model=WorkerOut)
async def heartbeat_worker(
    worker_id: str,
    body: WorkerHeartbeatIn,
    principal: WorkerPrincipalDependency,
    service: ExecutionServiceDependency,
    session: SessionDependency,
) -> WorkerOut:
    _identity(principal.worker_id, worker_id)
    return await execution.heartbeat_worker(worker_id, body, service, session)


@router.post("/checkout", response_model=CheckoutOut)
async def checkout(
    body: CheckoutIn,
    principal: WorkerPrincipalDependency,
    service: ExecutionServiceDependency,
    session: SessionDependency,
) -> CheckoutOut:
    _identity(principal.worker_id, body.worker_id)
    return await execution.checkout_execution_work(body, service, session)


@router.get("/work-orders/{work_order_id}", response_model=WorkOrderOut)
async def get_work_order(
    work_order_id: int,
    principal: WorkerPrincipalDependency,
    service: ExecutionServiceDependency,
    session: SessionDependency,
) -> WorkOrderOut:
    run = (
        await session.execute(
            select(ExecutionRun)
            .where(ExecutionRun.work_order_id == work_order_id)
            .order_by(ExecutionRun.id.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    if run is None or run.worker_id != principal.worker_id:
        raise HTTPException(status_code=403, detail="worker_scope_denied")
    return await execution.get_work_order(work_order_id, service, session)


@router.get("/runs/{run_id}", response_model=ExecutionRunOut)
async def get_run(
    run_id: int,
    principal: WorkerPrincipalDependency,
    service: ExecutionServiceDependency,
    session: SessionDependency,
) -> ExecutionRunOut:
    await _owned_run(session, principal.worker_id, run_id)
    return await execution.get_run(run_id, service, session)


@router.get("/manifests/{name}/{version}", response_model=CommandManifestOut)
async def get_manifest(  # noqa: PLR0913, PLR0917 - explicit scoped manifest identity
    name: str,
    version: str,
    principal: WorkerPrincipalDependency,
    service: ExecutionServiceDependency,
    session: SessionDependency,
    run_id: int = Query(ge=1),
) -> CommandManifestOut:
    run = await _owned_run(session, principal.worker_id, run_id)
    order = await session.get(ExecutionWorkOrder, run.work_order_id)
    if (
        order is None
        or order.manifest_name != name
        or order.manifest_version != version
    ):
        raise HTTPException(status_code=403, detail="worker_scope_denied")
    return await execution.get_manifest(name, version, service, session)


@router.post("/runs/{run_id}/heartbeat", response_model=ExecutionRunOut)
async def heartbeat_run(
    run_id: int,
    body: RunHeartbeatIn,
    principal: WorkerPrincipalDependency,
    service: ExecutionServiceDependency,
    session: SessionDependency,
) -> ExecutionRunOut:
    _identity(principal.worker_id, body.worker_id)
    await _owned_run(session, principal.worker_id, run_id)
    return await execution.heartbeat_run(run_id, body, service, session)


@router.post("/runs/{run_id}/reuse-candidate", response_model=ReuseCandidateOut)
async def resolve_reuse_candidate(
    run_id: int,
    body: ReuseCandidateRequestIn,
    principal: WorkerPrincipalDependency,
    service: ExecutionServiceDependency,
    session: SessionDependency,
) -> ReuseCandidateOut:
    _identity(principal.worker_id, body.worker_id)
    await _owned_run(session, principal.worker_id, run_id)
    return await execution.resolve_reuse_candidate(run_id, body, service, session)


@router.post("/runs/{run_id}/complete", response_model=ExecutionRunOut)
async def complete_run(
    run_id: int,
    body: ExecutionCompletionIn,
    principal: WorkerPrincipalDependency,
    service: ExecutionServiceDependency,
    session: SessionDependency,
) -> ExecutionRunOut:
    _identity(principal.worker_id, body.worker_id)
    await _owned_run(session, principal.worker_id, run_id)
    return await execution.complete_run(run_id, body, service, session)
