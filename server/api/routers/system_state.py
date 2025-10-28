"""System state management routes."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request

from server.api.dependencies import SessionDependency
from server.api.plan import broadcast_system_state
from server.api.utils import system_state_to_out
from server.application import SystemStateUpdate, build_system_state_service
from server.application.exceptions import SystemStateConflictError
from server.domain import SystemState
from server.schema import SystemStateOut, SystemStateUpdateIn

router = APIRouter()


def _serialize_state(state: SystemState | None) -> SystemStateOut:
    if state is None:
        return SystemStateOut(
            maintenance_mode=False,
            message=None,
            updated_at=None,
            version=0,
        )
    return system_state_to_out(state)


@router.get("/api/system-state", response_model=SystemStateOut)
async def read_system_state(
    session: SessionDependency,
) -> SystemStateOut:
    service = build_system_state_service(session)
    state = await service.get_state()
    return _serialize_state(state)


@router.put("/api/system-state", response_model=SystemStateOut)
async def mutate_system_state(
    payload: SystemStateUpdateIn,
    request: Request,
    session: SessionDependency,
) -> SystemStateOut:
    _ = request  # Request context reserved for future middleware hooks.
    service = build_system_state_service(session)
    update = SystemStateUpdate(
        maintenance_mode=payload.maintenance_mode,
        message=payload.message,
        expected_version=payload.expected_version,
    )
    try:
        state = await service.update_state(update)
    except SystemStateConflictError as exc:
        detail = {
            "error": "version_conflict",
            "expected_version": exc.expected_version,
            "actual_version": exc.actual_version,
        }
        raise HTTPException(status_code=409, detail=detail) from exc
    await session.commit()
    await broadcast_system_state(state)
    return _serialize_state(state)
