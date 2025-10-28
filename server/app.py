"""Compatibility wrapper exporting the FastAPI application and route helpers."""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession
from starlette.requests import Request as StarletteRequest

from .api import AppConfig, create_app
from .api.plan import (
    PLAN_BROADCASTER,
    PLAN_SEND_TIMEOUT,
    PlanBroadcaster,
    PlanBroadcastPayload,
    broadcast_plan,
    broadcast_system_state,
    ensure_plan_snapshot,
    serialize_plan,
)
from .api.routers import (
    agents,
    configuration,
    files,
    observability,
    plan,
    system_state,
    tasks,
    ui,
)
from .db import AsyncSessionLocal
from .observability import collect_diagnostics
from .schema import SystemStateUpdateIn

app = create_app()


def _compat_request(method: str, path: str) -> StarletteRequest:
    """Build a minimal Starlette request for legacy call sites."""

    scope = {
        "type": "http",
        "method": method,
        "path": path,
        "app": app,
        "headers": [],
        "query_string": b"",
        "client": ("127.0.0.1", 0),
        "server": ("testserver", 80),
        "scheme": "http",
    }
    return StarletteRequest(scope)


# Re-export route callables for compatibility with existing imports and tests.
register_agent = agents.register_agent
list_tasks = tasks.list_tasks
read_task_analytics = tasks.read_task_analytics
create_task = tasks.create_task
update_task = tasks.update_task
delete_task = tasks.delete_task
checkout = tasks.checkout
heartbeat = tasks.heartbeat
complete = tasks.complete
abandon = tasks.abandon

read_settings = configuration.read_settings
read_configuration = configuration.read_configuration
read_diagnostics = configuration.read_diagnostics
read_telemetry = observability.read_observability_telemetry
read_observability_metrics = observability.read_observability_metrics
read_combined_health = observability.read_combined_health

read_system_state = system_state.read_system_state


async def mutate_system_state(
    payload: SystemStateUpdateIn,
    *,
    session: AsyncSession | None = None,
    request: StarletteRequest | None = None,
):
    """Preserve the legacy callable signature for direct imports."""

    request = request or _compat_request("PUT", "/api/system-state")
    if session is None:
        async with AsyncSessionLocal() as managed_session:
            return await system_state.mutate_system_state(
                payload,
                request=request,
                session=managed_session,
            )
    return await system_state.mutate_system_state(
        payload,
        request=request,
        session=session,
    )


execplan_index = plan.execplan_index
read_plan = plan.read_plan
get_plan = plan.read_plan
plan_ws = plan.plan_ws
read_activity_feed = plan.read_activity_feed

put_live_file = files.put_live_file
get_live_file = files.get_live_file

health_live = observability.health_live
health_ready = observability.health_ready
health = observability.health
read_observability_health = observability.read_observability_health
read_observability_overview = observability.read_observability_overview

index = ui.index

__all__ = [
    "PLAN_BROADCASTER",
    "PLAN_SEND_TIMEOUT",
    "AppConfig",
    "PlanBroadcastPayload",
    "PlanBroadcaster",
    "abandon",
    "app",
    "broadcast_plan",
    "broadcast_system_state",
    "checkout",
    "collect_diagnostics",
    "complete",
    "create_app",
    "create_task",
    "delete_task",
    "ensure_plan_snapshot",
    "execplan_index",
    "get_live_file",
    "get_plan",
    "health",
    "health_live",
    "health_ready",
    "index",
    "list_tasks",
    "mutate_system_state",
    "plan_ws",
    "put_live_file",
    "read_activity_feed",
    "read_combined_health",
    "read_configuration",
    "read_diagnostics",
    "read_observability_health",
    "read_observability_metrics",
    "read_observability_overview",
    "read_plan",
    "read_settings",
    "read_system_state",
    "read_task_analytics",
    "read_telemetry",
    "register_agent",
    "serialize_plan",
    "update_task",
]
