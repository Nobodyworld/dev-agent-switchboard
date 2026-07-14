"""Typed, authenticated execution control-plane routes.

These routes persist lifecycle contracts only. They do not launch commands,
modify repositories, create worktrees, or accept executable payloads.
"""

from __future__ import annotations

from typing import NoReturn

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.exc import IntegrityError

from server.api.dependencies import (
    ExecutionServiceDependency,
    SessionDependency,
    require_admin_token,
)
from server.execution.entities import (
    ExecutionCompletion,
    WorkerRegistration,
    WorkOrderDraft,
)
from server.execution.enums import ExecutionRunStatus
from server.execution.exceptions import (
    ApprovalDeniedError,
    ExecutionDomainError,
    ExecutionNotFoundError,
    LifecycleConflictError,
    ManifestIntegrityError,
    ManifestParameterError,
    OwnershipConflictError,
    RepositoryWritePolicyError,
    UnknownManifestError,
)
from server.execution.schemas import (
    ApproveWorkOrderIn,
    CheckoutIn,
    CheckoutOut,
    CommandManifestOut,
    ExecutionCompletionIn,
    ExecutionRunOut,
    ExpireLeasesOut,
    ReasonIn,
    RunHeartbeatIn,
    WorkerHeartbeatIn,
    WorkerOut,
    WorkerRegistrationIn,
    WorkOrderCreateIn,
    WorkOrderOut,
)

router = APIRouter(dependencies=[Depends(require_admin_token)])


def _raise_domain_error(error: ExecutionDomainError) -> NoReturn:
    """Map expected execution-domain errors to documented HTTP responses."""

    if isinstance(error, ExecutionNotFoundError):
        raise HTTPException(status_code=404, detail=str(error)) from error
    if isinstance(
        error,
        (UnknownManifestError, ManifestParameterError, RepositoryWritePolicyError),
    ):
        raise HTTPException(status_code=422, detail=str(error)) from error
    if isinstance(
        error,
        (
            ApprovalDeniedError,
            LifecycleConflictError,
            ManifestIntegrityError,
            OwnershipConflictError,
        ),
    ):
        raise HTTPException(status_code=409, detail=str(error)) from error
    raise HTTPException(
        status_code=409, detail="execution_lifecycle_conflict"
    ) from error


async def _commit(session: SessionDependency) -> None:
    """Commit a successful mutation or surface an expected persistence conflict."""

    try:
        await session.commit()
    except IntegrityError as error:
        await session.rollback()
        raise HTTPException(
            status_code=409, detail="execution_persistence_conflict"
        ) from error


async def _rollback_and_raise(
    session: SessionDependency, error: ExecutionDomainError
) -> NoReturn:
    """Clear an incomplete request transaction before returning a typed error."""

    await session.rollback()
    _raise_domain_error(error)


@router.get("/api/execution/manifests", response_model=list[CommandManifestOut])
async def list_manifests(
    service: ExecutionServiceDependency,
    session: SessionDependency,
) -> list[CommandManifestOut]:
    """List server-controlled manifest identities and safe metadata."""

    try:
        manifests = await service.list_manifests()
    except ExecutionDomainError as error:
        await _rollback_and_raise(session, error)
    await _commit(session)
    return [CommandManifestOut.model_validate(manifest) for manifest in manifests]


@router.get(
    "/api/execution/manifests/{name}/{version}", response_model=CommandManifestOut
)
async def get_manifest(
    name: str,
    version: str,
    service: ExecutionServiceDependency,
    session: SessionDependency,
) -> CommandManifestOut:
    """Read one persisted trusted manifest identity."""

    try:
        manifest = await service.get_manifest(name, version)
    except ExecutionDomainError as error:
        await _rollback_and_raise(session, error)
    await _commit(session)
    return CommandManifestOut.model_validate(manifest)


@router.post("/api/execution/work-orders", response_model=WorkOrderOut)
async def create_work_order(
    body: WorkOrderCreateIn,
    service: ExecutionServiceDependency,
    session: SessionDependency,
) -> WorkOrderOut:
    """Create a pending work order using a trusted manifest reference only."""

    draft = WorkOrderDraft(
        schema_version=body.schema_version,
        repository_full_name=body.repository_full_name,
        commit_sha=body.commit_sha,
        manifest_name=body.manifest.name,
        manifest_version=body.manifest.version,
        manifest_parameters=body.manifest.parameters,
        required_capabilities=body.required_capabilities,
        permitted_paths=tuple(body.permitted_paths),
        forbidden_scope_notes=body.forbidden_scope_notes,
        expected_artifact_kinds=tuple(body.expected_artifact_kinds),
        approval_policy=body.approval_policy,
        timeout_seconds=body.timeout_seconds,
        resource_metadata=body.resource_metadata,
        network_policy=body.network_policy,
        repository_write_allowed=body.repository_write,
        preferred_executor=body.preferred_executor,
        cost_ceiling=body.cost_ceiling,
    )
    try:
        work_order = await service.create_work_order(draft)
    except ExecutionDomainError as error:
        await _rollback_and_raise(session, error)
    await _commit(session)
    return WorkOrderOut.model_validate(work_order)


