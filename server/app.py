"""FastAPI application wiring for Switchboard's REST and WebSocket interfaces."""

# ruff: noqa: B008  # FastAPI relies on Depends() defaults for dependency injection.

from __future__ import annotations

import asyncio
import inspect
import json
import logging
import os
import warnings
from collections.abc import Mapping, Sequence
from contextlib import asynccontextmanager, suppress
from pathlib import Path
from typing import Any, Literal, TypedDict

from fastapi import (
    Depends,
    FastAPI,
    HTTPException,
    Query,
    Request,
    Response,
    WebSocket,
    WebSocketDisconnect,
)
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import (
    FileResponse,
    HTMLResponse,
    JSONResponse,
    PlainTextResponse,
)
from fastapi.staticfiles import StaticFiles
from jinja2 import Environment, FileSystemLoader, select_autoescape
from sqlalchemy import inspect as sa_inspect, select, text
from sqlalchemy.ext.asyncio import AsyncSession
from yaml import safe_dump

from .application import TaskService, build_task_service
from .application.exceptions import (
    MissingDependenciesError,
    SelfDependencyError,
    TaskNotFoundError,
)
from .db import AsyncSessionLocal, Base, engine, get_session
from .domain import Agent, TaskRecord
from .execplan_registry import build_registry_index
from .file_store import ensure_root, full_path, put_file
from .instrumentation import (
    configure_logging,
    setup_logging,
    setup_metrics,
    setup_tracing,
)
from .middleware import RateLimitMiddleware
from .schema import (
    AgentIn,
    AgentRegistrationResponse,
    CheckoutFailureReason,
    CheckoutOut,
    CompleteIn,
    CompleteResponse,
    FileUploadResponse,
    HealthStatus,
    LeaseSettingsOut,
    PlanOut,
    RateLimitSettingsOut,
    SettingsResponse,
    StatusResponse,
    TaskIn,
    TaskOut,
    TaskUpdate,
)
from .settings import get_lease_settings, get_rate_limit_settings, get_settings_bundle
from .task_status import TaskStatus
from .time_utils import utcnow_naive


def _build_task_service(session: AsyncSession) -> TaskService:
    """Compatibility wrapper returning :class:`TaskService` instances."""

    warnings.warn(
        "server.app._build_task_service is deprecated; import "
        "server.application.build_task_service instead.",
        DeprecationWarning,
        stacklevel=2,
    )
    return build_task_service(session)


def get_task_service(session: AsyncSession = Depends(get_session)) -> TaskService:
    """Return a task service wired with SQLAlchemy-backed repositories."""

    return build_task_service(session)

try:  # optional live file ETag helper
    from .file_store import etag_for_path  # type: ignore[attr-defined]
except ImportError:  # pragma: no cover - helper may be absent
    etag_for_path = None  # type: ignore[assignment]

configure_logging()


@asynccontextmanager
async def lifespan(_app: FastAPI):
    """Create the database schema and storage roots on application startup."""

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

        def ensure_completed_notes_column(sync_conn):
            inspector = sa_inspect(sync_conn)
            columns = {column["name"] for column in inspector.get_columns("tasks")}
            if "completed_notes" not in columns:
                # TODO - Move this schema migration into a formal Alembic revision
                # to avoid runtime DDL.
                sync_conn.execute(
                    text("ALTER TABLE tasks ADD COLUMN completed_notes TEXT")
                )

        await conn.run_sync(ensure_completed_notes_column)

    ensure_root()
    startup_logger = logging.getLogger(__name__)
    settings_bundle = get_settings_bundle()
    rate_settings = settings_bundle.rate_limit
    lease_settings = settings_bundle.lease
    startup_logger.info(
        "Loaded configuration: rate_limit_enabled=%s requests=%s window=%s lease_seconds=%s",
        rate_settings.enabled,
        rate_settings.requests,
        rate_settings.window_seconds,
        lease_settings.duration_seconds,
    )
    yield


app = FastAPI(title="Switchboard", version="0.1.0", lifespan=lifespan)

setup_logging(app)
setup_tracing(app)

# TODO - Restrict CORS origins to trusted hosts once deployment domains are known.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.add_middleware(
    RateLimitMiddleware,
    settings_provider=get_rate_limit_settings,
)


