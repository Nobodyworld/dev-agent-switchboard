"""Shared FastAPI dependency helpers for the Switchboard API."""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from server.application import TaskService, build_task_service
from server.db import get_session
from server.settings import get_admin_token

SessionDependency = Annotated[AsyncSession, Depends(get_session)]


def get_task_service(session: SessionDependency) -> TaskService:
    """Return a task service wired with SQLAlchemy-backed repositories."""

    return build_task_service(session)


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
    if token != configured:
        raise HTTPException(status_code=401, detail="Invalid or missing admin token")


TaskServiceDependency = Annotated[TaskService, Depends(get_task_service)]
OptionalSessionDependency = Annotated[AsyncSession | None, Depends(get_session)]
OptionalTaskServiceDependency = Annotated[TaskService | None, Depends(get_task_service)]
