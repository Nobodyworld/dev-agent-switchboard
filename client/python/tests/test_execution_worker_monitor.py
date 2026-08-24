# ruff: noqa: S603, S607
"""Run-heartbeat fail-closed behavior and process-tree cancellation tests."""

from __future__ import annotations

import os
import subprocess
import sys
import time
from pathlib import Path

import pytest
from requests.exceptions import JSONDecodeError

from client.python.execution_worker.client import ExecutionOwnershipLostError
from client.python.execution_worker.runner import CancellationToken
from client.python.execution_worker.worker import LocalWorker, _RunMonitor
from client.python.tests.execution_worker_test_support import work_order_payload
from client.python.tests.test_execution_worker_runtime import (
    _config,
    _FakeClient,
    _repository,
)
from server.execution.enums import NetworkPolicy, RepositoryWritePolicy
from server.execution.registry import TrustedManifest, TrustedStep

_SECOND_CALL_COUNT = 2
_CANCELLATION_SECONDS = 4


class _MonitorClient:
    def __init__(self) -> None:
        self.worker_calls = 0
        self.run_calls = 0
        self.worker_error: OSError | None = None
        self.run_values: list[object] = [{"id": 7, "status": "running"}]

    def heartbeat_worker(self, *, status: str | None = None) -> dict[str, object]:
        assert status == "busy"
        self.worker_calls += 1
        if self.worker_error is not None:
            raise self.worker_error
        return {}

    def heartbeat_run(self, _run_id: int) -> object:
        self.run_calls += 1
        value = self.run_values[min(self.run_calls - 1, len(self.run_values) - 1)]
        if isinstance(value, BaseException):
            raise value
        return value


def _monitor(
    tmp_path: Path, client: _MonitorClient
) -> tuple[_RunMonitor, CancellationToken]:
    worker = LocalWorker(
        _config(tmp_path, tmp_path / "canonical"),
        client,  # type: ignore[arg-type]
    )
    token = CancellationToken()
    return _RunMonitor(worker, 7, time.monotonic() + 30, token), token


def test_worker_heartbeat_transport_failure_does_not_suppress_run_heartbeat(
    tmp_path: Path,
) -> None:
    client = _MonitorClient()
    client.worker_error = OSError("worker heartbeat unavailable")
    monitor, token = _monitor(tmp_path, client)

    monitor.tick()

    assert client.worker_calls == 1
    assert client.run_calls == 1
    assert token.cancelled is False


@pytest.mark.parametrize(
    "payload",
    [[], {"id": 7}, {"id": 7, "status": "future"}, {"id": 8, "status": "running"}],
)
def test_malformed_or_unsupported_run_heartbeat_cancels(
    tmp_path: Path, payload: object
) -> None:
    client = _MonitorClient()
    client.run_values = [payload]
    monitor, token = _monitor(tmp_path, client)

    monitor.tick()

    assert token.cancelled is True
    assert token.reason == "invalid_run_heartbeat"


def test_malformed_json_run_heartbeat_cancels(tmp_path: Path) -> None:
    client = _MonitorClient()
    client.run_values = [JSONDecodeError("Expecting value", "not-json", 0)]
    monitor, token = _monitor(tmp_path, client)

    monitor.tick()

    assert token.cancelled is True
    assert token.reason == "invalid_run_heartbeat"


def test_transient_run_heartbeat_failure_waits_for_next_tick(tmp_path: Path) -> None:
    client = _MonitorClient()
    client.run_values = [OSError("temporary"), {"id": 7, "status": "running"}]
    monitor, token = _monitor(tmp_path, client)

    monitor.tick()
    assert client.run_calls == 1
    assert token.cancelled is False

    monitor.tick()
    assert client.run_calls == _SECOND_CALL_COUNT
    assert token.cancelled is False


