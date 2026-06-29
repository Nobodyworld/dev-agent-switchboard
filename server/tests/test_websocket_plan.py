from __future__ import annotations

import asyncio
import json
from contextlib import asynccontextmanager, suppress

import httpx
import pytest
import uvicorn

try:
    import websockets
except ImportError:  # pragma: no cover - handled by skip
    pytest.skip(
        "websockets is required for websocket integration tests",
        allow_module_level=True,
    )  # type: ignore[arg-type]

from server.app import app
from server.middleware import get_current_rate_limit_middleware
from server.settings import reload_rate_limit_settings


async def _recv_json(websocket) -> dict[str, object]:
    raw = await asyncio.wait_for(websocket.recv(), timeout=2)
    return json.loads(raw)


@asynccontextmanager
async def run_app():
    config = uvicorn.Config(
        app,
        host="127.0.0.1",
        port=0,
        loop="asyncio",
        lifespan="on",
        log_level="error",
    )
    # TODO(P3, 3d) - Add coverage for TLS endpoints so we ensure secure websocket
    # upgrades continue to function.
    reload_rate_limit_settings()
    middleware = get_current_rate_limit_middleware()
    if middleware is not None:
        middleware.reset()
    sock = config.bind_socket()
    server = uvicorn.Server(config)
    task = asyncio.create_task(server.serve(sockets=[sock]))
    try:
        if hasattr(server.started, "wait"):
            await asyncio.wait_for(server.started.wait(), timeout=5)  # type: ignore[arg-type]
        else:
            for _ in range(50):
                if server.started:
                    break
                await asyncio.sleep(0.1)
            else:  # pragma: no cover - defensive timeout guard
                raise TimeoutError("Server failed to start")
        host, port = sock.getsockname()[:2]
        yield host, port
    finally:
        server.should_exit = True
        with suppress(asyncio.TimeoutError):
            await asyncio.wait_for(task, timeout=5)
        if not task.done():
            task.cancel()
            with suppress(asyncio.CancelledError):
                await task


@pytest.mark.asyncio
async def test_websocket_plan_broadcasts_version_increments():
    async with run_app() as (host, port):
        base_url = f"http://{host}:{port}"
        ws_url = f"ws://{host}:{port}/ws/plan"

        async with (
            httpx.AsyncClient(base_url=base_url) as client,
            websockets.connect(ws_url) as websocket,
        ):
            hello_raw = await asyncio.wait_for(websocket.recv(), timeout=2)
            hello = json.loads(hello_raw)
            assert hello["type"] == "plan_snapshot"
            assert "plan" in hello
            assert hello.get("version") == hello["plan"].get("version")
            assert "state" in hello
            assert "maintenance_mode" in hello["state"]

            create_resp = await client.post(
                "/api/tasks",
                json={"title": "first", "description": "", "depends_on": []},
            )
            create_resp.raise_for_status()

            version_msg_raw = await asyncio.wait_for(websocket.recv(), timeout=2)
            version_msg = json.loads(version_msg_raw)
            assert version_msg["type"] == "plan_version"
            first_version = version_msg["version"]

            register_resp = await client.post(
                "/api/agents",
                json={"agent_name": "agent"},
            )
            register_resp.raise_for_status()

            checkout_resp = await client.post(
                "/api/tasks/checkout",
                params={"agent_id": "agent"},
            )
            checkout_resp.raise_for_status()

            second_msg = json.loads(await asyncio.wait_for(websocket.recv(), timeout=2))
            assert second_msg["type"] == "plan_version"
            assert second_msg["version"] == first_version + 1
            if "plan" in second_msg:
                assert second_msg["plan"]["version"] == second_msg["version"]

            upload_resp = await client.put(
                "/api/files/docs/test.txt",
                content=b"hello world",
            )
            upload_resp.raise_for_status()

            third_msg = json.loads(await asyncio.wait_for(websocket.recv(), timeout=2))
            assert third_msg["type"] == "plan_version"
            assert third_msg["version"] == first_version + 2
            if "plan" in third_msg:
                assert third_msg["plan"]["version"] == third_msg["version"]


@pytest.mark.asyncio
async def test_websocket_plan_demonstrates_two_agent_dependency_flow():
    async with run_app() as (host, port):
        base_url = f"http://{host}:{port}"
        ws_url = f"ws://{host}:{port}/ws/plan"

        async with (
            httpx.AsyncClient(base_url=base_url) as client,
            websockets.connect(ws_url) as websocket,
        ):
            hello = await _recv_json(websocket)
            assert hello["type"] == "plan_snapshot"

            for agent_id in ("agent-one", "agent-two"):
                response = await client.post(
                    "/api/agents",
                    json={"agent_name": agent_id},
                )
                response.raise_for_status()

            task_a = await client.post(
                "/api/tasks",
                json={"title": "Task A", "description": "Ready", "depends_on": []},
            )
            task_a.raise_for_status()
            task_a_id = task_a.json()["id"]
            create_a_msg = await _recv_json(websocket)
            assert create_a_msg["type"] == "plan_version"

            task_b = await client.post(
                "/api/tasks",
                json={
                    "title": "Task B",
                    "description": "Depends on Task A",
                    "depends_on": [task_a_id],
                },
            )
            task_b.raise_for_status()
            task_b_id = task_b.json()["id"]
            create_b_msg = await _recv_json(websocket)
            assert create_b_msg["type"] == "plan_version"
            assert create_b_msg["version"] == create_a_msg["version"] + 1

            first_checkout = await client.post(
                "/api/tasks/checkout",
                params={"agent_id": "agent-one"},
            )
            first_checkout.raise_for_status()
            assert first_checkout.json()["task"]["id"] == task_a_id
            checkout_msg = await _recv_json(websocket)
            assert checkout_msg["type"] == "plan_version"

            blocked_checkout = await client.post(
                "/api/tasks/checkout",
                params={"agent_id": "agent-two"},
            )
            blocked_checkout.raise_for_status()
            assert blocked_checkout.json()["task"] is None
            assert blocked_checkout.json()["reason"] == "no_available_tasks"

            heartbeat = await client.post(
                f"/api/tasks/{task_a_id}/heartbeat",
                params={"agent_id": "agent-one"},
            )
            heartbeat.raise_for_status()
            assert heartbeat.json() == {"ok": True}

            completion = await client.post(
                f"/api/tasks/{task_a_id}/complete",
                params={"agent_id": "agent-one"},
                json={"notes": "done"},
            )
            completion.raise_for_status()
            assert completion.json()["ok"] is True
            completion_msg = await _recv_json(websocket)
            assert completion_msg["type"] == "plan_version"

            second_checkout = await client.post(
                "/api/tasks/checkout",
                params={"agent_id": "agent-two"},
            )
            second_checkout.raise_for_status()
            assert second_checkout.json()["task"]["id"] == task_b_id
            second_checkout_msg = await _recv_json(websocket)
            assert second_checkout_msg["type"] == "plan_version"

            final_plan = second_checkout_msg["plan"]
            tasks = {task["id"]: task for task in final_plan["tasks"]}
            assert tasks[task_a_id]["status"] == "completed"
            assert tasks[task_b_id]["status"] == "in_progress"
