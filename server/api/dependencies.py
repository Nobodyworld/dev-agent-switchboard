"""Shared FastAPI dependency helpers for the Switchboard API."""

from __future__ import annotations

import hmac
from typing import Annotated

from fastapi import Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from server.application import (
    TaskService,
    build_execution_service,
    build_task_service,
)
from server.db import get_session
from server.execution.credentials import WorkerPrincipal, authenticate
from server.execution.service import ExecutionService
from server.github_adapter.repository import GitHubAdapterRepository
from server.github_adapter.service import (
    GitHubAdapterDependencies,
    GitHubAdapterService,
)
from server.github_adapter.transport import GitHubTransport
from server.settings import (
    GitHubConfigurationError,
    get_admin_token,
    get_github_settings,
)
from server.time_utils import utcnow_naive

SessionDependency = Annotated[AsyncSession, Depends(get_session)]


def get_task_service(session: SessionDependency) -> TaskService:
    """Return a task service wired with SQLAlchemy-backed repositories."""

    return build_task_service(session)


def get_execution_service(session: SessionDependency) -> ExecutionService:
    """Return an isolated execution-plane service for the request session."""

    return build_execution_service(session)


def get_github_adapter_service(
    session: SessionDependency,
) -> GitHubAdapterService:
    """Return the server-only outbound GitHub adapter for the request session."""

    try:
        settings = get_github_settings()
    except GitHubConfigurationError as error:
        raise HTTPException(status_code=503, detail=str(error)) from error
    return GitHubAdapterService(
        dependencies=GitHubAdapterDependencies(
            repository=GitHubAdapterRepository(session),
            execution=build_execution_service(session),
            transport=GitHubTransport(settings),
        ),
        settings=settings,
        clock=utcnow_naive,
    )


def resolve_task_service(
    service: TaskService | object,
    session: AsyncSession | object | None,
) -> TaskService:
    """Return a concrete :class:`TaskService` for route helpers and tests."""

    if isinstance(service, TaskService):
        return service
    if isinstance(session, AsyncSession):
        return build_task_service(session)
    raise RuntimeError("AsyncSession is required to construct TaskService")


def require_admin_token(request: Request) -> None:
    """Validate administrative token for protected endpoints."""

    configured = get_admin_token()
    if not configured:
        return
    header = request.headers.get("Authorization") or ""
    token: str | None = None
    if header.lower().startswith("bearer "):
        token = header.split(" ", 1)[1].strip()
    if not token:
        token = request.headers.get("X-Switchboard-Admin-Token")
    if token is None or not hmac.compare_digest(token.encode(), configured.encode()):
        raise HTTPException(status_code=401, detail="Invalid or missing admin token")


TaskServiceDependency = Annotated[TaskService, Depends(get_task_service)]
ExecutionServiceDependency = Annotated[ExecutionService, Depends(get_execution_service)]
GitHubAdapterServiceDependency = Annotated[
    GitHubAdapterService, Depends(get_github_adapter_service)
]
OptionalSessionDependency = Annotated[AsyncSession | None, Depends(get_session)]
OptionalTaskServiceDependency = Annotated[TaskService | None, Depends(get_task_service)]


async def require_worker_token(
    request: Request, session: SessionDependency
) -> WorkerPrincipal:
    """Authenticate only the closed worker bearer format; never fall back to admin."""
    headers = request.headers.getlist("Authorization")
    if (
        len(headers) != 1
        or not headers[0].startswith("Bearer ")
        or request.headers.getlist("X-Switchboard-Admin-Token")
    ):
        raise HTTPException(status_code=401, detail="worker_authentication_failed")
    principal = await authenticate(session, headers[0][7:])
    if principal is None:
        raise HTTPException(status_code=401, detail="worker_authentication_failed")
    if any(len(request.query_params.getlist(key)) != 1 for key in request.query_params):
        raise HTTPException(status_code=403, detail="worker_scope_denied")
    for key, value in request.query_params.multi_items():
        if key == "worker_id" and value == principal.worker_id:
            continue
        if key == "run_id" and request.url.path.startswith(
            "/api/execution/worker/manifests/"
        ):
            continue
        raise HTTPException(status_code=403, detail="worker_scope_denied")
    return principal


WorkerPrincipalDependency = Annotated[WorkerPrincipal, Depends(require_worker_token)]
