# ruff: noqa: S603, S607
"""Fixed-argv runtime, output, deadline, and cancellation coverage."""

from __future__ import annotations

import os
import signal
import subprocess
import sys
import threading
import time
from pathlib import Path, PurePosixPath
from unittest.mock import Mock, patch

import pytest

from client.python.execution_worker import runner as runner_module
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


def test_symbolic_python_step_uses_worker_interpreter() -> None:
    assert runner_module._runtime_argv(("python", "-m", "ruff")) == (
        sys.executable,
        "-m",
        "ruff",
    )
    assert runner_module._runtime_argv(("git", "status")) == ("git", "status")


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


def test_posix_group_observation_distinguishes_live_and_zombie(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        runner_module,
        "_linux_process_group_members",
        lambda _process_group_id: {101: "S", 102: "T", 103: "Z"},
    )
    alive, details = runner_module._process_group_observation(100)

    assert alive is True
    assert details == "pgid=100 live=101:S,102:T terminal=103:Z"

    monkeypatch.setattr(
        runner_module,
        "_linux_process_group_members",
        lambda _process_group_id: {103: "Z"},
    )
    alive, details = runner_module._process_group_observation(100)

    assert alive is False
    assert details == "pgid=100 terminal=103:Z"


def test_linux_process_stat_parser_handles_parentheses_in_command() -> None:
    parsed = runner_module._parse_linux_process_stat(
        "101 (worker ) helper) T 1 100 100 0 -1"
    )

    assert parsed == (100, "T")


def test_posix_group_wait_accepts_terminated_zombie_pending_reaping(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    observations = iter(
        [
            (True, "pgid=100 live=101:S"),
            (False, "pgid=100 terminal=101:Z"),
            (False, "pgid=100 members=none"),
        ]
    )
    clock = iter([10.0, 10.0])
    pauses: list[float] = []
    monkeypatch.setattr(
        runner_module,
        "_process_group_observation",
        lambda _process_group_id: next(observations),
    )
    monkeypatch.setattr(runner_module.time, "monotonic", lambda: next(clock))
    monkeypatch.setattr(runner_module.time, "sleep", pauses.append)

    runner_module._wait_for_process_group_exit(100, 1.0)

    assert pauses == [runner_module._PROCESS_GROUP_POLL_SECONDS]
    assert next(observations) == (False, "pgid=100 members=none")


def test_posix_group_wait_reports_live_member_after_deadline(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    clock = iter([10.0, 10.0, 11.0])
    monkeypatch.setattr(
        runner_module,
        "_process_group_observation",
        lambda _process_group_id: (True, "pgid=100 live=101:S"),
    )
    monkeypatch.setattr(runner_module.time, "monotonic", lambda: next(clock))
    monkeypatch.setattr(runner_module.time, "sleep", lambda _seconds: None)

    with pytest.raises(
        RuntimeError,
        match=r"POSIX descendant process termination failed \(pgid=100 live=101:S\)",
    ):
        runner_module._wait_for_process_group_exit(100, 1.0)


def test_posix_termination_sends_term_then_one_kill(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    process = Mock(spec=subprocess.Popen)
    process.pid = 100
    signals: list[int | signal.Signals] = []
    observations = iter(
        [
            (True, "pgid=100 live=101:S"),
            (False, "pgid=100 terminal=101:Z"),
        ]
    )
    monkeypatch.setattr(
        runner_module.os,
        "killpg",
        lambda _process_group_id, signal_number: signals.append(signal_number),
        raising=False,
    )
    monkeypatch.setattr(
        runner_module, "_wait_for_parent", lambda _process, _grace: True
    )
    monkeypatch.setattr(
        runner_module,
        "_process_group_observation",
        lambda _process_group_id: next(observations),
    )

    runner_module._terminate_posix(process, 1.0)

    assert signals == [signal.SIGTERM, getattr(signal, "SIGKILL", signal.SIGTERM)]


def test_cancellation_terminates_parent_and_child_processes(tmp_path: Path) -> None:
    checkout = tmp_path / "checkout"
    checkout.mkdir()
    child_pid = tmp_path / "child.pid"
    child_ready = tmp_path / "child.ready"
    parent_pid = tmp_path / "parent.pid"
    child_script = (
        "import pathlib, signal, time; "
        "signal.signal(signal.SIGTERM, signal.SIG_IGN); "
        f"pathlib.Path({str(child_ready)!r}).write_text('ready'); "
        "time.sleep(30)"
    )
    script = (
        "import os, pathlib, subprocess, sys, time; "
        f"pathlib.Path({str(parent_pid)!r}).write_text(str(os.getpid())); "
        f"child=subprocess.Popen([sys.executable, '-c', {child_script!r}]); "
        f"pathlib.Path({str(child_pid)!r}).write_text(str(child.pid)); "
        "time.sleep(30)"
    )
    token = CancellationToken()

    def cancel_when_child_is_ready() -> None:
        deadline = time.monotonic() + 5
        while not child_ready.is_file() and time.monotonic() < deadline:
            time.sleep(0.01)
        reason = "test_cancel" if child_ready.is_file() else "child_setup_timeout"
        token.cancel(reason)

    cancellation_thread = threading.Thread(
        target=cancel_when_child_is_ready,
        name="runner-test-cancellation",
        daemon=True,
    )
    cancellation_thread.start()
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
        cancellation_thread.join(timeout=5)

    assert result.status == "cancelled"
    assert result.terminal_reason == "test_cancel"
    assert child_pid.is_file()
    assert parent_pid.is_file()
    child = int(child_pid.read_text(encoding="utf-8"))
    parent = int(parent_pid.read_text(encoding="utf-8"))
    if sys.platform.startswith("linux"):
        members = runner_module._linux_process_group_members(parent)
        assert members is not None
        assert all(
            state in runner_module._LINUX_TERMINAL_PROCESS_STATES
            for state in members.values()
        )
    elif os.name != "nt":
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
