
import os, datetime as dt
import inspect
from typing import List, Optional
from fastapi import FastAPI, Depends, UploadFile, WebSocket, WebSocketDisconnect, Request, Response
from fastapi.responses import HTMLResponse, FileResponse, JSONResponse, PlainTextResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession
from jinja2 import Environment, FileSystemLoader

from .db import engine, Base, get_session
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
)
from .task_logic import checkout_task, heartbeat as lease_heartbeat, complete as complete_task, abandon as abandon_task, get_dependencies, plan_version
from .file_store import put_file, full_path, ensure_root

try:  # optional plan version helper
    from .task_logic import plan_version_counter  # type: ignore[attr-defined]
except ImportError:  # pragma: no cover - helper may be absent
    plan_version_counter = None  # type: ignore[assignment]

try:  # optional live file ETag helper
    from .file_store import etag_for_path  # type: ignore[attr-defined]
except ImportError:  # pragma: no cover - helper may be absent
    etag_for_path = None  # type: ignore[assignment]

app = FastAPI(title="Switchboard", version="0.1.0")

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

async def broadcast_plan():
    # lazy broadcast: plan version only
    for ws in list(PLAN_CONNECTIONS):
        try:
            await ws.send_json({"type":"plan_version"})
        except Exception:
            try:
                PLAN_CONNECTIONS.remove(ws)
            except ValueError:
                pass

@app.on_event("startup")
async def on_startup():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    ensure_root()

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
    return {"ok": True, "agent_id": agent.agent_name}

# -------- Tasks & Plan --------
def task_to_out(t: Task, deps: List[int]) -> TaskOut:
    return TaskOut(id=t.id, title=t.title, description=t.description, status=t.status, depends_on=deps)

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
    await broadcast_plan()
    return task_to_out(t, await get_dependencies(session, t.id))

@app.delete("/api/tasks/{task_id}", response_model=StatusResponse)
async def delete_task(task_id: int, session: AsyncSession = Depends(get_session)):
    await session.execute(delete(TaskDependency).where(TaskDependency.task_id == task_id))
    await session.execute(delete(Task).where(Task.id == task_id))
    await session.execute(delete(Lease).where(Lease.task_id == task_id))
    await broadcast_plan()
    return {"ok": True}

@app.post("/api/tasks/checkout", response_model=CheckoutOut)
async def checkout(agent_id: str, session: AsyncSession = Depends(get_session)):
    task, reason = await checkout_task(session, agent_id=agent_id)
    await session.flush()
    if task:
        await broadcast_plan()
        return CheckoutOut(task=task_to_out(task, await get_dependencies(session, task.id)))
    return CheckoutOut(task=None, reason=reason)

@app.post("/api/tasks/{task_id}/heartbeat", response_model=StatusResponse)
async def heartbeat(task_id: int, agent_id: str, session: AsyncSession = Depends(get_session)):
    ok = await lease_heartbeat(session, agent_id=agent_id, task_id=task_id)
    await session.flush()
    return {"ok": ok}

@app.post("/api/tasks/{task_id}/complete", response_model=CompleteResponse)
async def complete(task_id: int, agent_id: str, body: CompleteIn, session: AsyncSession = Depends(get_session)):
    ok = await complete_task(session, agent_id=agent_id, task_id=task_id)
    await session.flush()
    if ok:
        await broadcast_plan()
    return {"ok": ok, "notes": body.notes}

@app.post("/api/tasks/{task_id}/abandon", response_model=StatusResponse)
async def abandon(task_id: int, agent_id: str, session: AsyncSession = Depends(get_session)):
    ok = await abandon_task(session, agent_id=agent_id, task_id=task_id)
    await session.flush()
    if ok:
        await broadcast_plan()
    return {"ok": ok}

@app.get("/api/plan", response_model=PlanOut)
async def get_plan(session: AsyncSession = Depends(get_session)):
    tasks = (await session.execute(select(Task))).scalars().all()
    outs = []
    for t in tasks:
        outs.append(task_to_out(t, await get_dependencies(session, t.id)))
    if plan_version_counter:
        version_candidate = plan_version_counter(session)
        if inspect.isawaitable(version_candidate):
            version = await version_candidate
        else:
            version = version_candidate
    else:
        version = await plan_version(session)
    return PlanOut(version=version, tasks=outs)

# -------- WebSockets --------
@app.websocket("/ws/plan")
async def ws_plan(ws: WebSocket):
    await ws.accept()
    PLAN_CONNECTIONS.append(ws)
    try:
        await ws.send_json({"type":"hello","msg":"connected"})
        while True:
            _ = await ws.receive_text()
            await ws.send_json({"type":"pong"})
    except WebSocketDisconnect:
        pass
    finally:
        try:
            PLAN_CONNECTIONS.remove(ws)
        except ValueError:
            pass

# -------- Files --------
@app.put("/api/files/{path:path}", response_model=FileUploadResponse)
async def put_live_file(path: str, request: Request, session: AsyncSession = Depends(get_session)):
    data = await request.body()
    sha, size = await put_file(session, path, data)
    await session.flush()
    await broadcast_plan()
    return {"ok": True, "sha256": sha, "size": size, "url": f"/live/{path}"}

@app.get("/live/{path:path}")
async def get_live_file(path: str):
    fp = full_path(path)
    if not os.path.exists(fp):
        return JSONResponse({"error":"not_found"}, status_code=404)
    response = FileResponse(fp)
    if etag_for_path:
        etag_value = etag_for_path(path)
        if inspect.isawaitable(etag_value):
            etag_value = await etag_value
        if etag_value:
            response.headers.setdefault("ETag", etag_value)
    return response

# -------- UI Helpers --------
@app.get("/health", response_class=PlainTextResponse)
async def health():
    return "OK"
