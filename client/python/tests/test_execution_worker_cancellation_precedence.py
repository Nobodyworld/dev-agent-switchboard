"""Authoritative control-plane cancellation must outrank local runner errors."""

from __future__ import annotations

from pathlib import Path

import pytest

from client.python.execution_worker.runner import CancellationToken
from client.python.execution_worker.worker import LocalWorker
from client.python.tests.execution_worker_test_support import work_order_payload
from client.python.tests.test_execution_worker_runtime import (
    _config,
    _FakeClient,
    _repository,
)
from server.execution.registry import get_trusted_manifest


@pytest.mark.parametrize("reason", ["ownership_lost", "server_terminal:cancelled"])
def test_authoritative_cancellation_outranks_runner_exception(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, reason: str
) -> None:
    canonical, sha = _repository(tmp_path)
    manifest = get_trusted_manifest("worker-smoke", "1")
    assert manifest is not None
    client = _FakeClient(work_order_payload(sha, manifest), manifest)
    worker = LocalWorker(_config(tmp_path, canonical), client)  # type: ignore[arg-type]

    def fail_after_cancellation(*_args: object, **kwargs: object) -> None:
        token = kwargs.get("cancellation")
        assert isinstance(token, CancellationToken)
        token.cancel(reason)
        raise RuntimeError("process-tree termination raced with cancellation")

    monkeypatch.setattr(
        "client.python.execution_worker.worker.run_step", fail_after_cancellation
    )

    assert worker.poll_once() is True

    assert client.completed == []
    assert worker._active_run_id is None
    assert worker._active_token is None


def test_runner_exception_without_cancellation_remains_failed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    canonical, sha = _repository(tmp_path)
    manifest = get_trusted_manifest("worker-smoke", "1")
    assert manifest is not None
    client = _FakeClient(work_order_payload(sha, manifest), manifest)
    worker = LocalWorker(_config(tmp_path, canonical), client)  # type: ignore[arg-type]

    def fail_without_cancellation(*_args: object, **_kwargs: object) -> None:
        raise RuntimeError("local runner failed")

    monkeypatch.setattr(
        "client.python.execution_worker.worker.run_step", fail_without_cancellation
    )

    assert worker.poll_once() is True

    assert len(client.completed) == 1
    assert client.completed[0]["status"] == "failed"
    assert client.completed[0]["terminal_reason"] == "worker_error:RuntimeError"
    assert worker._active_run_id is None
    assert worker._active_token is None
