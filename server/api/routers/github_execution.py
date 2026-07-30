"""Authenticated manual GitHub exact-PR validation and publication routes."""

from __future__ import annotations

from typing import NoReturn

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.exc import IntegrityError

from server.api.dependencies import (
    GitHubAdapterServiceDependency,
    SessionDependency,
    require_admin_token,
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