@router.get("/api/execution/work-orders", response_model=list[WorkOrderOut])
async def list_work_orders(
    service: ExecutionServiceDependency,
) -> list[WorkOrderOut]:
    """List independently persisted execution requests."""

    return [
        WorkOrderOut.model_validate(work_order)
        for work_order in await service.list_work_orders()
    ]


@router.get("/api/execution/work-orders/{work_order_id}", response_model=WorkOrderOut)
async def get_work_order(
    work_order_id: int,
    service: ExecutionServiceDependency,
    session: SessionDependency,
) -> WorkOrderOut:
    """Read a persisted work order and its current lifecycle status."""

    try:
        work_order = await service.get_work_order(work_order_id)
    except ExecutionDomainError as error:
        await _rollback_and_raise(session, error)
    return WorkOrderOut.model_validate(work_order)


@router.post(
    "/api/execution/work-orders/{work_order_id}/approve", response_model=WorkOrderOut
)
async def approve_work_order(
    work_order_id: int,
    body: ApproveWorkOrderIn,
    service: ExecutionServiceDependency,
    session: SessionDependency,
) -> WorkOrderOut:
    """Explicitly approve an allowlisted read-only work order."""

    try:
        work_order = await service.approve_work_order(work_order_id, queue=body.queue)
    except ExecutionDomainError as error:
        await _rollback_and_raise(session, error)
    await _commit(session)
    return WorkOrderOut.model_validate(work_order)


@router.post(
    "/api/execution/work-orders/{work_order_id}/queue", response_model=WorkOrderOut
)
async def queue_work_order(
    work_order_id: int,
    service: ExecutionServiceDependency,
    session: SessionDependency,
) -> WorkOrderOut:
    """Make an already approved work order available for worker checkout."""

    try:
        work_order = await service.queue_work_order(work_order_id)
    except ExecutionDomainError as error:
        await _rollback_and_raise(session, error)
    await _commit(session)
    return WorkOrderOut.model_validate(work_order)


@router.post(
    "/api/execution/work-orders/{work_order_id}/reject", response_model=WorkOrderOut
)
async def reject_work_order(
    work_order_id: int,
    body: ReasonIn,
    service: ExecutionServiceDependency,
    session: SessionDependency,
) -> WorkOrderOut:
    """Reject a pending work order before assignment."""

    try:
        work_order = await service.reject_work_order(work_order_id, reason=body.reason)
    except ExecutionDomainError as error:
        await _rollback_and_raise(session, error)
    await _commit(session)
    return WorkOrderOut.model_validate(work_order)


@router.post(
    "/api/execution/work-orders/{work_order_id}/cancel", response_model=WorkOrderOut
)
async def cancel_work_order(
    work_order_id: int,
    body: ReasonIn,
    service: ExecutionServiceDependency,
    session: SessionDependency,
) -> WorkOrderOut:
    """Cancel an order and safely release an active execution lease if present."""

    try:
        work_order = await service.cancel_work_order(work_order_id, reason=body.reason)
    except ExecutionDomainError as error:
        await _rollback_and_raise(session, error)
    await _commit(session)
    return WorkOrderOut.model_validate(work_order)


@router.post(
    "/api/execution/work-orders/{work_order_id}/expire", response_model=WorkOrderOut
)
async def expire_work_order(
    work_order_id: int,
    body: ReasonIn,
    service: ExecutionServiceDependency,
    session: SessionDependency,
) -> WorkOrderOut:
    """Expire an unassigned approved or queued work order."""

    try:
        work_order = await service.expire_work_order(work_order_id, reason=body.reason)
    except ExecutionDomainError as error:
        await _rollback_and_raise(session, error)
    await _commit(session)
    return WorkOrderOut.model_validate(work_order)


@router.post(
    "/api/execution/work-orders/{work_order_id}/requeue", response_model=WorkOrderOut
)
async def requeue_stale_work_order(
    work_order_id: int,
    service: ExecutionServiceDependency,
    session: SessionDependency,
) -> WorkOrderOut:
    """Safely requeue only work whose active execution lease has expired."""

    try:
        work_order = await service.requeue_stale_work_order(work_order_id)
    except ExecutionDomainError as error:
        await _rollback_and_raise(session, error)
    await _commit(session)
    return WorkOrderOut.model_validate(work_order)


