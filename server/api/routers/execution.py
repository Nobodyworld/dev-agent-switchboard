"""Typed, authenticated execution control-plane routes.

These routes persist lifecycle contracts only. They do not launch commands,
modify repositories, create worktrees, or accept executable payloads.
"""

from __future__ import annotations

import datetime as dt
from typing import Literal, NoReturn

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.exc import IntegrityError

from server.api.dependencies import (
    ExecutionServiceDependency,
    SessionDependency,
    require_admin_token,
)
from server.execution.entities import (
    ExecutionCompletion,
    RoutingProfileDraft,
    RoutingProfileReplacement,
    RoutingQuotaReset,
    WorkerRegistration,
    WorkOrderDraft,
)
from server.execution.enums import (
    ExecutionRunStatus,
    ReuseDecision,
    RoutingPolicy,
    WorkOrderStatus,
)
from server.execution.evidence import ExecutionEvidence
from server.execution.exceptions import (
    ApprovalDeniedError,
    ExecutionDomainError,
    ExecutionNotFoundError,
    LifecycleConflictError,
    MalformedEvidenceError,
    ManifestIntegrityError,
    ManifestParameterError,
    OwnershipConflictError,
    RepositoryWritePolicyError,
    UnknownManifestError,
)
from server.execution.operator_projection import (
    MAX_OPERATOR_LIMIT,
    MAX_OPERATOR_OFFSET,
    MAX_OPERATOR_WINDOW_DAYS,
    ExecutionHistoryPageOut,
    ExecutionOperatorOverviewOut,
    ExecutionOperatorProjection,
    ExecutionWorkerPageOut,
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
    ReuseCandidateOut,
    ReuseCandidateRequestIn,
    RouteAssessmentOut,
    RouteProvenanceOut,
    RoutingQuotaResetIn,
    RunHeartbeatIn,
    WorkerHeartbeatIn,
    WorkerOut,
    WorkerRegistrationIn,
    WorkerRoutingProfileCreateIn,
    WorkerRoutingProfileOut,
    WorkerRoutingProfileReplaceIn,
    WorkOrderCreateIn,
    WorkOrderOut,
)
from server.settings import get_execution_routing_settings

router = APIRouter(dependencies=[Depends(require_admin_token)])


@router.get(
    "/api/execution/operator/overview",
    response_model=ExecutionOperatorOverviewOut,
)
async def get_operator_overview(
    session: SessionDependency,
    window_days: int = Query(default=30, ge=1, le=MAX_OPERATOR_WINDOW_DAYS),
) -> ExecutionOperatorOverviewOut:
    """Return bounded validation, reuse, publication, and worker metrics."""

    freshness = get_execution_routing_settings()
    return await ExecutionOperatorProjection(session).overview(
        window_days=window_days,
        heartbeat_freshness_seconds=freshness.heartbeat_freshness_seconds,
        active_poll_freshness_seconds=freshness.active_poll_freshness_seconds,
    )


@router.get(
    "/api/execution/operator/history",
    response_model=ExecutionHistoryPageOut,
)
async def list_operator_history(  # noqa: PLR0913
    session: SessionDependency,
    limit: int = Query(default=25, ge=1, le=MAX_OPERATOR_LIMIT),
    offset: int = Query(default=0, ge=0, le=MAX_OPERATOR_OFFSET),
    repository_full_name: str | None = Query(
        default=None, min_length=3, max_length=255
    ),
    pull_request_number: int | None = Query(default=None, ge=1),
    work_order_status: WorkOrderStatus | None = None,
    run_status: ExecutionRunStatus | None = None,
    reuse_decision: ReuseDecision | None = None,
    routing_policy: RoutingPolicy | None = None,
    publication_state: (
        Literal[
            "not_published",
            "published_current",
            "published_stale",
            "retryable_failure",
            "failed",
        ]
        | None
    ) = None,
    created_after: dt.datetime | None = None,
    created_before: dt.datetime | None = None,
) -> ExecutionHistoryPageOut:
    """List redacted validation history in stable newest-first order."""

    return await ExecutionOperatorProjection(session).list_history(
        limit=limit,
        offset=offset,
        repository_full_name=repository_full_name,
        pull_request_number=pull_request_number,
        work_order_status=(work_order_status.value if work_order_status else None),
        run_status=(run_status.value if run_status else None),
        reuse_decision=(reuse_decision.value if reuse_decision else None),
        routing_policy=(routing_policy.value if routing_policy else None),
        publication_state=publication_state,
        created_after=created_after,
        created_before=created_before,
    )