@app.get("/api/settings", response_model=SettingsResponse)
async def read_settings() -> SettingsResponse:
    """Return the current rate limit and lease configuration."""

    settings_bundle = get_settings_bundle()
    rate_settings = settings_bundle.rate_limit
    lease_settings = settings_bundle.lease
    return SettingsResponse(
        rate_limit=RateLimitSettingsOut(
            requests=rate_settings.requests,
            window_seconds=rate_settings.window_seconds,
            trusted_bypass=sorted(rate_settings.trusted_bypass),
            trusted_proxies=sorted(rate_settings.trusted_proxies),
            enabled=rate_settings.enabled,
        ),
        lease=LeaseSettingsOut(duration_seconds=lease_settings.duration_seconds),
    )


# Static UI
WEB_ROOT = Path(__file__).resolve().parent.parent / "web"
STATIC_ROOT = WEB_ROOT / "static"
app.mount("/static", StaticFiles(directory=str(STATIC_ROOT)), name="static")

templates = Environment(
    loader=FileSystemLoader(str(WEB_ROOT)),
    autoescape=select_autoescape(enabled_extensions=("html", "xml")),
)

# WebSocket connections
logger = logging.getLogger(__name__)


PLAN_SEND_TIMEOUT = 2.0


class PlanBroadcastPayload(TypedDict, total=False):
    """Typed WebSocket payload used when broadcasting plan updates."""

    type: Literal["plan_version", "plan_snapshot"]
    version: int
    plan: dict[str, Any]
    delta: dict[str, Any]


class PlanBroadcaster:
    """Manage WebSocket connections that should receive plan updates."""

    def __init__(self, *, send_timeout: float = PLAN_SEND_TIMEOUT) -> None:
        self._connections: set[WebSocket] = set()
        self._lock = asyncio.Lock()
        self._send_timeout = send_timeout

    async def add(self, ws: WebSocket) -> None:
        """Register a new WebSocket connection for future broadcasts."""

        async with self._lock:
            # TODO - Record connection metadata to help with targeted disconnects
            # and diagnostics.
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
            ok = await _send_ws_payload(ws, payload, timeout=self._send_timeout)
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


def _serialize_model(model: Any) -> dict[str, Any]:
    """Return a dictionary representation for both Pydantic v1 and v2 models."""

    if hasattr(model, "model_dump"):
        return model.model_dump(mode="json")  # type: ignore[no-any-return]
    if hasattr(model, "json"):
        return json.loads(model.json())  # type: ignore[no-any-return]
    return model.dict()  # type: ignore[no-any-return]


def _task_record_to_out(task: TaskRecord) -> TaskOut:
    """Convert a domain task record into the public schema."""

    return TaskOut(
        id=task.id,
        title=task.title,
        description=task.description,
        status=task.status,
        completed_notes=task.completed_notes,
        depends_on=list(task.depends_on),
    )


def _records_to_out(tasks: Sequence[TaskRecord]) -> list[TaskOut]:
    return [_task_record_to_out(task) for task in tasks]


async def _serialize_plan(service: TaskService) -> dict[str, Any]:
    tasks = await service.list_tasks()
    snapshot = await service.plan_version_snapshot()
    plan = PlanOut(
        version=snapshot.value,
        updated_at=snapshot.updated_at,
        tasks=_records_to_out(tasks),
    )
    return _serialize_model(plan)


