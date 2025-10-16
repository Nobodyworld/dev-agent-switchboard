import asyncio
import json
from contextlib import asynccontextmanager, suppress

import httpx
import pytest
import uvicorn

websockets = pytest.importorskip("websockets")

from server.app import app


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
    sock = config.bind_socket()
    server = uvicorn.Server(config)
    task = asyncio.create_task(server.serve(sockets=[sock]))
    try:
        await asyncio.wait_for(server.started.wait(), timeout=5)
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

        async with httpx.AsyncClient(base_url=base_url) as client:
            async with websockets.connect(ws_url) as websocket:
                hello_raw = await asyncio.wait_for(websocket.recv(), timeout=2)
                hello = json.loads(hello_raw)
                assert hello == {"type": "hello", "msg": "connected"}

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
                assert second_msg == {"type": "plan_version", "version": first_version + 1}

                upload_resp = await client.put(
                    "/api/files/docs/test.txt",
                    content=b"hello world",
                )
                upload_resp.raise_for_status()

                third_msg = json.loads(await asyncio.wait_for(websocket.recv(), timeout=2))
                assert third_msg == {"type": "plan_version", "version": first_version + 2}