@pytest.mark.parametrize(
    ("value", "reason"),
    [
        (ExecutionOwnershipLostError(409), "ownership_lost"),
        ({"id": 7, "status": "cancelled"}, "server_terminal:cancelled"),
    ],
)
def test_ownership_loss_and_terminal_state_cancel_immediately(
    tmp_path: Path, value: object, reason: str
) -> None:
    client = _MonitorClient()
    client.run_values = [value]
    monitor, token = _monitor(tmp_path, client)

    monitor.tick()

    assert token.cancelled is True
    assert token.reason == reason


class _CancellingClient(_FakeClient):
    def __init__(
        self,
        order: dict[str, object],
        manifest: TrustedManifest,
        mode: str,
        child_pid: Path,
    ) -> None:
        super().__init__(order, manifest)
        self.mode = mode
        self.child_pid = child_pid
        self.cancellation_requested_at: float | None = None

    def heartbeat_run(self, _run_id: int) -> dict[str, object]:
        self.heartbeat_count += 1
        if self.heartbeat_count == 1 or not self.child_pid.is_file():
            return {"id": 7, "status": "running"}
        self.cancellation_requested_at = time.monotonic()
        if self.mode == "ownership":
            raise ExecutionOwnershipLostError(409)
        if self.mode == "terminal":
            return {"id": 7, "status": "cancelled"}
        return {"unexpected": True}


def _process_manifest(child_pid: Path) -> TrustedManifest:
    script = (
        "import pathlib, subprocess, sys, time; "
        "child=subprocess.Popen("
        "[sys.executable, '-c', 'import time; time.sleep(30)']); "
        f"pathlib.Path({str(child_pid)!r}).write_text(str(child.pid)); "
        "time.sleep(30)"
    )
    step = TrustedStep(
        id="process-tree",
        title="Fixed process-tree test",
        argv=(sys.executable, "-c", script),
        required=True,
        timeout_seconds=20,
    )
    return TrustedManifest(
        name="test-monitor",
        version="1",
        schema_version=1,
        description="fixed monitor cancellation manifest",
        registry_source="client/python/tests",
        required_capabilities={"repository_write": False},
        fixed_step_metadata=[step.safe_metadata()],
        environment_policy={},
        network_policy=NetworkPolicy.WORKER_RESTRICTED,
        repository_write_policy=RepositoryWritePolicy.READ_ONLY,
        timeout_seconds=20,
        artifact_declarations=[],
        execution_steps=(step,),
    )


@pytest.mark.parametrize("mode", ["ownership", "terminal", "malformed"])
def test_control_plane_cancellation_stops_parent_and_child_without_stale_success(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, mode: str
) -> None:
    canonical, sha = _repository(tmp_path)
    child_pid = tmp_path / "child.pid"
    manifest = _process_manifest(child_pid)
    client = _CancellingClient(
        work_order_payload(sha, manifest), manifest, mode, child_pid
    )
    monkeypatch.setattr(
        "client.python.execution_worker.worker.get_trusted_manifest",
        lambda _name, _version: manifest,
    )
    worker = LocalWorker(
        _config(
            tmp_path,
            canonical,
            execution_timeout_seconds=20,
            heartbeat_interval_seconds=0.1,
        ),
        client,  # type: ignore[arg-type]
    )

    assert worker.poll_once() is True

    assert client.cancellation_requested_at is not None
    assert time.monotonic() - client.cancellation_requested_at < _CANCELLATION_SECONDS
    assert child_pid.is_file()
    child = int(child_pid.read_text(encoding="utf-8"))
    if os.name != "nt":
        with pytest.raises(ProcessLookupError):
            os.kill(child, 0)
    else:
        listed = subprocess.run(
            ["tasklist", "/FI", f"PID eq {child}", "/NH"],
            check=False,
            shell=False,
            capture_output=True,
            text=True,
        )
        assert str(child) not in listed.stdout
    if mode in {"ownership", "terminal"}:
        assert client.completed == []
    else:
        assert len(client.completed) == 1
        assert client.completed[0]["status"] == "cancelled"
        assert client.completed[0]["terminal_reason"] == "invalid_run_heartbeat"