@router.get("/api/execution/workers", response_model=ExecutionWorkerPageOut)
async def list_execution_workers(
    session: SessionDependency,
    limit: int = Query(default=25, ge=1, le=MAX_OPERATOR_LIMIT),
    offset: int = Query(default=0, ge=0, le=MAX_OPERATOR_OFFSET),
) -> ExecutionWorkerPageOut:
    """List bounded worker and operator-owned routing profile summaries."""

    freshness = get_execution_routing_settings()
    return await ExecutionOperatorProjection(session).list_workers(
        limit=limit,
        offset=offset,
        heartbeat_freshness_seconds=freshness.heartbeat_freshness_seconds,
        active_poll_freshness_seconds=freshness.active_poll_freshness_seconds,
    )


def _raise_domain_error(error: ExecutionDomainError) -> NoReturn:
    """Map expected execution-domain errors to documented HTTP responses."""

    if isinstance(error, ExecutionNotFoundError):
        raise HTTPException(status_code=404, detail=str(error)) from error
    if isinstance(error, MalformedEvidenceError):
        raise HTTPException(status_code=500, detail=str(error)) from error
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
        reuse_policy=body.reuse_policy,
        routing_policy=body.routing_policy,
        maximum_cost_units=body.maximum_cost_units,
        required_quota_units=body.required_quota_units,
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


@router.get(
    "/api/execution/work-orders/{work_order_id}/route-assessment",
    response_model=RouteAssessmentOut,
)
async def assess_work_order_route(
    work_order_id: int,
    service: ExecutionServiceDependency,
    session: SessionDependency,
) -> RouteAssessmentOut:
    """Assess current routing without refreshing polls or reserving state."""

    try:
        assessment = await service.assess_route(work_order_id)
    except ExecutionDomainError as error:
        await _rollback_and_raise(session, error)
    await _commit(session)
    return RouteAssessmentOut.model_validate(assessment)


@router.get(
    "/api/execution/work-orders/{work_order_id}/route",
    response_model=RouteProvenanceOut,
)
async def get_work_order_route(
    work_order_id: int,
    service: ExecutionServiceDependency,
    session: SessionDependency,
) -> RouteProvenanceOut:
    """Read compact persisted route provenance for an assigned order."""

    try:
        work_order = await service.get_work_order(work_order_id)
        if work_order.route_provenance is None:
            raise ExecutionNotFoundError("route_provenance_not_found")
    except ExecutionDomainError as error:
        await _rollback_and_raise(session, error)
    return RouteProvenanceOut.model_validate(work_order.route_provenance)


@router.post(
    "/api/execution/routing-profiles",
    response_model=WorkerRoutingProfileOut,
)
async def create_routing_profile(
    body: WorkerRoutingProfileCreateIn,
    service: ExecutionServiceDependency,
    session: SessionDependency,
) -> WorkerRoutingProfileOut:
    """Create privileged operator-owned cost and quota state."""

    try:
        profile = await service.create_routing_profile(
            RoutingProfileDraft(
                schema_version=body.schema_version,
                worker_id=body.worker_id,
                enabled=body.enabled,
                estimated_cost_units_per_run=body.estimated_cost_units_per_run,
                quota_capacity_units=body.quota_capacity_units,
                quota_remaining_units=body.quota_remaining_units,
                quota_reset_at=body.quota_reset_at,
                routing_priority=body.routing_priority,
            )
        )
    except ExecutionDomainError as error:
        await _rollback_and_raise(session, error)
    await _commit(session)
    return WorkerRoutingProfileOut.model_validate(profile)


@router.get(
    "/api/execution/routing-profiles",
    response_model=list[WorkerRoutingProfileOut],
)
async def list_routing_profiles(
    service: ExecutionServiceDependency,
) -> list[WorkerRoutingProfileOut]:
    """List privileged routing profiles in stable worker-ID order."""

    return [
        WorkerRoutingProfileOut.model_validate(profile)
        for profile in await service.list_routing_profiles()
    ]


