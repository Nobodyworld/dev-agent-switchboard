"""Bounded worker credential persistence and constant-time verification."""

from __future__ import annotations

import hashlib
import hmac
import re
import secrets
from dataclasses import dataclass
from typing import Any, cast

from sqlalchemy import select, update
from sqlalchemy.engine import CursorResult
from sqlalchemy.ext.asyncio import AsyncSession

from server.execution.enums import WorkerStatus
from server.models import ExecutionWorker, WorkerCredential
from server.time_utils import utcnow_naive

TOKEN_PATTERN = re.compile(r"swb_w1\.([0-9a-f]{32})\.([0-9a-f]{64})")
WORKER_ID_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,127}")
_DUMMY_VERIFIER = "0" * 64


@dataclass(frozen=True, slots=True)
class WorkerPrincipal:
    worker_id: str
    credential_id: str


class CredentialConflictError(ValueError):
    """A deliberate credential transition no longer matches stored state."""


async def authenticate(session: AsyncSession, token: str) -> WorkerPrincipal | None:
    match = TOKEN_PATTERN.fullmatch(token)
    if match is None:
        return None
    credential_id, secret = match.groups()
    row = (
        await session.execute(
            select(WorkerCredential)
            .where(WorkerCredential.credential_id == credential_id)
            .execution_options(populate_existing=True)
        )
    ).scalar_one_or_none()
    verifier = row.verifier if row is not None else _DUMMY_VERIFIER
    valid = hmac.compare_digest(
        hashlib.sha256(secret.encode("ascii")).hexdigest(), verifier
    )
    if not valid or row is None or row.revoked_at is not None:
        return None
    return WorkerPrincipal(row.worker_id, row.credential_id)


async def issue(session: AsyncSession, worker_id: str) -> tuple[WorkerCredential, str]:
    if await session.get(WorkerCredential, worker_id) is not None:
        raise CredentialConflictError("credential_already_issued")
    now = utcnow_naive()
    worker = (
        await session.execute(
            select(ExecutionWorker).where(ExecutionWorker.worker_id == worker_id)
        )
    ).scalar_one_or_none()
    if worker is None:
        session.add(
            ExecutionWorker(
                worker_id=worker_id,
                display_name=worker_id,
                operating_system="unregistered",
                architecture="unregistered",
                repository_full_names=[],
                capabilities={},
                status=WorkerStatus.OFFLINE,
                last_heartbeat_at=now,
            )
        )
        await session.flush()
    credential_id, secret = secrets.token_hex(16), secrets.token_hex(32)
    row = WorkerCredential(
        worker_id=worker_id,
        credential_id=credential_id,
        verifier=hashlib.sha256(secret.encode("ascii")).hexdigest(),
        created_at=now,
    )
    session.add(row)
    await session.flush()
    return row, f"swb_w1.{credential_id}.{secret}"


async def rotate(
    session: AsyncSession,
    worker_id: str,
    expected_id: str,
) -> tuple[WorkerCredential, str]:
    credential_id, secret = secrets.token_hex(16), secrets.token_hex(32)
    result = await session.execute(
        update(WorkerCredential)
        .where(
            WorkerCredential.worker_id == worker_id,
            WorkerCredential.credential_id == expected_id,
        )
        .values(
            credential_id=credential_id,
            verifier=hashlib.sha256(secret.encode("ascii")).hexdigest(),
            rotated_at=utcnow_naive(),
            revoked_at=None,
        )
        .execution_options(synchronize_session=False)
    )
    if cast(CursorResult[Any], result).rowcount != 1:
        raise CredentialConflictError("credential_transition_conflict")
    row = await session.get(WorkerCredential, worker_id, populate_existing=True)
    if row is None:
        raise CredentialConflictError("credential_transition_conflict")
    return row, f"swb_w1.{credential_id}.{secret}"


async def revoke(
    session: AsyncSession, worker_id: str, expected_id: str
) -> WorkerCredential:
    await session.execute(
        update(WorkerCredential)
        .where(
            WorkerCredential.worker_id == worker_id,
            WorkerCredential.credential_id == expected_id,
            WorkerCredential.revoked_at.is_(None),
        )
        .values(revoked_at=utcnow_naive())
        .execution_options(synchronize_session=False)
    )
    row = await session.get(WorkerCredential, worker_id, populate_existing=True)
    if row is None or row.credential_id != expected_id:
        raise CredentialConflictError("credential_transition_conflict")
    return row
