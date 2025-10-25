import asyncio

import pytest
from fastapi.testclient import TestClient

from server.app import PLAN_BROADCASTER, app, broadcast_plan

HTTP_OK = 200
TEST_PLAN_VERSION = 42


@pytest.fixture(autouse=True)
async def clear_ws_connections():
    await PLAN_BROADCASTER.close_all()
    yield
    await PLAN_BROADCASTER.close_all()


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.mark.anyio
async def test_ws_plan_receives_snapshot_and_updates():
    with TestClient(app) as client:
        with client.websocket_connect("/ws/plan") as websocket:
            initial = websocket.receive_json()
            assert initial["type"] == "plan_snapshot"
            assert initial["plan"]["tasks"] == []
            assert initial["version"] == initial["plan"]["version"]
            assert "state" in initial
            assert "maintenance_mode" in initial["state"]

            response = client.post(
                "/api/tasks",
                json={"title": "ws-task", "description": "", "depends_on": []},
            )
            assert response.status_code == HTTP_OK

            update = websocket.receive_json()
            assert update["type"] == "plan_version"
            assert update["version"] > initial["version"]
            assert len(update["plan"]["tasks"]) == 1
            assert update["plan"]["tasks"][0]["title"] == "ws-task"

        for _ in range(5):
            if PLAN_BROADCASTER.connection_count() == 0:
                break
            await asyncio.sleep(0)
        assert PLAN_BROADCASTER.connection_count() == 0


@pytest.mark.anyio
async def test_broadcast_plan_can_include_delta_payload():
    with TestClient(app) as client:
        with client.websocket_connect("/ws/plan") as websocket:
            _ = websocket.receive_json()

            delta = {"changed": [1, 2, 3]}
            await broadcast_plan(version=TEST_PLAN_VERSION, delta=delta)

            message = websocket.receive_json()
            assert message["type"] == "plan_version"
            assert message["version"] == TEST_PLAN_VERSION
            assert message["delta"] == delta

        for _ in range(5):
            if PLAN_BROADCASTER.connection_count() == 0:
                break
            await asyncio.sleep(0)
        assert PLAN_BROADCASTER.connection_count() == 0
