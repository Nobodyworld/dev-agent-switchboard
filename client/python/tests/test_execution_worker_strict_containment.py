# ruff: noqa: S603, S607
"""Strict public-workload process-containment regression coverage."""

from __future__ import annotations

import os
import signal
import subprocess
import sys
import time
from pathlib import Path

import pytest

from client.python.execution_worker import runner as runner_module
from client.python.execution_worker.config import WorkerConfig
from client.python.execution_worker.containment import ContainmentLaunchError
from client.python.execution_worker.runner import run_step
from server.execution.registry import TrustedStep

_TOKEN = "worker-test-token"  # noqa: S105 - non-secret test fixture


def _config(tmp_path: Path) -> WorkerConfig:
    return WorkerConfig(
        base_url="http://localhost:8000",
        worker_id="strict-containment-worker",
        display_name="Strict containment worker",
        admin_token=_TOKEN,
        worker_root=tmp_path / "worker-root",
        evidence_root=tmp_path / "evidence-root",
        repositories={"Nobodyworld/example": tmp_path / "canonical"},
    )


def _step(*argv: str) -> TrustedStep:
    return TrustedStep(
        id="strict-step",
        title="Strict step",
        argv=argv,
        required=True,
        timeout_seconds=20,
        output_summary_limit=4096,
    )


def _run_strict(tmp_path: Path, step: TrustedStep):
    checkout = tmp_path / "checkout"
    checkout.mkdir()
    return run_step(
        step,
        checkout,
        tmp_path / "logs",
        _config(tmp_path),
        time.monotonic() + 20,
        strict_containment=True,
    )


@pytest.mark.skipif(
    not runner_module.sys.platform.startswith("linux") and os.name != "nt",
    reason="strict containment currently has Linux and Windows implementations",
)
def test_strict_host_runs_fixed_target_after_containment_setup(tmp_path: Path) -> None:
    result = _run_strict(
        tmp_path,
        _step(sys.executable, "-c", "print('strict-host-target-ran')"),
    )

    assert result.status == "succeeded"
    assert result.terminal_reason is None
    assert result.stdout_summary.strip() == "strict-host-target-ran"


