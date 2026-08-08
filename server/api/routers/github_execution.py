"""Authenticated manual GitHub exact-PR validation and publication routes."""

from __future__ import annotations

import datetime as dt
from typing import Literal, NoReturn

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.exc import IntegrityError

from server.api.dependencies import (
    GitHubAdapterServiceDependency,
    SessionDependency,
    require_admin_token,
)
from server.execution.enums import (
    ExecutionRunStatus,
    ReuseDecision,
    RoutingPolicy,
    WorkOrderStatus,
)
from server.execution.operator_projection import (
    MAX_OPERATOR_LIMIT,
    MAX_OPERATOR_OFFSET,
    ExecutionHistoryPageOut,
    ExecutionOperatorProjection,
)
from server.github_adapter.errors import (
    GitHubAdapterError,
    GitHubManifestError,
    GitHubRepositoryNotAllowedError,
    GitHubRequestNotFoundError,
    GitHubTerminalEvidenceRequiredError,
    GitHubTransportError,
)
from server.github_adapter.schemas import (
    GitHubValidationCreateIn,
    GitHubValidationRequestOut,
)

router = APIRouter(dependencies=[Depends(require_admin_token)])


@router.get(
    "/api/execution/github/requests",
    response_model=ExecutionHistoryPageOut,
)
async def list_github_validation_requests(  # noqa: PLR0913
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
    """List bounded GitHub request and linked lifecycle projections."""

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


def _raise_adapter_error(error: GitHubAdapterError) -> NoReturn:
    reason = str(error)
    if isinstance(error, GitHubRequestNotFoundError):
        raise HTTPException(status_code=404, detail=reason) from error
    if isinstance(error, GitHubRepositoryNotAllowedError):
        raise HTTPException(status_code=403, detail=reason) from error
    if isinstance(error, GitHubManifestError):
        raise HTTPException(status_code=422, detail=reason) from error
    if isinstance(error, GitHubTerminalEvidenceRequiredError):
        raise HTTPException(status_code=409, detail=reason) from error
    if isinstance(error, GitHubTransportError):
        status_code = 404 if reason.endswith("_not_found") else 503
        raise HTTPException(status_code=status_code, detail=reason) from error
    raise HTTPException(status_code=409, detail="github_adapter_conflict") from error


async def _commit(session: SessionDependency) -> None:
    try:
        await session.commit()
    except IntegrityError as error:
        await session.rollback()
        raise HTTPException(
            status_code=409, detail="github_adapter_persistence_conflict"
        ) from error


@router.post(
    "/api/execution/github/pull-requests/validate",
    response_model=GitHubValidationRequestOut,
)
async def request_pull_request_validation(
    body: GitHubValidationCreateIn,
    service: GitHubAdapterServiceDependency,
    session: SessionDependency,
) -> GitHubValidationRequestOut:
    """Resolve one exact head and create or return a pending work order."""

    try:
        status = await service.request_validation(
            repository_full_name=body.repository_full_name,
            pull_request_number=body.pull_request_number,
            manifest_name=body.manifest.name,
            manifest_version=body.manifest.version,
            reuse_policy=body.reuse_policy,
            routing_policy=body.routing_policy,
            maximum_cost_units=body.maximum_cost_units,
            required_quota_units=body.required_quota_units,
            preferred_executor=body.preferred_executor,
        )
    except GitHubAdapterError as error:
        await session.rollback()
        _raise_adapter_error(error)
    await _commit(session)
    return GitHubValidationRequestOut.from_status(status)


@router.get(
    "/api/execution/github/requests/{request_id}",
    response_model=GitHubValidationRequestOut,
)
async def get_github_validation_request(
    request_id: int,
    service: GitHubAdapterServiceDependency,
    session: SessionDependency,
) -> GitHubValidationRequestOut:
    """Return bounded adapter provenance and linked lifecycle only."""

    try:
        status = await service.get_status(request_id)
    except GitHubAdapterError as error:
        await session.rollback()
        _raise_adapter_error(error)
    return GitHubValidationRequestOut.from_status(status)


@router.post(
    "/api/execution/github/requests/{request_id}/publish",
    response_model=GitHubValidationRequestOut,
)
async def publish_github_validation_request(
    request_id: int,
    service: GitHubAdapterServiceDependency,
    session: SessionDependency,
) -> GitHubValidationRequestOut:
    """Recheck the head and synchronously upsert one managed PR comment."""

    try:
        status = await service.publish(request_id)
    except GitHubAdapterError as error:
        await session.rollback()
        _raise_adapter_error(error)
    await _commit(session)
    return GitHubValidationRequestOut.from_status(status)


__all__ = ["router"]
