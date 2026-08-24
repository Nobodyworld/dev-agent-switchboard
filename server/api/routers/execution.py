"""Typed, authenticated execution control-plane routes.

These routes persist lifecycle contracts only. They do not launch commands,
modify repositories, create worktrees, or accept executable payloads.
"""

from __future__ import annotations

import datetime as dt
from typing import Literal, NoReturn, TypeAlias, cast

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.exc import IntegrityError

from server.api.dependencies import (
    ExecutionServiceDependency,
    SessionDependency,
    require_admin_token,
)
from server.execution.catalog import (
    get_trusted_repository,
    iter_trusted_repositories,
    repository_allows_manifest,
    trusted_catalog_digest,
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
    CatalogReadinessLimitError,
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
from server.execution.registry import get_trusted_manifest
from server.execution.routing import MAX_ROUTING_INTEGER, RoutingEligibility
from server.execution.schemas import (
    ApproveWorkOrderIn,
    CatalogReadinessBlockerOut,
    CatalogReadinessEntryOut,
    CatalogReadinessLatestResultOut,
    CatalogReadinessManifestOut,
    CatalogReadinessOut,
    CatalogReadinessSourceAvailabilityOut,
    CheckoutIn,
    CheckoutOut,
    CommandManifestOut,
    ExecutionCompletionIn,
    ExecutionRunOut,
    ExpireLeasesOut,
    ReasonIn,
    RepositoryWorkerReadinessOut,
    ReuseCandidateOut,
    ReuseCandidateRequestIn,
    RouteAssessmentOut,
    RouteProvenanceOut,
    RoutingQuotaResetIn,
    RunHeartbeatIn,
    TrustedCatalogOut,
    TrustedManifestReferenceOut,
    TrustedRepositoryOut,
    TrustedRepositoryReadinessOut,
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
_MAX_READINESS_WORKERS = 100
_CATALOG_SOURCE_AVAILABILITY_CAVEAT = (
    "Exact source availability requires an operator-configured canonical checkout "
    "at the requested SHA."
)
_CATALOG_BLOCKER_LABELS = {
    "ready": "No current blocker",
    "no_registered_workers": "No registered workers",
    "repository_unavailable": "No registered worker advertises this repository",
    "manifest_capability_mismatch": (
        "No worker satisfies the reviewed runtime requirements"
    ),
    "profile_missing": "Routing profile is missing",
    "profile_invalid": "Routing profile is invalid",
    "profile_disabled": "Routing profile is disabled",
    "stale_worker": "Registered workers are stale",
    "capacity_constrained": "Compatible workers are at capacity",
    "worker_unavailable": "Compatible workers are unavailable",
    "maximum_cost_exceeded": "Routing cost ceiling excludes compatible workers",
    "insufficient_quota": "Routing quota is insufficient",
    "preferred_executor_unavailable": "Preferred worker is unavailable",
}
RepositoryReadinessReason: TypeAlias = Literal[
    "ready",
    "repository_unavailable",
    "manifest_capability_mismatch",
    "profile_missing",
    "profile_invalid",
    "profile_disabled",
    "stale",
    "capacity_constrained",
    "worker_unavailable",
    "maximum_cost_exceeded",
    "insufficient_quota",
    "preferred_executor_mismatch",
]


@router.get("/api/execution/catalog", response_model=TrustedCatalogOut)
async def get_trusted_catalog() -> TrustedCatalogOut:
    """Return safe source-controlled repository and manifest associations."""

    repositories = []
    for repository in iter_trusted_repositories():
        manifests = []
        for reference in repository.manifests:
            manifest = get_trusted_manifest(reference.name, reference.version)
            if manifest is None:  # Import-time catalog validation makes this defensive.
                continue
            manifests.append(
                TrustedManifestReferenceOut(
                    name=manifest.name,
                    version=manifest.version,
                    digest=manifest.digest,
                    description=manifest.description,
                )
            )
        repositories.append(
            TrustedRepositoryOut(
                full_name=repository.full_name,
                display_name=repository.display_name,
                description=repository.description,
                support_status=repository.support_status,
                documentation_reference=repository.documentation_reference,
                manifests=manifests,
                default_manifest=repository.default_manifest.safe_metadata(),
            )
        )
    return TrustedCatalogOut(
        schema_version=1,
        digest=trusted_catalog_digest(),
        repositories=repositories,
    )


@router.get(
    "/api/execution/catalog-readiness",
    response_model=CatalogReadinessOut,
)
async def get_catalog_readiness(
    service: ExecutionServiceDependency,
) -> CatalogReadinessOut:
    """Return one bounded, non-mutating readiness summary for public workloads."""

    try:
        assessments = await service.assess_catalog_readiness()
    except CatalogReadinessLimitError as error:
        raise HTTPException(status_code=503, detail=str(error)) from error
    entries: list[CatalogReadinessEntryOut] = []
    for assessment in assessments:
        label = _CATALOG_BLOCKER_LABELS.get(assessment.primary_blocker_code)
        if label is None:  # Source-controlled service state must fail closed.
            raise HTTPException(status_code=500, detail="catalog_readiness_invalid")
        latest_result = assessment.latest_result
        entries.append(
            CatalogReadinessEntryOut(
                repository=assessment.repository_full_name,
                display_name=assessment.display_name,
                default_manifest=CatalogReadinessManifestOut(
                    name=assessment.manifest_name,
                    version=assessment.manifest_version,
                    digest_prefix=assessment.manifest_digest[:12],
                ),
                runtime_requirements=dict(assessment.runtime_requirements),
                ready_count=assessment.ready_count,
                primary_blocker=CatalogReadinessBlockerOut(
                    code=assessment.primary_blocker_code,
                    label=label,
                ),
                latest_result=(
                    CatalogReadinessLatestResultOut(
                        reuse_decision=latest_result.reuse_decision,
                        duration_seconds=latest_result.duration_seconds,
                        step_count=latest_result.step_count,
                        avoided_work_count=latest_result.avoided_work_count,
                    )
                    if latest_result is not None
                    else None
                ),
                source_availability=CatalogReadinessSourceAvailabilityOut(
                    status="requires_exact_source",
                    caveat=_CATALOG_SOURCE_AVAILABILITY_CAVEAT,
                ),
                exclusions=list(assessment.exclusions),
            )
        )
    return CatalogReadinessOut(entries=entries)


@router.get(
    "/api/execution/trusted-repositories",
    response_model=TrustedCatalogOut,
)
async def list_trusted_repositories() -> TrustedCatalogOut:
    """Return the canonical bounded trusted-workload catalog."""

    return await get_trusted_catalog()


@router.get(
    "/api/execution/trusted-repositories/{owner}/{repository}",
    response_model=TrustedRepositoryOut,
)
async def get_trusted_repository_detail(
    owner: str,
    repository: str,
) -> TrustedRepositoryOut:
    """Return one bounded trusted repository definition."""

    catalog = await get_trusted_catalog()
    full_name = f"{owner}/{repository}"
    detail = next(
        (item for item in catalog.repositories if item.full_name == full_name), None
    )
    if detail is None:
        raise HTTPException(status_code=404, detail="trusted_repository_not_found")
    return detail


@router.get(
    "/api/execution/trusted-repositories/{owner}/{repository}/readiness",
    response_model=TrustedRepositoryReadinessOut,
)
async def get_named_trusted_repository_readiness(  # noqa: PLR0913, PLR0917
    owner: str,
    repository: str,
    service: ExecutionServiceDependency,
    manifest_name: str | None = Query(default=None, min_length=1, max_length=128),
    manifest_version: str | None = Query(default=None, min_length=1, max_length=64),
    routing_policy: RoutingPolicy = RoutingPolicy.FIRST_AVAILABLE,
    maximum_cost_units: int | None = Query(default=None, ge=0, le=MAX_ROUTING_INTEGER),
    required_quota_units: int = Query(default=0, ge=0, le=MAX_ROUTING_INTEGER),
    preferred_executor: str | None = Query(default=None, min_length=1, max_length=128),
) -> TrustedRepositoryReadinessOut:
    """Return read-only readiness at the canonical catalog route."""

    return await _build_repository_readiness(
        repository_full_name=f"{owner}/{repository}",
        service=service,
        manifest_name=manifest_name,
        manifest_version=manifest_version,
        routing_policy=routing_policy,
        maximum_cost_units=maximum_cost_units,
        required_quota_units=required_quota_units,
        preferred_executor=preferred_executor,
    )


@router.get(
    "/api/execution/catalog/{repository_full_name:path}/readiness",
    response_model=TrustedRepositoryReadinessOut,
)
async def get_trusted_repository_readiness(  # noqa: PLR0913, PLR0917
    repository_full_name: str,
    service: ExecutionServiceDependency,
    manifest_name: str | None = Query(default=None, min_length=1, max_length=128),
    manifest_version: str | None = Query(default=None, min_length=1, max_length=64),
    routing_policy: RoutingPolicy = RoutingPolicy.FIRST_AVAILABLE,
    maximum_cost_units: int | None = Query(default=None, ge=0, le=MAX_ROUTING_INTEGER),
    required_quota_units: int = Query(default=0, ge=0, le=MAX_ROUTING_INTEGER),
    preferred_executor: str | None = Query(default=None, min_length=1, max_length=128),
) -> TrustedRepositoryReadinessOut:
    """Return bounded read-only worker readiness for one catalog entry."""

    return await _build_repository_readiness(
        repository_full_name=repository_full_name,
        service=service,
        manifest_name=manifest_name,
        manifest_version=manifest_version,
        routing_policy=routing_policy,
        maximum_cost_units=maximum_cost_units,
        required_quota_units=required_quota_units,
        preferred_executor=preferred_executor,
    )


async def _build_repository_readiness(  # noqa: PLR0913
    *,
    repository_full_name: str,
    service: ExecutionServiceDependency,
    manifest_name: str | None,
    manifest_version: str | None,
    routing_policy: RoutingPolicy,
    maximum_cost_units: int | None,
    required_quota_units: int,
    preferred_executor: str | None,
) -> TrustedRepositoryReadinessOut:
    """Project shared routing eligibility into the bounded catalog contract."""

    repository = get_trusted_repository(repository_full_name)
    if repository is None:
        raise HTTPException(status_code=404, detail="trusted_repository_not_found")
    if (manifest_name is None) != (manifest_version is None):
        raise HTTPException(
            status_code=422, detail="manifest_identity_must_be_complete"
        )
    if manifest_name is None or manifest_version is None:
        default_manifest = repository.default_manifest
        if default_manifest is None:
            raise HTTPException(
                status_code=422, detail="repository_default_manifest_missing"
            )
        manifest_name = default_manifest.name
        manifest_version = default_manifest.version
    if not repository_allows_manifest(
        repository_full_name, manifest_name, manifest_version
    ):
        raise HTTPException(status_code=422, detail="repository_manifest_not_allowed")

    evaluations, selected = await service.assess_repository_readiness(
        repository_full_name=repository_full_name,
        manifest_name=manifest_name,
        manifest_version=manifest_version,
        routing_policy=routing_policy,
        maximum_cost_units=maximum_cost_units,
        required_quota_units=required_quota_units,
        preferred_executor=preferred_executor,
    )
    eligible_count = sum(item.candidate is not None for item in evaluations)
    workers: list[RepositoryWorkerReadinessOut] = []
    for evaluation in evaluations[:_MAX_READINESS_WORKERS]:
        worker = evaluation.worker
        profile = evaluation.profile
        reason = _repository_readiness_reason(evaluation)
        ready = evaluation.candidate is not None
        workers.append(
            RepositoryWorkerReadinessOut(
                worker_id=worker.worker_id,
                display_name=worker.display_name,
                advertises_repository=(
                    repository_full_name in worker.repository_full_names
                ),
                activity_state=_repository_activity_state(evaluation),
                routing_profile_enabled=(profile is not None and profile.enabled),
                estimated_comparison_units=(
                    profile.estimated_cost_units_per_run
                    if profile is not None
                    else None
                ),
                quota_remaining_units=(
                    profile.quota_remaining_units if profile is not None else None
                ),
                quota_capacity_units=(
                    profile.quota_capacity_units if profile is not None else None
                ),
                active_run_count=worker.active_run_count,
                max_concurrency=worker.max_concurrency,
                readiness_reason=reason,
                ready=ready,
                selected=(
                    selected is not None
                    and selected.worker.worker_id == worker.worker_id
                ),
            )
        )
    return TrustedRepositoryReadinessOut(
        repository_full_name=repository_full_name,
        manifest_name=manifest_name,
        manifest_version=manifest_version,
        routing_policy=routing_policy,
        maximum_cost_units=maximum_cost_units,
        required_quota_units=required_quota_units,
        preferred_executor=preferred_executor,
        selected_worker_id=(
            selected.worker.worker_id if selected is not None else None
        ),
        eligible_worker_count=eligible_count,
        ready_worker_count=eligible_count,
        workers=workers,
    )


def _repository_readiness_reason(
    evaluation: RoutingEligibility,
) -> RepositoryReadinessReason:
    """Collapse internal diagnostics into a stable operator-safe vocabulary."""

    if evaluation.candidate is not None:
        return "ready"
    precedence = (
        ("preferred_executor_mismatch", "preferred_executor_mismatch"),
        ("worker_repository_unavailable", "repository_unavailable"),
        ("routing_profile_missing", "profile_missing"),
        ("routing_profile_invalid", "profile_invalid"),
        ("routing_profile_disabled", "profile_disabled"),
        ("worker_heartbeat_stale", "stale"),
        ("worker_checkout_poll_stale", "stale"),
        ("worker_not_available", "worker_unavailable"),
        ("worker_concurrency_limit", "capacity_constrained"),
        ("routing_cost_ceiling_exceeded", "maximum_cost_exceeded"),
        ("routing_quota_insufficient", "insufficient_quota"),
    )
    for internal, public in precedence:
        if internal in evaluation.reasons:
            return cast(RepositoryReadinessReason, public)
    return "manifest_capability_mismatch"


def _repository_activity_state(
    evaluation: RoutingEligibility,
) -> Literal["active", "stale", "capacity_constrained", "unavailable"]:
    """Derive activity state from the same evaluator diagnostics."""

    reasons = evaluation.reasons
    if "worker_not_available" in reasons:
        return "unavailable"
    if "worker_heartbeat_stale" in reasons or "worker_checkout_poll_stale" in reasons:
        return "stale"
    if "worker_concurrency_limit" in reasons:
        return "capacity_constrained"
    return "active"


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
async def list_operator_history(  # noqa: PLR0913, PLR0917
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
        pnpm_version=body.pnpm_version,
        docker_available=body.docker_available,
        browsers=tuple(body.browsers),
        gpu_available=body.gpu_available,
        unity_available=body.unity_available,
        desktop_available=body.desktop_available,
        capabilities=body.capabilities,
        repository_full_names=tuple(body.repository_full_names),
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