def test_strict_host_launch_failure_never_executes_target(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    marker = tmp_path / "must-not-exist"

    def fail_before_payload(**_kwargs: object) -> object:
        raise ContainmentLaunchError("test host setup failure")

    monkeypatch.setattr(runner_module, "launch_strict_host", fail_before_payload)

    with pytest.raises(ContainmentLaunchError, match="test host setup failure"):
        _run_strict(
            tmp_path,
            _step(
                sys.executable,
                "-c",
                f"from pathlib import Path; Path({str(marker)!r}).write_text('ran')",
            ),
        )

    assert not marker.exists()


@pytest.mark.skipif(
    not runner_module.sys.platform.startswith("linux") and os.name != "nt",
    reason="strict containment currently has Linux and Windows implementations",
)
def test_strict_host_reaps_an_ordinary_background_descendant(tmp_path: Path) -> None:
    child_pid = tmp_path / "background-child.pid"
    child_ready = tmp_path / "background-child.ready"
    child_script = (
        "import os, pathlib, time; "
        f"pathlib.Path({str(child_pid)!r}).write_text(str(os.getpid())); "
        f"pathlib.Path({str(child_ready)!r}).write_text('ready'); "
        "time.sleep(30)"
    )
    parent_script = (
        "import pathlib, subprocess, sys, time; "
        f"subprocess.Popen([sys.executable, '-c', {child_script!r}]); "
        f"ready=pathlib.Path({str(child_ready)!r}); "
        "time.sleep(0.5); "
        "raise SystemExit(0 if ready.exists() else 1)"
    )

    result = _run_strict(tmp_path, _step(sys.executable, "-c", parent_script))

    assert result.status == "failed"
    assert result.terminal_reason == "unexpected_descendant_process"
    assert child_pid.is_file()
    process_id = child_pid.read_text(encoding="utf-8").strip()
    if os.name == "nt":
        listed = subprocess.run(
            ["tasklist", "/FI", f"PID eq {process_id}", "/NH"],
            check=False,
            shell=False,
            capture_output=True,
            text=True,
        )
        assert process_id not in listed.stdout
    else:
        with pytest.raises(ProcessLookupError):
            os.kill(int(process_id), 0)


@pytest.mark.skipif(
    not runner_module.sys.platform.startswith("linux") and os.name != "nt",
    reason="strict containment currently has Linux and Windows implementations",
)
def test_strict_timeout_uses_the_containment_boundary_not_legacy_tree_kill(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    target_pid = tmp_path / "timed-target.pid"

    def legacy_terminate_must_not_run(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("strict execution must not use legacy termination")

    monkeypatch.setattr(runner_module, "_terminate", legacy_terminate_must_not_run)
    checkout = tmp_path / "timeout-checkout"
    checkout.mkdir()
    result = run_step(
        _step(
            sys.executable,
            "-c",
            "import os, pathlib, time; "
            f"pathlib.Path({str(target_pid)!r}).write_text(str(os.getpid())); "
            "time.sleep(30)",
        ),
        checkout,
        tmp_path / "timeout-logs",
        _config(tmp_path),
        time.monotonic() + 1,
        strict_containment=True,
    )

    assert result.status == "timed_out"
    assert result.terminal_reason == "overall_timeout"
    assert target_pid.is_file()
    process_id = target_pid.read_text(encoding="utf-8").strip()
    if os.name == "nt":
        listed = subprocess.run(
            ["tasklist", "/FI", f"PID eq {process_id}", "/NH"],
            check=False,
            shell=False,
            capture_output=True,
            text=True,
        )
        assert process_id not in listed.stdout
    else:
        with pytest.raises(ProcessLookupError):
            os.kill(int(process_id), 0)


@pytest.mark.skipif(
    not runner_module.sys.platform.startswith("linux") and os.name != "nt",
    reason="strict containment currently has Linux and Windows implementations",
)
def test_monitoring_io_failure_terminates_before_output_is_consumed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A target-controlled log-tree error must not bypass strict teardown."""

    step = TrustedStep(
        id="monitoring-failure-step",
        title="Monitoring failure regression",
        argv=(sys.executable, "-c", "import time; time.sleep(30)"),
        required=True,
        timeout_seconds=20,
        output_summary_limit=4096,
        parser_kind="pytest",
    )

    def fail_directory_size(_path: Path) -> int:
        raise OSError("target-controlled log tree is unavailable")

    def parser_must_not_run(*_args: object, **_kwargs: object) -> object:
        raise AssertionError("monitoring failure output must not be parsed")

    monkeypatch.setattr(runner_module, "_directory_size", fail_directory_size)
    monkeypatch.setattr(runner_module, "parse_result", parser_must_not_run)
    result = _run_strict(tmp_path, step)

    assert result.status == "failed"
    assert result.terminal_reason == "descendant_cleanup_failed"
    assert result.parsed_result is None
    assert result.stdout_summary == ""
    assert result.stderr_summary == ""


@pytest.mark.skipif(
    not runner_module.sys.platform.startswith("linux"),
    reason="Linux subreaper regression; Windows Job Objects use a different boundary",
)
def test_strict_host_reaps_a_setsid_escape_before_returning(tmp_path: Path) -> None:
    child_pid = tmp_path / "setsid-child.pid"
    child_ready = tmp_path / "setsid-child.ready"
    child_script = (
        "import os, pathlib, time; "
        "os.setsid(); "
        f"pathlib.Path({str(child_pid)!r}).write_text(str(os.getpid())); "
        f"pathlib.Path({str(child_ready)!r}).write_text('ready'); "
        "time.sleep(30)"
    )
    parent_script = (
        "import pathlib, subprocess, sys, time; "
        f"subprocess.Popen([sys.executable, '-c', {child_script!r}]); "
        f"ready=pathlib.Path({str(child_ready)!r}); "
        "time.sleep(0.5); "
        "raise SystemExit(0 if ready.exists() else 1)"
    )

    result = _run_strict(
        tmp_path,
        _step(sys.executable, "-c", parent_script),
    )

    assert result.status == "failed"
    assert result.terminal_reason == "unexpected_descendant_process"
    assert child_pid.is_file()
    escaped_process = int(child_pid.read_text(encoding="utf-8"))
    with pytest.raises(ProcessLookupError):
        os.kill(escaped_process, 0)


@pytest.mark.skipif(
    not runner_module.sys.platform.startswith("linux"),
    reason="Linux hostile-host-signal regression",
)
def test_killed_linux_host_returns_without_parsing_unquiescent_target_output(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A target that kills its host quarantines the run instead of parsing logs."""

    target_pid = tmp_path / "host-kill-target.pid"
    child_pid = tmp_path / "host-kill-child.pid"
    child_ready = tmp_path / "host-kill-child.ready"
    child_script = (
        "import os, pathlib, time; os.setsid(); "
        f"pathlib.Path({str(child_pid)!r}).write_text(str(os.getpid())); "
        f"pathlib.Path({str(child_ready)!r}).write_text('ready'); "
        "time.sleep(30)"
    )
    target_script = (
        "import os, pathlib, signal, subprocess, sys, time\n"
        f"pathlib.Path({str(target_pid)!r}).write_text(str(os.getpid()))\n"
        f"subprocess.Popen([sys.executable, '-c', {child_script!r}])\n"
        f"ready = pathlib.Path({str(child_ready)!r})\n"
        "deadline = time.monotonic() + 5\n"
        "while not ready.exists() and time.monotonic() < deadline:\n"
        "    time.sleep(0.01)\n"
        "assert ready.exists()\n"
        "os.kill(os.getppid(), signal.SIGKILL)\n"
        "time.sleep(30)\n"
    )
    step = TrustedStep(
        id="host-kill-step",
        title="Host kill regression",
        argv=(sys.executable, "-c", target_script),
        required=True,
        timeout_seconds=20,
        output_summary_limit=4096,
        parser_kind="pytest",
    )

    def parser_must_not_run(*_args: object, **_kwargs: object) -> object:
        raise AssertionError("unquiescent target output must not be parsed")

    monkeypatch.setattr(runner_module, "parse_result", parser_must_not_run)
    try:
        result = _run_strict(tmp_path, step)
    finally:
        for path in (target_pid, child_pid):
            if not path.is_file():
                continue
            try:
                os.kill(int(path.read_text(encoding="utf-8")), signal.SIGKILL)
            except ProcessLookupError:
                pass

    assert result.status == "failed"
    assert result.terminal_reason == "descendant_cleanup_failed"
    assert result.parsed_result is None
    assert result.stdout_summary == ""
    assert result.stderr_summary == ""


@pytest.mark.skipif(
    not runner_module.sys.platform.startswith("linux"),
    reason="Linux strict-host signal-interruption regression",
)
def test_target_sigterm_cannot_interrupt_linux_host_cleanup(tmp_path: Path) -> None:
    """A target-directed TERM is never accepted as a successful step."""

    child_script = (
        "import os, pathlib, signal, time; os.setsid(); "
        "target_pid=os.getppid(); "
        "stat_path=f'/proc/{target_pid}/stat'; "
        "fields=pathlib.Path(stat_path).read_text()"
        ".rsplit(')', 1)[1].split(); "
        "os.kill(int(fields[1]), signal.SIGTERM); "
        "time.sleep(30)"
    )
    target_script = (
        "import subprocess, sys, time; "
        f"subprocess.Popen([sys.executable, '-c', {child_script!r}]); "
        "time.sleep(30)"
    )
    step = TrustedStep(
        id="host-signal-step",
        title="Host signal regression",
        argv=(sys.executable, "-c", target_script),
        required=True,
        timeout_seconds=20,
        output_summary_limit=4096,
        parser_kind="pytest",
    )

    result = _run_strict(tmp_path, step)

    assert result.status == "failed"
    assert result.terminal_reason == "unexpected_descendant_process"


def test_legacy_step_does_not_call_strict_host(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def should_not_run(**_kwargs: object) -> object:
        raise AssertionError("legacy work must not enter strict containment")

    monkeypatch.setattr(runner_module, "launch_strict_host", should_not_run)
    checkout = tmp_path / "legacy-checkout"
    checkout.mkdir()

    result = run_step(
        _step(sys.executable, "-c", "print('legacy')"),
        checkout,
        tmp_path / "legacy-logs",
        _config(tmp_path),
        time.monotonic() + 20,
    )

    assert result.status == "succeeded"
    assert result.stdout_summary.strip() == "legacy"
