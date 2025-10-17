"""FastAPI application entrypoint for Switchboard."""

from __future__ import annotations

import asyncio
import inspect
import logging
import os
from contextlib import asynccontextmanager, suppress
from typing import Any, Dict, List, Mapping, MutableMapping, Optional, Sequence

from fastapi import (
    Depends,
    FastAPI,
    HTTPException,
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
from jinja2 import Environment, FileSystemLoader
from sqlalchemy import delete, or_, select, text
from sqlalchemy import inspect as sa_inspect
from sqlalchemy.ext.asyncio import AsyncSession
from yaml import safe_dump

from .db import AsyncSessionLocal, Base, engine, get_session
from .file_store import ensure_root, full_path, put_file
from .execplan_registry import build_registry_index
from .instrumentation import (
    configure_logging,
    setup_logging,
    setup_metrics,
    setup_tracing,
)
from .middleware import RateLimitMiddleware
from .models import Agent, Lease, Task, TaskDependency
from .schema import (
    AgentIn,
    AgentRegistrationResponse,
    CheckoutOut,
    CompleteIn,
    CompleteResponse,
    FileUploadResponse,
    PlanOut,
    StatusResponse,
    TaskIn,
    TaskOut,
    TaskUpdate,
)
from .settings import get_rate_limit_settings
from .task_logic import (
    abandon as abandon_task,
    checkout_task,
    complete as complete_task,
    heartbeat as lease_heartbeat,
    increment_plan_version,
    plan_version,
    plan_version_snapshot,
    update_dependencies,
)

try:  # optional plan version helper
    from .task_logic import plan_version_counter  # type: ignore[attr-defined]
except ImportError:  # pragma: no cover - helper may be absent
    plan_version_counter = None  # type: ignore[assignment]

try:  # optional live file ETag helper
    from .file_store import etag_for_path  # type: ignore[attr-defined]
except ImportError:  # pragma: no cover - helper may be absent
    etag_for_path = None  # type: ignore[assignment]

configure_logging()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Create the database schema and storage roots on application startup."""

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

        def ensure_completed_notes_column(sync_conn):
            inspector = sa_inspect(sync_conn)
            columns = {column["name"] for column in inspector.get_columns("tasks")}
            if "completed_notes" not in columns:
                sync_conn.execute(
                    text("ALTER TABLE tasks ADD COLUMN completed_notes TEXT")
                )

        await conn.run_sync(ensure_completed_notes_column)

    ensure_root()
    yield


app = FastAPI(title="Switchboard", version="0.1.0", lifespan=lifespan)

setup_logging(app)
setup_tracing(app)

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

# Static UI
WEB_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "web"))
app.mount(
    "/static", StaticFiles(directory=os.path.join(WEB_ROOT, "static")), name="static"
)

templates = Environment(loader=FileSystemLoader(WEB_ROOT))

# WebSocket connections
logger = logging.getLogger(__name__)


PLAN_CONNECTIONS: List[WebSocket] = []
PLAN_SEND_TIMEOUT = 2.0


def _serialize_model(model: Any) -> Dict[str, Any]:
    """Return a dictionary representation for both Pydantic v1 and v2 models."""

    if hasattr(model, "model_dump"):
        return model.model_dump()  # type: ignore[no-any-return]
    return model.dict()  # type: ignore[no-any-return]


async def _resolve_plan_version(session: AsyncSession) -> int:
    """Resolve the current plan version using the optional counter helper when available."""

    if plan_version_counter:
        version_candidate = plan_version_counter(session)
        if inspect.isawaitable(version_candidate):
            return await version_candidate
        return version_candidate
    return await plan_version(session)


async def _dependency_map(
    session: AsyncSession, task_ids: Sequence[int]
) -> Mapping[int, List[int]]:
    """Return a mapping of task id to sorted dependency ids."""

    if not task_ids:
        return {}

    rows = await session.execute(
        select(TaskDependency.task_id, TaskDependency.depends_on_task_id)
        .where(TaskDependency.task_id.in_(task_ids))
        .order_by(TaskDependency.task_id, TaskDependency.depends_on_task_id)
    )
    dependencies: MutableMapping[int, List[int]] = {task_id: [] for task_id in task_ids}
    for task_id, depends_on_id in rows:
        dependencies.setdefault(task_id, []).append(depends_on_id)
    return dependencies


def _task_to_out(task: Task, dependencies: Mapping[int, Sequence[int]]) -> TaskOut:
    """Convert a task model into a serializable API response."""

    depends_on = list(dependencies.get(task.id, ()))
    return TaskOut(
        id=task.id,
        title=task.title,
        description=task.description,
        status=task.status,
        completed_notes=task.completed_notes,
        depends_on=depends_on,
    )


async def _tasks_to_out(session: AsyncSession, tasks: Sequence[Task]) -> List[TaskOut]:
    """Serialize multiple tasks with a single dependency query."""

    if not tasks:
        return []
    mapping = await _dependency_map(session, [task.id for task in tasks])
    return [_task_to_out(task, mapping) for task in tasks]


async def _task_out(session: AsyncSession, task: Task) -> TaskOut:
    return (await _tasks_to_out(session, [task]))[0]


async def _serialize_plan(session: AsyncSession) -> Dict[str, Any]:
    tasks = (await session.execute(select(Task).order_by(Task.id))).scalars().all()
    outs = await _tasks_to_out(session, tasks)
    version, updated_at = await plan_version_snapshot(session)
    plan = PlanOut(version=version, updated_at=updated_at, tasks=outs)
    return _serialize_model(plan)


async def _send_ws_payload(ws: WebSocket, payload: Dict[str, Any]) -> bool:
    try:
        await asyncio.wait_for(ws.send_json(payload), timeout=PLAN_SEND_TIMEOUT)
        return True
    except (asyncio.TimeoutError, WebSocketDisconnect, RuntimeError):
        return False
    except Exception as exc:  # pragma: no cover - defensive logging
        logger.warning("Failed to broadcast plan payload", exc_info=exc)
        return False


def _remove_ws_connection(ws: WebSocket) -> None:
    with suppress(ValueError):
        PLAN_CONNECTIONS.remove(ws)


async def broadcast_plan(
    version: Optional[int] = None,
    session: Optional[AsyncSession] = None,
    *,
    include_plan: bool = False,
    plan: Optional[Dict[str, Any]] = None,
    delta: Optional[Dict[str, Any]] = None,
) -> None:
    if version is None:
        if session is None:
            async with AsyncSessionLocal() as temp_session:
                version = await _resolve_plan_version(temp_session)
        else:
            version = await _resolve_plan_version(session)

    plan_payload: Optional[Dict[str, Any]] = plan
    if include_plan and plan_payload is None:
        if session is None:
            async with AsyncSessionLocal() as temp_session:
                plan_payload = await _serialize_plan(temp_session)
        else:
            plan_payload = await _serialize_plan(session)

    if plan_payload is not None and version is None:
        version = plan_payload.get("version")

    payload: Dict[str, Any] = {"type": "plan_version"}
    if version is not None:
        payload["version"] = version
    if plan_payload is not None:
        payload["plan"] = plan_payload
    if delta is not None:
        payload["delta"] = delta

    stale: List[WebSocket] = []
    for ws in list(PLAN_CONNECTIONS):
        ok = await _send_ws_payload(ws, payload)
        if not ok:
            stale.append(ws)

    for ws in stale:
        with suppress(Exception):
            await ws.close()
        _remove_ws_connection(ws)


@app.get("/", response_class=HTMLResponse)
async def index(request: Request, session: AsyncSession = Depends(get_session)):
    tmpl = templates.get_template("index.html")
    tasks = (await session.execute(select(Task).order_by(Task.id))).scalars().all()
    deps = (await session.execute(select(TaskDependency))).all()
    return tmpl.render(tasks=tasks, deps=deps)


# -------- Agents --------
@app.post("/api/agents", response_model=AgentRegistrationResponse)
async def register_agent(agent: AgentIn, session: AsyncSession = Depends(get_session)):
    exists = (
        await session.execute(select(Agent).where(Agent.agent_id == agent.agent_name))
    ).scalar_one_or_none()
    if exists is None:
        session.add(Agent(agent_id=agent.agent_name))
    await session.commit()
    return {"ok": True, "agent_id": agent.agent_name}


# -------- Tasks & Plan --------
@app.get("/api/tasks", response_model=List[TaskOut])
async def list_tasks(
    status: Optional[str] = None, session: AsyncSession = Depends(get_session)
):
    stmt = select(Task).order_by(Task.id)
    if status and status != "all":
        stmt = stmt.where(Task.status == status)
    tasks = (await session.execute(stmt)).scalars().all()
    return await _tasks_to_out(session, tasks)


@app.post("/api/tasks", response_model=TaskOut)
async def create_task(task: TaskIn, session: AsyncSession = Depends(get_session)):
    new_task = Task(title=task.title, description=task.description or "")
    session.add(new_task)
    await session.flush()

    unique_dependencies = {
        dep_id for dep_id in task.depends_on if dep_id != new_task.id
    }
    if unique_dependencies:
        rows = (
            await session.execute(
                select(Task.id).where(Task.id.in_(unique_dependencies))
            )
        ).all()
        found_ids = {row[0] for row in rows}
        missing = unique_dependencies - found_ids
        if missing:
            raise HTTPException(
                status_code=400, detail={"missing_dependencies": sorted(missing)}
            )
        for dep_id in unique_dependencies:
            session.add(TaskDependency(task_id=new_task.id, depends_on_task_id=dep_id))

    await session.flush()
    version = await increment_plan_version(session)
    await broadcast_plan(version=version, session=session, include_plan=True)
    await session.commit()
    return await _task_out(session, new_task)


@app.put("/api/tasks/{task_id}", response_model=TaskOut)
@app.patch("/api/tasks/{task_id}", response_model=TaskOut)
async def update_task(
    task_id: int, update: TaskUpdate, session: AsyncSession = Depends(get_session)
):
    task = await session.get(Task, task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="task_not_found")

    update_payload = update.model_dump(exclude_unset=True)
    if not update_payload:
        raise HTTPException(status_code=400, detail="no_updates_provided")

    if update.depends_on is not None:
        if task_id in update.depends_on:
            raise HTTPException(status_code=400, detail="task_cannot_depend_on_itself")
        if update.depends_on:
            rows = (
                await session.execute(
                    select(Task.id).where(Task.id.in_(set(update.depends_on)))
                )
            ).all()
            found_ids = {r[0] for r in rows}
            missing = set(update.depends_on) - found_ids
            if missing:
                raise HTTPException(
                    status_code=400,
                    detail={"missing_dependencies": sorted(missing)},
                )

    if update.title is not None:
        task.title = update.title
    if update.description is not None:
        task.description = update.description
    if update.status is not None:
        task.status = update.status
        if update.status in {"pending", "completed"}:
            await session.execute(delete(Lease).where(Lease.task_id == task.id))
    if update.depends_on is not None:
        await update_dependencies(session, task.id, update.depends_on)

    await session.merge(task)
    await session.flush()
    version = await increment_plan_version(session)
    await broadcast_plan(version=version, session=session)
    await session.commit()
    return await _task_out(session, task)


@app.delete("/api/tasks/{task_id}", response_model=StatusResponse)
async def delete_task(task_id: int, session: AsyncSession = Depends(get_session)):
    task = await session.get(Task, task_id)

    await session.execute(
        delete(TaskDependency).where(
            or_(
                TaskDependency.task_id == task_id,
                TaskDependency.depends_on_task_id == task_id,
            )
        )
    )
    await session.execute(delete(Lease).where(Lease.task_id == task_id))

    if task is not None:
        await session.delete(task)
        await session.flush()
        version = await increment_plan_version(session)
        await broadcast_plan(version=version, session=session, include_plan=True)

    await session.commit()
    return {"ok": True}


@app.post("/api/tasks/checkout", response_model=CheckoutOut)
async def checkout(
    agent_id: str,
    task_id: Optional[int] = None,
    session: AsyncSession = Depends(get_session),
):
    task, reason = await checkout_task(session, agent_id=agent_id, task_id=task_id)
    await session.flush()
    if task:
        version = await increment_plan_version(session)
        await broadcast_plan(version=version, session=session, include_plan=True)
    await session.commit()
    if task:
        return CheckoutOut(task=await _task_out(session, task))
    return CheckoutOut(task=None, reason=reason)


@app.post("/api/tasks/{task_id}/heartbeat", response_model=StatusResponse)
async def heartbeat(
    task_id: int, agent_id: str, session: AsyncSession = Depends(get_session)
):
    ok = await lease_heartbeat(session, agent_id=agent_id, task_id=task_id)
    await session.flush()
    await session.commit()
    return {"ok": ok}


@app.post("/api/tasks/{task_id}/complete", response_model=CompleteResponse)
async def complete(
    task_id: int,
    agent_id: str,
    body: CompleteIn,
    session: AsyncSession = Depends(get_session),
):
    ok, stored_notes = await complete_task(
        session,
        agent_id=agent_id,
        task_id=task_id,
        notes=body.notes,
    )
    await session.flush()
    if ok:
        version = await increment_plan_version(session)
        await broadcast_plan(version=version, session=session, include_plan=True)
    await session.commit()
    return {"ok": ok, "notes": stored_notes}


@app.post("/api/tasks/{task_id}/abandon", response_model=StatusResponse)
async def abandon(
    task_id: int, agent_id: str, session: AsyncSession = Depends(get_session)
):
    ok = await abandon_task(session, agent_id=agent_id, task_id=task_id)
    await session.flush()
    if ok:
        version = await increment_plan_version(session)
        await broadcast_plan(version=version, session=session, include_plan=True)
    await session.commit()
    return {"ok": ok}


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


def _etag_matches(etag: str, header_value: Optional[str]) -> bool:
    if not header_value:
        return False
    candidates = [tag.strip() for tag in header_value.split(",") if tag.strip()]
    return "*" in candidates or etag in candidates


@app.get("/api/execplans/index", name="execplan_index")
async def execplan_index(request: Request, session: AsyncSession = Depends(get_session)):
    desired_format = _negotiate_execplan_format(request)
    source_url = str(request.url)
    payload, etag, _, http_date = await build_registry_index(
        session, source_url=source_url
    )

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
    plan_dict = await _serialize_plan(session)
    if hasattr(PlanOut, "model_validate"):
        return PlanOut.model_validate(plan_dict)  # type: ignore[attr-defined]
    return PlanOut(**plan_dict)


# -------- WebSockets --------
@app.websocket("/ws/plan")
async def ws_plan(ws: WebSocket):
    await ws.accept()
    PLAN_CONNECTIONS.append(ws)
    try:
        async with AsyncSessionLocal() as session:
            plan_payload = await _serialize_plan(session)
        initial_payload = {
            "type": "plan_snapshot",
            "version": plan_payload.get("version"),
            "plan": plan_payload,
        }
        ok = await _send_ws_payload(ws, initial_payload)
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
        _remove_ws_connection(ws)


# -------- Files --------
@app.put("/api/files/{path:path}", response_model=FileUploadResponse)
async def put_live_file(
    path: str, request: Request, session: AsyncSession = Depends(get_session)
):
    data = await request.body()
    sha, size = await put_file(session, path, data)
    await session.flush()
    version = await increment_plan_version(session)
    await broadcast_plan(version=version, session=session, include_plan=True)
    await session.commit()
    return {"ok": True, "sha256": sha, "size": size, "url": f"/live/{path}"}


@app.get("/live/{path:path}")
async def get_live_file(path: str, request: Request):
    fp = full_path(path)
    if not os.path.exists(fp):
        return JSONResponse({"error": "not_found"}, status_code=404)

    etag_value: Optional[str] = None
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
            normalized_request_tags: List[str] = []
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
@app.get("/health", response_class=PlainTextResponse)
async def health():
    return "OK"


setup_metrics(app)
