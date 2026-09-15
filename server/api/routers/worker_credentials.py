"""Deliberate administrator-only worker credential management."""

from __future__ import annotations

import datetime as dt
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Path, Response
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.exc import IntegrityError

from server.api.dependencies import SessionDependency, require_admin_token
from server.execution import credentials
from server.models import WorkerCredential
from server.settings import get_admin_token

router = APIRouter()
WorkerId = Annotated[str, Path(pattern=r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$")]


class EmptyCredentialRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")


class CredentialChangeIn(EmptyCredentialRequest):
    credential_id: str = Field(pattern=r"^[0-9a-f]{32}$")


class CredentialOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    worker_id: str
    credential_id: str
    created_at: dt.datetime
    rotated_at: dt.datetime | None
    revoked_at: dt.datetime | None


class IssuedCredentialOut(CredentialOut):
    worker_token: str = Field(repr=False)


def require_credential_administrator() -> None:
    if not get_admin_token():
        raise HTTPException(status_code=503, detail="administrator_not_configured")


_MANAGEMENT = [Depends(require_admin_token), Depends(require_credential_administrator)]


@router.post(
    "/api/execution/worker-credentials/{worker_id}/issue",
    response_model=IssuedCredentialOut,
    dependencies=_MANAGEMENT,
)
async def issue_credential(
    worker_id: WorkerId,
    body: EmptyCredentialRequest,
    session: SessionDependency,
    response: Response,
) -> IssuedCredentialOut:
    del body
    try:
        row, token = await credentials.issue(session, worker_id)
        await session.commit()
    except (credentials.CredentialConflictError, IntegrityError) as error:
        await session.rollback()
        raise HTTPException(
            status_code=409, detail="credential_transition_conflict"
        ) from error
    response.headers["Cache-Control"] = "no-store"
    return IssuedCredentialOut(
        **CredentialOut.model_validate(row).model_dump(), worker_token=token
    )


@router.post(
    "/api/execution/worker-credentials/{worker_id}/rotate",
    response_model=IssuedCredentialOut,
    dependencies=_MANAGEMENT,
)
async def rotate_credential(
    worker_id: WorkerId,
    body: CredentialChangeIn,
    session: SessionDependency,
    response: Response,
) -> IssuedCredentialOut:
    try:
        row, token = await credentials.rotate(session, worker_id, body.credential_id)
        await session.commit()
    except (credentials.CredentialConflictError, IntegrityError) as error:
        await session.rollback()
        raise HTTPException(
            status_code=409, detail="credential_transition_conflict"
        ) from error
    response.headers["Cache-Control"] = "no-store"
    return IssuedCredentialOut(
        **CredentialOut.model_validate(row).model_dump(), worker_token=token
    )


@router.post(
    "/api/execution/worker-credentials/{worker_id}/revoke",
    response_model=CredentialOut,
    dependencies=_MANAGEMENT,
)
async def revoke_credential(
    worker_id: WorkerId, body: CredentialChangeIn, session: SessionDependency
) -> CredentialOut:
    try:
        row = await credentials.revoke(session, worker_id, body.credential_id)
        await session.commit()
    except (credentials.CredentialConflictError, IntegrityError) as error:
        await session.rollback()
        raise HTTPException(
            status_code=409, detail="credential_transition_conflict"
        ) from error
    return CredentialOut.model_validate(row)


@router.get(
    "/api/execution/worker-credentials/{worker_id}",
    response_model=CredentialOut,
    dependencies=_MANAGEMENT,
)
async def get_credential(
    worker_id: WorkerId, session: SessionDependency
) -> CredentialOut:
    row = await session.get(WorkerCredential, worker_id)
    if row is None:
        raise HTTPException(status_code=404, detail="credential_not_found")
    return CredentialOut.model_validate(row)
