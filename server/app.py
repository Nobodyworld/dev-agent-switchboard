
import os, datetime as dt
import inspect
import asyncio
from contextlib import asynccontextmanager, suppress
from typing import List, Optional, Dict, Any
from fastapi import FastAPI, Depends, UploadFile, WebSocket, WebSocketDisconnect, Request, Response
from contextlib import asynccontextmanager
from typing import List, Optional
from fastapi import FastAPI, Depends, UploadFile, WebSocket, WebSocketDisconnect, Request, Response, HTTPException
from fastapi.responses import HTMLResponse, FileResponse, JSONResponse, PlainTextResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from sqlalchemy import select, delete, or_, text
from sqlalchemy import inspect as sa_inspect
from sqlalchemy.ext.asyncio import AsyncSession
from jinja2 import Environment, FileSystemLoader

from .db import engine, Base, get_session, AsyncSessionLocal
from .models import Agent, Task, TaskDependency, Lease, FileEntry
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
from .task_logic import (
    checkout_task,
    heartbeat as lease_heartbeat,
    complete as complete_task,
    abandon as abandon_task,
    get_dependencies,
    update_dependencies,
    plan_version,
    increment_plan_version,
)
from .file_store import put_file, full_path, ensure_root

try:  # optional plan version helper
    from .task_logic import plan_version_counter  # type: ignore[attr-defined]
except ImportError:  # pragma: no cover - helper may be absent
    plan_version_counter = None  # type: ignore[assignment]

try:  # optional live file ETag helper
    from .file_store import etag_for_path  # type: ignore[attr-defined]
except ImportError:  # pragma: no cover - helper may be absent
    etag_for_path = None  # type: ignore[assignment]

@asynccontextmanager
async def lifespan(app: FastAPI):
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

        def ensure_completed_notes_column(sync_conn):
            inspector = sa_inspect(sync_conn)
            if not inspector.has_column("tasks", "completed_notes"):
                sync_conn.execute(text("ALTER TABLE tasks ADD COLUMN completed_notes TEXT"))

        await conn.run_sync(ensure_completed_notes_column)
    ensure_root()
    yield

app = FastAPI(title="Switchboard", version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Static UI
WEB_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "web"))
app.mount("/static", StaticFiles(directory=os.path.join(WEB_ROOT, "static")), name="static")

templates = Environment(loader=FileSystemLoader(WEB_ROOT))

# WebSocket connections
PLAN_CONNECTIONS: List[WebSocket] = []
PLAN_SEND_TIMEOUT = 2.0

async def _resolve_plan_version(session: AsyncSession) -> int:
    if plan_version_counter:
        version_candidate = plan_version_counter(session)
        if inspect.isawaitable(version_candidate):
            return await version_candidate
        return version_candidate
    return await plan_version(session)


async def _serialize_plan(session: AsyncSession) -> Dict[str, Any]:
    tasks = (await session.execute(select(Task))).scalars().all()
    outs = []
    for t in tasks:
        outs.append(task_to_out(t, await get_dependencies(session, t.id)))
    version = await _resolve_plan_version(session)
    plan = PlanOut(version=version, tasks=outs)
    return plan.model_dump() if hasattr(plan, "model_dump") else plan.dict()


async def _send_ws_payload(ws: WebSocket, payload: Dict[str, Any]) -> bool:
    try:
        await asyncio.wait_for(ws.send_json(payload), timeout=PLAN_SEND_TIMEOUT)
        return True
    except (asyncio.TimeoutError, WebSocketDisconnect, RuntimeError):
        return False
    except Exception:
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
):
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

    # Preserve the historical event type so existing web clients refresh
    # correctly without needing simultaneous UI changes. Additional payload
    # fields such as the serialized plan and optional deltas are still sent
    # for newer consumers that expect the richer structure.
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
    tasks = (await session.execute(select(Task))).scalars().all()
    deps = (await session.execute(select(TaskDependency))).all()
    return tmpl.render(tasks=tasks, deps=deps)

# -------- Agents --------
@app.post("/api/agents", response_model=AgentRegistrationResponse)
async def register_agent(agent: AgentIn, session: AsyncSession = Depends(get_session)):
    exists = (await session.execute(select(Agent).where(Agent.agent_id == agent.agent_name))).scalar_one_or_none()
    if exists is None:
        session.add(Agent(agent_id=agent.agent_name))
        await session.flush()
        await session.commit()
    return {"ok": True, "agent_id": agent.agent_name}

# -------- Tasks & Plan --------
def task_to_out(t: Task, deps: List[int]) -> TaskOut:
    return TaskOut(
        id=t.id,
        title=t.title,
        description=t.description,
        status=t.status,
        completed_notes=t.completed_notes,
        depends_on=deps,
    )

