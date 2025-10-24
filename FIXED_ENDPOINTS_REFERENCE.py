"""
Reference implementation showing the corrected endpoints for PR #73.

This file demonstrates the fixes needed for the issue:
"Update plan endpoints to pass TaskService to _serialize_plan"

Apply these changes to server/app.py in PR #73 (commit 3d6d237).
"""

from fastapi import Depends, WebSocket
from sqlalchemy.ext.asyncio import AsyncSession

# These imports assume PR #73's code structure
# from .application import TaskService, build_task_service
# from .db import AsyncSessionLocal, get_session
# from .schema import PlanOut


# ============================================================================
# FIX #1: /api/plan endpoint
# ============================================================================

# BEFORE (INCORRECT - line ~787 in PR #73):
#
# @app.get("/api/plan", response_model=PlanOut)
# async def get_plan(session: AsyncSession = Depends(get_session)):
#     """Return the full task plan, including version metadata."""
#  
#     plan_dict = await _serialize_plan(session)  # ❌ Wrong! session not TaskService
#     if hasattr(PlanOut, "model_validate"):
#         return PlanOut.model_validate(plan_dict)
#     return PlanOut(**plan_dict)


# AFTER (CORRECT):

def get_task_service_dependency(session: AsyncSession = Depends(lambda: None)) -> "TaskService":
    """Mock dependency for illustration"""
    pass

@app.get("/api/plan", response_model=PlanOut)  # type: ignore  # noqa
async def get_plan(service: "TaskService" = Depends(get_task_service_dependency)):  # ✓ Correct!
    """Return the full task plan, including version metadata."""

    plan_dict = await _serialize_plan(service)  # ✓ Pass TaskService
    if hasattr(PlanOut, "model_validate"):
        return PlanOut.model_validate(plan_dict)  # type: ignore
    return PlanOut(**plan_dict)  # type: ignore


# ============================================================================
# FIX #2: /ws/plan WebSocket endpoint  
# ============================================================================

# BEFORE (INCORRECT - line ~800 in PR #73):
#
# @app.websocket("/ws/plan")
# async def ws_plan(ws: WebSocket):
#     """Stream plan updates to connected web clients via WebSocket."""
#
#     await ws.accept()
#     await PLAN_BROADCASTER.add(ws)
#     try:
#         async with AsyncSessionLocal() as session:
#             plan_payload = await _serialize_plan(session)  # ❌ Wrong! session not TaskService
#         initial_payload: PlanBroadcastPayload = {
#             "type": "plan_snapshot",
#             "version": plan_payload.get("version", 0),
#             "plan": plan_payload,
#         }
#         # ... rest of function


# AFTER (CORRECT):

@app.websocket("/ws/plan")  # type: ignore  # noqa
async def ws_plan(ws: WebSocket):
    """Stream plan updates to connected web clients via WebSocket."""

    await ws.accept()
    await PLAN_BROADCASTER.add(ws)  # type: ignore  # noqa
    try:
        async with AsyncSessionLocal() as session:  # type: ignore  # noqa
            service = build_task_service(session)  # ✓ Create TaskService from session
            plan_payload = await _serialize_plan(service)  # ✓ Pass TaskService
        initial_payload: PlanBroadcastPayload = {  # type: ignore  # noqa
            "type": "plan_snapshot",
            "version": plan_payload.get("version", 0),
            "plan": plan_payload,
        }
        ok = await _send_ws_payload(ws, initial_payload, timeout=PLAN_SEND_TIMEOUT)  # type: ignore  # noqa
        if not ok:
            return
        while True:
            try:
                await ws.receive_text()
            except WebSocketDisconnect:  # type: ignore  # noqa
                break
            except Exception as exc:
                logger.info("Plan websocket receive error", exc_info=exc)  # type: ignore  # noqa
                break
    except WebSocketDisconnect:  # type: ignore  # noqa
        pass
    except Exception as exc:
        logger.error("Plan websocket failure", exc_info=exc)  # type: ignore  # noqa
    finally:
        await PLAN_BROADCASTER.discard(ws)  # type: ignore  # noqa


# ============================================================================
# SUMMARY OF CHANGES
# ============================================================================
#
# 1. get_plan endpoint:
#    - Change parameter from: session: AsyncSession = Depends(get_session)
#    - To: service: TaskService = Depends(get_task_service)
#    - Update call from: _serialize_plan(session)
#    - To: _serialize_plan(service)
#
# 2. ws_plan WebSocket:
#    - After creating session, add: service = build_task_service(session)
#    - Update call from: _serialize_plan(session)
#    - To: _serialize_plan(service)
#
# These changes ensure that _serialize_plan receives a TaskService instance
# (which has list_tasks() and plan_version_snapshot() methods) rather than
# an AsyncSession object (which doesn't have these methods).