@router.get(
    "/api/execution/routing-profiles/{worker_id}",
    response_model=WorkerRoutingProfileOut,
)
async def get_routing_profile(
    worker_id: str,
    service: ExecutionServiceDependency,
    session: SessionDependency,
) -> WorkerRoutingProfileOut:
    """Read one privileged routing profile."""

    try:
        profile = await service.get_routing_profile(worker_id)
    except ExecutionDomainError as error:
        await _rollback_and_raise(session, error)
    return WorkerRoutingProfileOut.model_validate(profile)


@router.put(
    "/api/execution/routing-profiles/{worker_id}",
    response_model=WorkerRoutingProfileOut,
)
async def replace_routing_profile(
    worker_id: str,
    body: WorkerRoutingProfileReplaceIn,
    service: ExecutionServiceDependency,
    session: SessionDependency,
) -> WorkerRoutingProfileOut:
    """Replace one profile only at its expected revision."""

    try:
        profile = await service.replace_routing_profile(
            worker_id,
            RoutingProfileReplacement(
                expected_revision=body.expected_revision,
                enabled=body.enabled,
                estimated_cost_units_per_run=body.estimated_cost_units_per_run,
                quota_capacity_units=body.quota_capacity_units,
                quota_remaining_units=body.quota_remaining_units,
                quota_reset_at=body.quota_reset_at,
                routing_priority=body.routing_priority,
            ),
        )
    except ExecutionDomainError as error:
        await _rollback_and_raise(session, error)
    await _commit(session)
    return WorkerRoutingProfileOut.model_validate(profile)


@router.post(
    "/api/execution/routing-profiles/{worker_id}/quota-reset",
    response_model=WorkerRoutingProfileOut,
)
async def reset_routing_quota(
    worker_id: str,
    body: RoutingQuotaResetIn,
    service: ExecutionServiceDependency,
    session: SessionDependency,
) -> WorkerRoutingProfileOut:
    """Apply an idempotent monotonic quota reset at an expected revision."""

    try:
        profile = await service.reset_routing_quota(
            worker_id,
            RoutingQuotaReset(
                expected_revision=body.expected_revision,
                quota_remaining_units=body.quota_remaining_units,
                quota_reset_at=body.quota_reset_at,
            ),
        )
    except ExecutionDomainError as error:
        await _rollback_and_raise(session, error)
    await _commit(session)
    return WorkerRoutingProfileOut.model_validate(profile)


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


@router.get(
    "/api/execution/runs/{run_id}/route",
    response_model=RouteProvenanceOut,
)
async def get_run_route(
    run_id: int,
    service: ExecutionServiceDependency,
    session: SessionDependency,
) -> RouteProvenanceOut:
    """Read compact persisted route provenance for one execution run."""

    try:
        run = await service.get_run(run_id)
    except ExecutionDomainError as error:
        await _rollback_and_raise(session, error)
    return RouteProvenanceOut.model_validate(run.route_provenance)


@router.get("/api/execution/runs/{run_id}/evidence", response_model=ExecutionEvidence)
async def get_run_evidence(
    run_id: int,
    service: ExecutionServiceDependency,
    session: SessionDependency,
) -> ExecutionEvidence:
    """Return strict compact evidence without local paths or full logs."""

    try:
        return await service.get_run_evidence(run_id)
    except ExecutionDomainError as error:
        await _rollback_and_raise(session, error)


@router.post(
    "/api/execution/runs/{run_id}/reuse-candidate",
    response_model=ReuseCandidateOut,
)
async def resolve_reuse_candidate(
    run_id: int,
    body: ReuseCandidateRequestIn,
    service: ExecutionServiceDependency,
    session: SessionDependency,
) -> ReuseCandidateOut:
    """Resolve one exact server-owned source for the current lease owner."""

    try:
        result = await service.resolve_reuse_candidate(
            run_id,
            worker_id=body.worker_id,
            reuse_identity=body.reuse_identity,
            reuse_identity_hash=body.reuse_identity_hash,
        )
    except ExecutionDomainError as error:
        await _rollback_and_raise(session, error)
    await _commit(session)
    return ReuseCandidateOut(
        decision=result.decision,
        reason=result.reason,
        candidate=result.candidate,
    )


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
        reuse_decision=body.reuse_decision,
        reuse_reason=body.reuse_reason,
        reuse_identity=body.reuse_identity,
        reuse_identity_hash=body.reuse_identity_hash,
        evidence_retention_expires_at=body.evidence_retention_expires_at,
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