@app.get("/api/tasks", response_model=List[TaskOut])
async def list_tasks(status: Optional[str] = None, session: AsyncSession = Depends(get_session)):
    q = select(Task)
    if status:
        q = q.where(Task.status == status)
    tasks = (await session.execute(q)).scalars().all()
    out = []
    for t in tasks:
        out.append(task_to_out(t, await get_dependencies(session, t.id)))
    return out

@app.post("/api/tasks", response_model=TaskOut)
async def create_task(task: TaskIn, session: AsyncSession = Depends(get_session)):
    t = Task(title=task.title, description=task.description or "")
    session.add(t)
    await session.flush()
    for d in task.depends_on:
        session.add(TaskDependency(task_id=t.id, depends_on_task_id=d))
    await session.flush()
    version = await increment_plan_version(session)
    await broadcast_plan(version=version, session=session, include_plan=True)
    await session.commit()
    return task_to_out(t, await get_dependencies(session, t.id))


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
    return task_to_out(task, await get_dependencies(session, task.id))

@app.delete("/api/tasks/{task_id}", response_model=StatusResponse)
async def delete_task(task_id: int, session: AsyncSession = Depends(get_session)):
    existing = (await session.execute(select(Task.id).where(Task.id == task_id))).scalar_one_or_none()
    await session.execute(delete(TaskDependency).where(TaskDependency.task_id == task_id))
    await session.execute(
        delete(TaskDependency).where(
            # Remove both outbound and inbound edges to keep the dependency graph consistent.
            or_(
                TaskDependency.task_id == task_id,
                TaskDependency.depends_on_task_id == task_id,
            )
        )
    )
    await session.execute(delete(Task).where(Task.id == task_id))
    await session.execute(delete(Lease).where(Lease.task_id == task_id))
    if existing is not None:
        await session.flush()
        version = await increment_plan_version(session)
        await broadcast_plan(version=version, session=session, include_plan=True)
    await session.commit()
    return {"ok": True}

@app.post("/api/tasks/checkout", response_model=CheckoutOut)
async def checkout(agent_id: str, session: AsyncSession = Depends(get_session)):
    task, reason = await checkout_task(session, agent_id=agent_id)
    await session.flush()
    if task:
        version = await increment_plan_version(session)
        await broadcast_plan(version=version, session=session, include_plan=True)
    await session.commit()
    if task:
        return CheckoutOut(task=task_to_out(task, await get_dependencies(session, task.id)))
    return CheckoutOut(task=None, reason=reason)

@app.post("/api/tasks/{task_id}/heartbeat", response_model=StatusResponse)
async def heartbeat(task_id: int, agent_id: str, session: AsyncSession = Depends(get_session)):
    ok = await lease_heartbeat(session, agent_id=agent_id, task_id=task_id)
    await session.flush()
    await session.commit()
    return {"ok": ok}

@app.post("/api/tasks/{task_id}/complete", response_model=CompleteResponse)
async def complete(task_id: int, agent_id: str, body: CompleteIn, session: AsyncSession = Depends(get_session)):
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
async def abandon(task_id: int, agent_id: str, session: AsyncSession = Depends(get_session)):
    ok = await abandon_task(session, agent_id=agent_id, task_id=task_id)
    await session.flush()
    if ok:
        version = await increment_plan_version(session)
        await broadcast_plan(version=version, session=session, include_plan=True)
    await session.commit()
    return {"ok": ok}

@app.get("/api/plan", response_model=PlanOut)
async def get_plan(session: AsyncSession = Depends(get_session)):
    plan = await _serialize_plan(session)
    if hasattr(PlanOut, "model_validate"):
        return PlanOut.model_validate(plan)  # type: ignore[attr-defined]
    return PlanOut(**plan)

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
            except Exception:
                break
    except WebSocketDisconnect:
        pass
    finally:
        _remove_ws_connection(ws)

# -------- Files --------
@app.put("/api/files/{path:path}", response_model=FileUploadResponse)
async def put_live_file(path: str, request: Request, session: AsyncSession = Depends(get_session)):
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
        return JSONResponse({"error":"not_found"}, status_code=404)
    etag_value = None
    if etag_for_path:
        etag_candidate = etag_for_path(path)
        if inspect.isawaitable(etag_candidate):
            etag_candidate = await etag_candidate
        if etag_candidate:
            etag_value = etag_candidate

    if etag_value:
        incoming = request.headers.get("if-none-match")
        if incoming:
            etag_candidates = [tag.strip() for tag in incoming.split(",") if tag.strip()]
            normalized_request_tags = []
            for candidate in etag_candidates:
                if candidate == "*":
                    normalized_request_tags.append("*")
                    continue
                candidate_value = candidate[2:].strip() if candidate.startswith("W/") else candidate.strip()
                if not candidate_value:
                    continue
                if not (candidate_value.startswith('"') and candidate_value.endswith('"')):
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
