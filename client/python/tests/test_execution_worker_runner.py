# ruff: noqa: S603, S607
"""Fixed-argv runtime, output, deadline, and cancellation coverage."""

from __future__ import annotations

import os
import subprocess
import sys
import threading
import time
from pathlib import Path, PurePosixPath
from unittest.mock import patch

import pytest

from client.python.execution_worker.config import WorkerConfig
from client.python.execution_worker.runner import (
    CancellationToken,
    OverallDeadlineExceededError,
    run_step,
)
from server.execution.registry import TrustedStep

_TOKEN = "worker-test-token"  # noqa: S105 - non-secret test fixture
_LARGE_LOG_BYTES = 100
_EXPECTED_REDACTED_PATHS = 2


def _config(tmp_path: Path, **overrides: object) -> WorkerConfig:
    values: dict[str, object] = {
        "base_url": "http://localhost:8000",
        "worker_id": "worker-1",
        "display_name": "Worker 1",
        "admin_token": _TOKEN,
        "worker_root": tmp_path / "worker-root",
        "evidence_root": tmp_path / "evidence-root",
        "repositories": {"Nobodyworld/example": tmp_path / "canonical"},
    }
    values.update(overrides)
    return WorkerConfig(**values)  # type: ignore[arg-type]


def _step(*argv: str, timeout: int = 10, limit: int = 4096) -> TrustedStep:
    return TrustedStep(
        id="safe-step",
        title="Safe step",
        argv=argv,
        required=True,
        timeout_seconds=timeout,
        output_summary_limit=limit,
    )


def test_deadline_expired_before_launch_does_not_call_popen(tmp_path: Path) -> None:
    checkout = tmp_path / "checkout"
    checkout.mkdir()
    with (
        patch("client.python.execution_worker.runner.subprocess.Popen") as popen,
        pytest.raises(OverallDeadlineExceededError),
    ):
        run_step(
            _step(sys.executable, "--version"),
            checkout,
            tmp_path / "logs",
            _config(tmp_path),
            time.monotonic() - 1,
        )
    popen.assert_not_called()


def test_summary_is_bounded_and_redacts_values(tmp_path: Path) -> None:
    checkout = tmp_path / "checkout"
    checkout.mkdir()
    config = _config(
        tmp_path,
        output_summary_limit=12,
        redacted_value_patterns=("worker-secret",),
    )
    step = _step(
        sys.executable,
        "-c",
        "print('worker-secret ' + 'x' * 200)",
        limit=64,
    )

    result = run_step(
        step,
        checkout,
        tmp_path / "logs",
        config,
        time.monotonic() + 10,
    )

    assert result.status == "succeeded"
    assert len(result.stdout_summary) <= config.output_summary_limit
    assert "worker-secret" not in result.stdout_summary
    assert result.summaries_truncated is True
    assert (tmp_path / "logs" / result.stdout_log).stat().st_size > _LARGE_LOG_BYTES


def test_summary_redacts_absolute_local_paths(tmp_path: Path) -> None:
    checkout = tmp_path / "checkout"
    checkout.mkdir()
    config = _config(tmp_path, output_summary_limit=4096)
    posix_path = f"/{PurePosixPath('var', 'tmp', 'secret.log')}"
    step = _step(
        sys.executable,
        "-c",
        f"print(r'C:\\worker\\secret.log'); print({posix_path!r})",
    )

    result = run_step(
        step,
        checkout,
        tmp_path / "logs",
        config,
        time.monotonic() + 10,
    )

    assert result.status == "succeeded"
    assert "C:\\worker" not in result.stdout_summary
    assert str(PurePosixPath("var", "tmp")) not in result.stdout_summary
    assert result.stdout_summary.count("[LOCAL_PATH]") == _EXPECTED_REDACTED_PATHS


def test_total_output_limit_terminates_fixed_process(tmp_path: Path) -> None:
    checkout = tmp_path / "checkout"
    checkout.mkdir()
    config = _config(tmp_path, total_output_limit=512, disk_limit_bytes=1024)
    step = _step(sys.executable, "-c", "print('x' * 100000)")

    result = run_step(
        step,
        checkout,
        tmp_path / "logs",
        config,
        time.monotonic() + 10,
    )

    assert result.status == "failed"
    assert result.terminal_reason == "total_output_limit_exceeded"


def test_cancellation_terminates_parent_and_child_processes(tmp_path: Path) -> None:
    checkout = tmp_path / "checkout"
    checkout.mkdir()
    child_pid = tmp_path / "child.pid"
    script = (
        "import pathlib, subprocess, sys, time; "
        "child=subprocess.Popen("
        "[sys.executable, '-c', 'import time; time.sleep(30)']); "
        f"pathlib.Path({str(child_pid)!r}).write_text(str(child.pid)); "
        "time.sleep(30)"
    )
    token = CancellationToken()
    timer = threading.Timer(0.2, lambda: token.cancel("test_cancel"))
    timer.start()
    try:
        result = run_step(
            _step(sys.executable, "-c", script, timeout=20),
            checkout,
            tmp_path / "logs",
            _config(tmp_path),
            time.monotonic() + 20,
            cancellation=token,
        )
    finally:
        timer.cancel()

    assert result.status == "cancelled"
    assert result.terminal_reason == "test_cancel"
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
