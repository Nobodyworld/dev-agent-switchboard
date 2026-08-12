"""Live file management routes."""

from __future__ import annotations

import inspect
import os
from collections.abc import Awaitable, Callable

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse, Response
from sqlalchemy.ext.asyncio import AsyncSession

from server.api.dependencies import (
    OptionalSessionDependency,
    OptionalTaskServiceDependency,
    require_admin_token,
    resolve_task_service,
)
from server.api.plan import broadcast_plan
from server.application import TaskService
from server.file_store import full_path, put_file
from server.schema import FileUploadResponse
from server.settings import get_max_live_file_bytes

try:  # optional live file ETag helper
    from server.file_store import etag_for_path as _etag_for_path
except ImportError:  # pragma: no cover - helper may be absent
    _etag_for_path: Callable[[str], Awaitable[str | None] | str | None] | None = None

router = APIRouter()


def _require_session(
    session: OptionalSessionDependency | AsyncSession | None,
) -> AsyncSession:
    if isinstance(session, AsyncSession):
        return session
    raise RuntimeError("AsyncSession is required for file operations")


async def _resolve_etag(path: str) -> str | None:
    provider = _etag_for_path
    if provider is None:
        return None
    candidate = provider(path)
    if inspect.isawaitable(candidate):
        return await candidate
    return candidate


async def _read_bounded_body(request: Request) -> bytes:
    limit = get_max_live_file_bytes()
    content_length = request.headers.get("content-length")
    if content_length:
        try:
            declared_size = int(content_length)
        except ValueError:
            declared_size = None
        if declared_size is not None and declared_size > limit:
            raise HTTPException(status_code=413, detail="live file exceeds size limit")

    data = bytearray()
    async for chunk in request.stream():
        if len(data) + len(chunk) > limit:
            raise HTTPException(status_code=413, detail="live file exceeds size limit")
        data.extend(chunk)
    return bytes(data)


@router.put(
    "/api/files/{path:path}",
    response_model=FileUploadResponse,
    dependencies=[Depends(require_admin_token)],
)
async def put_live_file(
    path: str,
    request: Request,
    service: OptionalTaskServiceDependency = None,
    session: OptionalSessionDependency = None,
) -> FileUploadResponse:
    db_session = _require_session(session)
    resolved: TaskService = resolve_task_service(service, db_session)
    data = await _read_bounded_body(request)
    write_result = await put_file(db_session, path, data)
    await db_session.flush()
    version = await resolved.increment_plan_version()
    await broadcast_plan(version=version, service=resolved, include_plan=True)
    await db_session.commit()
    return FileUploadResponse(
        ok=True,
        sha256=write_result.sha256,
        size=write_result.size,
        url=f"/live/{path}",
    )


@router.get("/live/{path:path}")
async def get_live_file(path: str, request: Request):
    fp = full_path(path)
    if not os.path.exists(fp):  # noqa: ASYNC240 - bounded local metadata probe
        return JSONResponse({"error": "not_found"}, status_code=404)

    etag_value = await _resolve_etag(path)

    if etag_value:
        incoming = request.headers.get("if-none-match")
        if incoming:
            etag_candidates = [
                tag.strip() for tag in incoming.split(",") if tag.strip()
            ]
            normalized_request_tags: list[str] = []
            for candidate in etag_candidates:
                if candidate == "*":
                    normalized_request_tags.append("*")
                    continue
                candidate_value = (
                    candidate[2:].strip()
                    if candidate.startswith("W/")
                    else candidate.strip()
                )
                if not candidate_value:
                    continue
                if not (
                    candidate_value.startswith('"') and candidate_value.endswith('"')
                ):
                    candidate_value = candidate_value.strip('"')
                    candidate_value = f'"{candidate_value}"'
                normalized_request_tags.append(candidate_value)
            if "*" in normalized_request_tags or etag_value in normalized_request_tags:
                not_modified = Response(status_code=304)
                not_modified.headers["ETag"] = etag_value
                return not_modified

    response = FileResponse(fp)
    if etag_value:
        response.headers.setdefault("ETag", etag_value)
    return response
