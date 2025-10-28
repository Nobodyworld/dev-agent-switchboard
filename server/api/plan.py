"""Plan broadcasting utilities and shared helpers."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Mapping
from contextlib import suppress
from typing import Any, Literal, TypedDict

from fastapi import WebSocket, WebSocketDisconnect
from sqlalchemy.ext.asyncio import AsyncSession

from server.api.utils import records_to_out, serialize_model, system_state_to_out
from server.application import TaskService, build_task_service
from server.db import AsyncSessionLocal
from server.domain import SystemState
from server.extensions import get_extension_bundle
from server.observability import span
from server.schema import PlanOut

logger = logging.getLogger(__name__)

PLAN_SEND_TIMEOUT = 2.0


class PlanBroadcastPayload(TypedDict, total=False):
    """Typed WebSocket payload used when broadcasting plan updates."""

    type: Literal["plan_version", "plan_snapshot", "system_state"]
    version: int
    plan: dict[str, Any]
    delta: dict[str, Any]
    state: dict[str, Any]


class PlanBroadcaster:
    """Manage WebSocket connections that should receive plan updates."""

    def __init__(self, *, send_timeout: float = PLAN_SEND_TIMEOUT) -> None:
        self._connections: set[WebSocket] = set()
        self._lock = asyncio.Lock()
        self._send_timeout = send_timeout

    async def add(self, ws: WebSocket) -> None:
        """Register a new WebSocket connection for future broadcasts."""

        async with self._lock:
            # TODO(P3, 3d) - Record connection metadata to help with targeted
            # disconnects and diagnostics.
            self._connections.add(ws)

    async def discard(self, ws: WebSocket) -> None:
        """Remove a WebSocket connection if present."""

        async with self._lock:
            self._connections.discard(ws)

    async def broadcast(self, payload: PlanBroadcastPayload) -> None:
        """Send a payload to all active connections, pruning stale sockets."""

        async with self._lock:
            recipients = list(self._connections)

        stale: list[WebSocket] = []
        for ws in recipients:
            ok = await send_ws_payload(ws, payload, timeout=self._send_timeout)
            if not ok:
                stale.append(ws)

        if not stale:
            return

        for ws in stale:
            with suppress(Exception):
                await ws.close()
            await self.discard(ws)

    def connection_count(self) -> int:
        """Return the number of currently tracked WebSocket connections."""

        return len(self._connections)

    async def close_all(self) -> None:
        """Close and drop all tracked connections (primarily used in tests)."""

        async with self._lock:
            recipients = list(self._connections)
            self._connections.clear()

        for ws in recipients:
            with suppress(Exception):
                await ws.close()


PLAN_BROADCASTER = PlanBroadcaster()


async def send_ws_payload(
    ws: WebSocket,
    payload: Mapping[str, Any] | PlanBroadcastPayload,
    *,
    timeout: float = PLAN_SEND_TIMEOUT,
) -> bool:
    try:
        await asyncio.wait_for(ws.send_json(payload), timeout=timeout)
        return True
    except (asyncio.TimeoutError, WebSocketDisconnect, RuntimeError):
        return False
    except Exception as exc:  # pragma: no cover - defensive logging
        logger.warning("Failed to broadcast plan payload", exc_info=exc)
        return False


async def serialize_plan(service: TaskService) -> dict[str, Any]:
    """Serialize the current task plan to the public schema."""

    tasks = await service.list_tasks()
    snapshot = await service.plan_version_snapshot()
    plan = PlanOut(
        version=snapshot.value,
        updated_at=snapshot.updated_at,
        tasks=records_to_out(tasks),
    )
    return serialize_model(plan)


async def _prepare_plan_payload(
    service: TaskService,
    *,
    version: int | None,
    include_plan: bool,
    plan: dict[str, Any] | None,
    serializer,
) -> tuple[int | None, dict[str, Any] | None]:
    """Resolve the plan version and optional payload for broadcasting."""

    resolved_version = version or await service.plan_version()
    plan_payload = plan
    if include_plan and plan_payload is None:
        plan_payload = await serializer(service)
    if plan_payload is not None and version is None:
        resolved_version = plan_payload.get("version", resolved_version)
    return resolved_version, plan_payload


async def broadcast_plan(  # noqa: PLR0913 - broadcast requires optional collaborators for tests
    version: int | None = None,
    session: AsyncSession | None = None,
    *,
    include_plan: bool = False,
    plan: dict[str, Any] | None = None,
    delta: dict[str, Any] | None = None,
    service: TaskService | None = None,
    serializer=None,
) -> None:
    """Broadcast the latest plan version to connected WebSocket listeners."""

    if serializer is None:
        serializer = serialize_plan

    bundle = get_extension_bundle()
    observer_count = len(bundle.plan_observers)

    async def _dispatch(
        task_service: TaskService,
        *,
        resolved_version: int | None,
        plan_payload: dict[str, Any] | None,
    ) -> None:
        analytics = None
        if observer_count:
            with span(
                "broadcast_plan.analytics",
                plan_version=resolved_version,
                observer_count=observer_count,
            ):
                analytics = await task_service.analytics()

        payload: PlanBroadcastPayload = {"type": "plan_version"}
        if resolved_version is not None:
            payload["version"] = resolved_version
        if plan_payload is not None:
            payload["plan"] = plan_payload
        if delta is not None:
            payload["delta"] = delta

        if observer_count:
            with span(
                "broadcast_plan.observers",
                plan_version=resolved_version,
                observer_count=observer_count,
                has_plan=plan_payload is not None,
                includes_delta=delta is not None,
            ):
                await bundle.emit_plan_event(
                    "on_plan_broadcast",
                    version=resolved_version,
                    plan=plan_payload,
                    delta=delta,
                    analytics=analytics,
                )

        with span(
            "broadcast_plan.broadcast",
            plan_version=resolved_version,
            observer_count=observer_count,
            has_plan=plan_payload is not None,
            includes_delta=delta is not None,
        ):
            await PLAN_BROADCASTER.broadcast(payload)

    if service is None and session is None:
        async with AsyncSessionLocal() as temp_session:
            temp_service = build_task_service(temp_session)
            resolved_version, plan_payload = await _prepare_plan_payload(
                temp_service,
                version=version,
                include_plan=include_plan,
                plan=plan,
                serializer=serializer,
            )
            await _dispatch(
                temp_service,
                resolved_version=resolved_version,
                plan_payload=plan_payload,
            )
        return

    if service is None:
        if session is None:  # pragma: no cover - defensive
            raise RuntimeError("AsyncSession is required when service is not provided")
        service = build_task_service(session)

    resolved_version, plan_payload = await _prepare_plan_payload(
        service,
        version=version,
        include_plan=include_plan,
        plan=plan,
        serializer=serializer,
    )
    await _dispatch(
        service,
        resolved_version=resolved_version,
        plan_payload=plan_payload,
    )


async def broadcast_system_state(state: SystemState) -> None:
    """Broadcast system state updates to connected clients."""

    payload: PlanBroadcastPayload = {
        "type": "system_state",
        "state": serialize_model(system_state_to_out(state)),
    }
    await PLAN_BROADCASTER.broadcast(payload)


async def ensure_plan_snapshot(service: TaskService, serializer) -> dict[str, Any]:
    """Serialize the plan for initial WebSocket payloads."""

    return await serializer(service)