async def _send_ws_payload(
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


async def _prepare_plan_payload(
    service: TaskService,
    *,
    version: int | None,
    include_plan: bool,
    plan: dict[str, Any] | None,
) -> tuple[int | None, dict[str, Any] | None]:
    """Resolve the plan version and optional payload for broadcasting."""

    resolved_version = version or await service.plan_version()
    plan_payload = plan
    if include_plan and plan_payload is None:
        plan_payload = await _serialize_plan(service)
    if plan_payload is not None and version is None:
        resolved_version = plan_payload.get("version", resolved_version)
    return resolved_version, plan_payload


async def broadcast_plan(
    version: int | None = None,
    session: AsyncSession | None = None,
    *,
    include_plan: bool = False,
    plan: dict[str, Any] | None = None,
    delta: dict[str, Any] | None = None,
    service: TaskService | None = None,
) -> None:
    """Broadcast the latest plan version to connected WebSocket listeners."""

    if service is None and session is None:
        async with AsyncSessionLocal() as temp_session:
            temp_service = build_task_service(temp_session)
            resolved_version, plan_payload = await _prepare_plan_payload(
                temp_service,
                version=version,
                include_plan=include_plan,
                plan=plan,
            )
            payload: PlanBroadcastPayload = {"type": "plan_version"}
            if resolved_version is not None:
                payload["version"] = resolved_version
            if plan_payload is not None:
                payload["plan"] = plan_payload
            if delta is not None:
                payload["delta"] = delta
            await PLAN_BROADCASTER.broadcast(payload)
        return

    local_service = service or build_task_service(session)
    resolved_version, plan_payload = await _prepare_plan_payload(
        local_service,
        version=version,
        include_plan=include_plan,
        plan=plan,
    )

    payload: PlanBroadcastPayload = {"type": "plan_version"}
    if resolved_version is not None:
        payload["version"] = resolved_version
    if plan_payload is not None:
        payload["plan"] = plan_payload
    if delta is not None:
        payload["delta"] = delta

    await PLAN_BROADCASTER.broadcast(payload)


@app.get("/", response_class=HTMLResponse)
async def index(_request: Request) -> str:
    """Render the operator dashboard."""

    tmpl = templates.get_template("index.html")
    return tmpl.render()


# -------- Agents --------
@app.post("/api/agents", response_model=AgentRegistrationResponse)
async def register_agent(
    agent: AgentIn,
    service: TaskService = Depends(get_task_service),
    session: AsyncSession = Depends(get_session),
):
    """Upsert the provided agent and echo the canonical registration payload."""

    await service.ensure_agent(Agent(agent_id=agent.agent_name))
    await session.commit()
    return {"ok": True, "agent_id": agent.agent_name}


# -------- Tasks & Plan --------
@app.get("/api/tasks", response_model=list[TaskOut])
async def list_tasks(
    status: TaskStatus | Literal["all"] | None = Query(
        None, description="Filter by status (use 'all' to disable filtering)."
    ),
    service: TaskService = Depends(get_task_service),
):
    """Return tasks matching the requested status filter."""

    records = await service.list_tasks(status=status)
    return _records_to_out(records)


@app.post("/api/tasks", response_model=TaskOut)
async def create_task(
    task: TaskIn,
    service: TaskService = Depends(get_task_service),
    session: AsyncSession = Depends(get_session),
):
    """Persist a new task and broadcast the resulting plan snapshot."""

    try:
        record = await service.create_task(
            title=task.title,
            description=task.description,
            depends_on=task.depends_on,
        )
    except MissingDependenciesError as exc:
        raise HTTPException(
            status_code=400, detail={"missing_dependencies": list(exc.missing_ids)}
        ) from exc

    await session.flush()
    version = await service.increment_plan_version()
    await broadcast_plan(version=version, service=service, include_plan=True)
    await session.commit()
    return _task_record_to_out(record)


@app.put("/api/tasks/{task_id}", response_model=TaskOut)
@app.patch("/api/tasks/{task_id}", response_model=TaskOut)
async def update_task(
    task_id: int,
    update: TaskUpdate,
    service: TaskService = Depends(get_task_service),
    session: AsyncSession = Depends(get_session),
):
    """Apply field updates to an existing task and propagate plan changes."""

    update_payload = update.model_dump(exclude_unset=True)
    if not update_payload:
        raise HTTPException(status_code=400, detail="no_updates_provided")

    try:
        record = await service.update_task(
            task_id,
            title=update.title,
            description=update.description,
            status=update.status,
            depends_on=update.depends_on,
        )
    except SelfDependencyError as exc:
        raise HTTPException(status_code=400, detail="task_cannot_depend_on_itself") from exc
    except MissingDependenciesError as exc:
        raise HTTPException(
            status_code=400, detail={"missing_dependencies": list(exc.missing_ids)}
        ) from exc
    except TaskNotFoundError as exc:
        raise HTTPException(status_code=404, detail="task_not_found") from exc

    await session.flush()
    version = await service.increment_plan_version()
    await broadcast_plan(version=version, service=service)
    await session.commit()
    return _task_record_to_out(record)


@app.delete("/api/tasks/{task_id}", response_model=StatusResponse)
async def delete_task(
    task_id: int,
    service: TaskService = Depends(get_task_service),
    session: AsyncSession = Depends(get_session),
):
    """Remove a task and its related edges, broadcasting plan updates."""

    deleted = await service.delete_task(task_id)
    await session.flush()
    if deleted:
        version = await service.increment_plan_version()
        await broadcast_plan(version=version, service=service, include_plan=True)
    await session.commit()
    return {"ok": True}


@app.post("/api/tasks/checkout", response_model=CheckoutOut)
async def checkout(
    agent_id: str,
    task_id: int | None = None,
    service: TaskService = Depends(get_task_service),
    session: AsyncSession = Depends(get_session),
):
    """Checkout a task for the agent, returning the task or failure reason."""

    result = await service.checkout(Agent(agent_id=agent_id), task_id=task_id)
    await session.flush()
    if result.task is not None:
        version = await service.increment_plan_version()
        await broadcast_plan(version=version, service=service, include_plan=True)
        await session.commit()
        return CheckoutOut(task=_task_record_to_out(result.task))
    await session.commit()
    reason = result.reason
    reason_enum = CheckoutFailureReason(reason) if reason else None
    return CheckoutOut(task=None, reason=reason_enum)


@app.post("/api/tasks/{task_id}/heartbeat", response_model=StatusResponse)
async def heartbeat(
    task_id: int,
    agent_id: str,
    service: TaskService = Depends(get_task_service),
    session: AsyncSession = Depends(get_session),
):
    """Extend the lease for ``task_id`` if the agent currently holds it."""

    result = await service.heartbeat(agent_id, task_id)
    await session.flush()
    await session.commit()
    return {"ok": result.ok}


@app.post("/api/tasks/{task_id}/complete", response_model=CompleteResponse)
async def complete(
    task_id: int,
    agent_id: str,
    body: CompleteIn,
    service: TaskService = Depends(get_task_service),
    session: AsyncSession = Depends(get_session),
):
    """Mark the task as completed if the lease permits it."""

    result = await service.complete(agent_id, task_id, notes=body.notes)
    await session.flush()
    if result.ok:
        version = await service.increment_plan_version()
        await broadcast_plan(version=version, service=service, include_plan=True)
    await session.commit()
    return {"ok": result.ok, "notes": result.notes}


@app.post("/api/tasks/{task_id}/abandon", response_model=StatusResponse)
async def abandon(
    task_id: int,
    agent_id: str,
    service: TaskService = Depends(get_task_service),
    session: AsyncSession = Depends(get_session),
):
    """Release a task lease and revert the task to ``pending`` if possible."""

    result = await service.abandon(agent_id, task_id)
    await session.flush()
    if result.ok:
        version = await service.increment_plan_version()
        await broadcast_plan(version=version, service=service, include_plan=True)
    await session.commit()
    return {"ok": result.ok}


def _negotiate_execplan_format(request: Request) -> str:
    """Return ``json`` or ``yaml`` based on query and ``Accept`` headers."""

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
    """Return ``True`` when the provided ``If-None-Match`` header matches ``etag``."""

    if not header_value:
        return False
    candidates = [tag.strip() for tag in header_value.split(",") if tag.strip()]
    return "*" in candidates or etag in candidates


@app.get("/api/execplans/index", name="execplan_index")
async def execplan_index(
    request: Request, session: AsyncSession = Depends(get_session)
):
    """Return the ExecPlan registry index in JSON or YAML format."""

    desired_format = _negotiate_execplan_format(request)
    source_url = str(request.url)
    payload, etag, _, http_date = await build_registry_index(
        session, source_url=source_url
    )
    await session.commit()

    headers = {"ETag": etag, "Last-Modified": http_date}

    if _etag_matches(etag, request.headers.get("if-none-match")):
        not_modified = Response(status_code=304, headers=headers)
        return not_modified

    if desired_format == "yaml":
        body = safe_dump(payload, sort_keys=False)
        if not body.endswith("\n"):
            body = f"{body}\n"
        return Response(content=body, media_type="application/yaml", headers=headers)

    return JSONResponse(payload, headers=headers)


@app.get("/api/plan", response_model=PlanOut)
async def get_plan(session: AsyncSession = Depends(get_session)):
    """Return the full task plan, including version metadata."""

    plan_dict = await _serialize_plan(session)
    if hasattr(PlanOut, "model_validate"):
        return PlanOut.model_validate(plan_dict)  # type: ignore[attr-defined]
    return PlanOut(**plan_dict)


# -------- WebSockets --------
@app.websocket("/ws/plan")
async def ws_plan(ws: WebSocket):
    """Stream plan updates to connected web clients via WebSocket."""

    await ws.accept()
    await PLAN_BROADCASTER.add(ws)
    try:
        async with AsyncSessionLocal() as session:
            plan_payload = await _serialize_plan(session)
        initial_payload: PlanBroadcastPayload = {
            "type": "plan_snapshot",
            "version": plan_payload.get("version", 0),
            "plan": plan_payload,
        }
        ok = await _send_ws_payload(ws, initial_payload, timeout=PLAN_SEND_TIMEOUT)
        if not ok:
            return
        while True:
            try:
                await ws.receive_text()
            except WebSocketDisconnect:
                break
            except Exception as exc:  # pragma: no cover - defensive logging
                logger.info("Plan websocket receive error", exc_info=exc)
                break
    except WebSocketDisconnect:
        pass
    except Exception as exc:  # pragma: no cover - defensive logging
        logger.error("Plan websocket failure", exc_info=exc)
    finally:
        await PLAN_BROADCASTER.discard(ws)


# -------- Files --------
@app.put("/api/files/{path:path}", response_model=FileUploadResponse)
async def put_live_file(
    path: str,
    request: Request,
    service: TaskService = Depends(get_task_service),
    session: AsyncSession = Depends(get_session),
):
    """Persist a live file upload and broadcast the resulting plan delta."""

    data = await request.body()
    write_result = await put_file(session, path, data)
    await session.flush()
    version = await service.increment_plan_version()
    await broadcast_plan(version=version, service=service, include_plan=True)
    await session.commit()
    return {
        "ok": True,
        "sha256": write_result.sha256,
        "size": write_result.size,
        "url": f"/live/{path}",
    }


@app.get("/live/{path:path}")
async def get_live_file(path: str, request: Request):
    """Return a stored live file with optional ETag-based caching."""

    fp = full_path(path)
    if not os.path.exists(fp):
        return JSONResponse({"error": "not_found"}, status_code=404)

    etag_value: str | None = None
    if etag_for_path:
        etag_candidate = etag_for_path(path)
        if inspect.isawaitable(etag_candidate):
            etag_candidate = await etag_candidate
        if etag_candidate:
            etag_value = etag_candidate

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


# -------- UI Helpers --------
@app.get("/health/live", response_model=HealthStatus)
async def health_live() -> dict[str, object]:
    """Report basic process liveness for infrastructure probes.

    Returns
    -------
    dict[str, object]
        Serialized :class:`HealthStatus` payload indicating process health.
    """

    return {"ok": True, "checks": {"process": True}, "version": app.version}


@app.get("/health/ready", response_model=HealthStatus)
async def health_ready(session: AsyncSession = Depends(get_session)):
    """Probe dependencies to determine whether the service is ready.

    Parameters
    ----------
    session:
        Database session used to confirm connectivity.

    Returns
    -------
    Union[dict[str, object], JSONResponse]
        Aggregated readiness payload; returns HTTP 503 when dependencies fail.
    """

    checks: dict[str, bool] = {}
    overall_ok = True

    try:
        await session.execute(select(1))
        checks["database"] = True
    except Exception:  # pragma: no cover - surfaced via readiness response
        checks["database"] = False
        overall_ok = False

    try:
        ensure_root()
        checks["storage"] = True
    except HTTPException:
        checks["storage"] = False
        overall_ok = False

    payload = {"ok": overall_ok, "checks": checks, "version": app.version}
    if not overall_ok:
        return JSONResponse(status_code=503, content=payload)
    return payload


@app.get("/health", response_class=PlainTextResponse)
async def health():
    """Return a simple OK response for legacy health checks."""

    return "OK"


setup_metrics(app)
