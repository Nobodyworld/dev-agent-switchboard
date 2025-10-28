"""Plan and ExecPlan routes."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from fastapi import (
    APIRouter,
    Depends,
    Query,
    Request,
    Response,
    WebSocket,
    WebSocketDisconnect,
)
from fastapi.responses import JSONResponse
from yaml import safe_dump

from server.api.dependencies import SessionDependency, require_admin_token
from server.api.plan import (
    PLAN_BROADCASTER,
    PLAN_SEND_TIMEOUT,
    send_ws_payload,
    serialize_plan,
)
from server.api.utils import serialize_model, system_state_to_out
from server.application import build_system_state_service, build_task_service
from server.db import AsyncSessionLocal
from server.execplan_registry import build_registry_index
from server.observability.activity import get_activity_feed_snapshot
from server.schema import ActivityFeedOut, PlanOut

router = APIRouter()


def _negotiate_execplan_format(request: Request) -> str:
    format_hint = request.query_params.get("format")
    if format_hint:
        lowered = format_hint.lower()
        if lowered in {"yaml", "yml"}:
            return "yaml"
        if lowered == "json":
            return "json"
    accept = request.headers.get("accept", "")
    yaml_markers = {"application/yaml", "text/yaml", "application/x-yaml"}
    if any(marker in accept for marker in yaml_markers):
        return "yaml"
    return "json"


def _etag_matches(etag: str, header_value: str | None) -> bool:
    if not header_value:
        return False
    candidates = [tag.strip() for tag in header_value.split(",") if tag.strip()]
    return "*" in candidates or etag in candidates


@router.get("/api/execplans/index", name="execplan_index")
async def execplan_index(request: Request, session: SessionDependency):
    desired_format = _negotiate_execplan_format(request)
    source_url = str(request.url)
    payload, etag, _, http_date = await build_registry_index(
        session,
        source_url=source_url,
    )
    await session.commit()

    headers = {"ETag": etag, "Last-Modified": http_date}

    if _etag_matches(etag, request.headers.get("if-none-match")):
        return Response(status_code=304, headers=headers)

    if desired_format == "yaml":
        body = safe_dump(payload, sort_keys=False)
        if not body.endswith("\n"):
            body = f"{body}\n"
        return Response(content=body, media_type="application/yaml", headers=headers)

    return JSONResponse(payload, headers=headers)


@router.get("/api/plan", response_model=PlanOut)
async def read_plan(session: SessionDependency):
    service = build_task_service(session)
    plan_dict = await serialize_plan(service)
    if hasattr(PlanOut, "model_validate"):
        return PlanOut.model_validate(plan_dict)  # type: ignore[attr-defined]
    return PlanOut(**plan_dict)


@router.websocket("/ws/plan")
async def plan_ws(ws: WebSocket) -> None:
    await ws.accept()
    await PLAN_BROADCASTER.add(ws)
    try:
        async with AsyncSessionLocal() as session:
            service = build_task_service(session)
            plan_payload = await serialize_plan(service)
            state_service = build_system_state_service(session)
            system_state = await state_service.get_state()
        initial_payload: dict[str, Any] = {
            "type": "plan_snapshot",
            "version": plan_payload.get("version", 0),
            "plan": plan_payload,
            "state": serialize_model(system_state_to_out(system_state)),
        }
        ok = await send_ws_payload(ws, initial_payload, timeout=PLAN_SEND_TIMEOUT)
        if not ok:
            return
        while True:
            try:
                await ws.receive_text()
            except WebSocketDisconnect:
                break
            except Exception:  # pragma: no cover - defensive logging
                break
    finally:
        await PLAN_BROADCASTER.discard(ws)


@router.get(
    "/api/observability/audit-feed",
    response_model=ActivityFeedOut,
    dependencies=[Depends(require_admin_token)],
)
async def read_activity_feed(limit: int = Query(50, ge=1, le=200)) -> ActivityFeedOut:
    events = await get_activity_feed_snapshot(limit=limit)
    return {
        "generated_at": datetime.now(timezone.utc),
        "events": events,
    }
