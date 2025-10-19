import asyncio
from collections.abc import AsyncGenerator
from typing import Any

import pytest

from server.app import PLAN_BROADCASTER, PlanBroadcastPayload

# TODO - Add tests that simulate slow websocket consumers to verify broadcaster
# backpressure handling.


class _RecordingWebSocket:
    def __init__(self) -> None:
        self.messages: list[dict[str, Any]] = []
        self.close_calls = 0

    async def send_json(self, payload: dict[str, Any]) -> None:
        await asyncio.sleep(0)
        self.messages.append(payload)

    async def close(self) -> None:
        self.close_calls += 1


class _FailingWebSocket:
    def __init__(self) -> None:
        self.send_attempts = 0
        self.closed = False

    async def send_json(self, _payload: dict[str, Any]) -> None:
        self.send_attempts += 1
        await asyncio.sleep(0)
        raise RuntimeError("send failed")

    async def close(self) -> None:
        self.closed = True


@pytest.fixture(autouse=True)
async def reset_plan_broadcaster() -> AsyncGenerator[None, None]:
    await PLAN_BROADCASTER.close_all()
    yield
    await PLAN_BROADCASTER.close_all()


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.mark.anyio
async def test_broadcast_prunes_failed_websocket() -> None:
    failing = _FailingWebSocket()
    await PLAN_BROADCASTER.add(failing)  # type: ignore[arg-type]

    payload: PlanBroadcastPayload = {"type": "plan_version", "version": 1}
    await PLAN_BROADCASTER.broadcast(payload)

    assert failing.closed is True
    assert PLAN_BROADCASTER.connection_count() == 0
    assert failing.send_attempts == 1


@pytest.mark.anyio
async def test_broadcast_keeps_successful_connections() -> None:
    failing = _FailingWebSocket()
    healthy = _RecordingWebSocket()
    await PLAN_BROADCASTER.add(failing)  # type: ignore[arg-type]
    await PLAN_BROADCASTER.add(healthy)  # type: ignore[arg-type]

    payload: PlanBroadcastPayload = {"type": "plan_version", "version": 99}
    await PLAN_BROADCASTER.broadcast(payload)

    assert failing.closed is True
    assert PLAN_BROADCASTER.connection_count() == 1
    assert healthy.messages == [payload]
    assert healthy.close_calls == 0