@router.post("/api/execution/workers", response_model=WorkerOut)
async def register_worker(
    body: WorkerRegistrationIn,
    service: ExecutionServiceDependency,
    session: SessionDependency,
) -> WorkerOut:
    """Register or refresh a worker using the documented Phase 1 credential."""

    registration = WorkerRegistration(
        worker_id=body.worker_id,
        display_name=body.display_name,
        operating_system=body.operating_system,
        architecture=body.architecture,
        python_version=body.python_version,
        node_version=body.node_version,
        docker_available=body.docker_available,
        browsers=tuple(body.browsers),
        gpu_available=body.gpu_available,
        unity_available=body.unity_available,
        desktop_available=body.desktop_available,
        capabilities=body.capabilities,
        max_concurrency=body.max_concurrency,
        network_policy_capability=body.network_policy_capability,
        repository_write_capability=body.repository_write_capability,
        status=body.status,
    )
    try:
        worker = await service.register_worker(registration)
    except ExecutionDomainError as error:
        await _rollback_and_raise(session, error)
    await _commit(session)
    return WorkerOut.model_validate(worker)


@router.post("/api/execution/workers/{worker_id}/heartbeat", response_model=WorkerOut)
async def heartbeat_worker(
    worker_id: str,
    body: WorkerHeartbeatIn,
    service: ExecutionServiceDependency,
    session: SessionDependency,
) -> WorkerOut:
    """Refresh a worker registration heartbeat."""

    try:
        worker = await service.heartbeat_worker(worker_id, status=body.status)
    except ExecutionDomainError as error:
        await _rollback_and_raise(session, error)
    await _commit(session)
    return WorkerOut.model_validate(worker)


@router.post("/api/execution/checkout", response_model=CheckoutOut)
async def checkout_execution_work(
    body: CheckoutIn,
    service: ExecutionServiceDependency,
    session: SessionDependency,
) -> CheckoutOut:
    """Atomically assign at most one eligible queued work order to a worker."""

    try:
        result = await service.checkout(body.worker_id)
    except ExecutionDomainError as error:
        await _rollback_and_raise(session, error)
    await _commit(session)
    if result.run_id is None:
        return CheckoutOut(
            reason=result.reason,
            mismatch_reasons=list(result.mismatch_reasons),
        )
    run = await service.get_run(result.run_id)
    return CheckoutOut(run=ExecutionRunOut.model_validate(run))


@router.get("/api/execution/runs", response_model=list[ExecutionRunOut])
async def list_runs(
    service: ExecutionServiceDependency,
    work_order_id: int | None = Query(default=None, ge=1),
) -> list[ExecutionRunOut]:
    """List historical attempts without exposing unbounded logs or artifacts."""

    return [
        ExecutionRunOut.model_validate(run)
        for run in await service.list_runs(work_order_id)
    ]


@router.get("/api/execution/runs/{run_id}", response_model=ExecutionRunOut)
async def get_run(
    run_id: int,
    service: ExecutionServiceDependency,
    session: SessionDependency,
) -> ExecutionRunOut:
    """Read a historical execution-attempt record."""

    try:
        run = await service.get_run(run_id)
    except ExecutionDomainError as error:
        await _rollback_and_raise(session, error)
    return ExecutionRunOut.model_validate(run)


@router.post("/api/execution/runs/{run_id}/heartbeat", response_model=ExecutionRunOut)
async def heartbeat_run(
    run_id: int,
    body: RunHeartbeatIn,
    service: ExecutionServiceDependency,
    session: SessionDependency,
) -> ExecutionRunOut:
    """Refresh an owned run lease and transition assigned work to running."""

    try:
        run = await service.heartbeat_run(run_id, worker_id=body.worker_id)
    except ExecutionDomainError as error:
        await _rollback_and_raise(session, error)
    await _commit(session)
    return ExecutionRunOut.model_validate(run)


@router.post("/api/execution/runs/{run_id}/complete", response_model=ExecutionRunOut)
async def complete_run(
    run_id: int,
    body: ExecutionCompletionIn,
    service: ExecutionServiceDependency,
    session: SessionDependency,
) -> ExecutionRunOut:
    """Persist a terminal run result after verifying active-lease ownership."""

    completion = ExecutionCompletion(
        status=ExecutionRunStatus(body.status),
        result_summary=body.result_summary,
        terminal_reason=body.terminal_reason,
        cleanup_status=body.cleanup_status,
        artifact_metadata=tuple(body.artifact_metadata),
        evidence_metadata=body.evidence_metadata,
    )
    try:
        run = await service.complete_run(
            run_id,
            worker_id=body.worker_id,
            completion=completion,
        )
    except ExecutionDomainError as error:
        await _rollback_and_raise(session, error)
    await _commit(session)
    return ExecutionRunOut.model_validate(run)


@router.post("/api/execution/leases/expire", response_model=ExpireLeasesOut)
async def expire_stale_execution_leases(
    service: ExecutionServiceDependency,
    session: SessionDependency,
) -> ExpireLeasesOut:
    """Timeout stale runs, release capacity, and requeue eligible work safely."""

    try:
        result = await service.expire_stale_leases()
    except ExecutionDomainError as error:
        await _rollback_and_raise(session, error)
    await _commit(session)
    return ExpireLeasesOut(
        requeued_work_order_ids=list(result.requeued_work_order_ids),
        timed_out_run_ids=list(result.timed_out_run_ids),
    )
