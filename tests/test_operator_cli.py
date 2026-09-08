"""Operator CLI channel, approval, stored compatibility and safe error contracts."""

from __future__ import annotations

import io
import json
import subprocess
import sys
from pathlib import Path

import pytest
from scripts import dev

from client.python.execution_operator import lifecycle, readiness
from client.python.execution_operator.config import OperatorLifecycleConfig
from client.python.execution_operator.diagnostics import operator_diagnostic
from client.python.execution_operator.models import OperatorLifecycleFailure
from client.python.execution_operator.progress import ProgressEvent
from client.python.execution_operator.runtime import write_report
from client.python.tests.execution_operator_test_support import make_operator_report
from client.python.tests.test_execution_operator_corrections import _config, _runtime
from client.python.tests.test_execution_operator_readiness import (
    ready_config as ready_config,  # noqa: PLC0414 - shared pytest fixture
)


def _use_config(monkeypatch: pytest.MonkeyPatch, root: Path) -> OperatorLifecycleConfig:
    config = _config(root)
    monkeypatch.setattr(OperatorLifecycleConfig, "from_file", lambda _path: config)
    return config


@pytest.mark.parametrize(
    "command",
    ["validation-preflight", "validation-lifecycle", "inspect-validation-runtime"],
)
def test_missing_input_is_one_json_object_without_private_values(
    tmp_path: Path, command: str
) -> None:
    private = tmp_path / "private-missing-input"
    args = (
        [str(private)]
        if command == "inspect-validation-runtime"
        else ["--config", str(private)]
    )
    result = subprocess.run(  # noqa: S603 - fixed repository CLI
        [sys.executable, "scripts/dev.py", command, *args, "--format", "json"],
        cwd=dev.REPOSITORY_ROOT,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert result.returncode == 1
    payload = json.loads(result.stdout)
    assert isinstance(payload, dict)
    assert str(private) not in result.stdout + result.stderr
    assert "Traceback" not in result.stdout + result.stderr


@pytest.mark.parametrize(
    "command",
    ["validation-preflight", "validation-lifecycle", "inspect-validation-runtime"],
)
def test_machine_argument_errors_are_bounded_json(command, capsys) -> None:
    with pytest.raises(SystemExit) as error:
        dev.main([command, "--format", "json", "--unknown-private-value"])
    assert error.value.code == 1
    captured = capsys.readouterr()
    assert json.loads(captured.out)["reason"] == "invalid_arguments"
    assert "unknown-private-value" not in captured.out + captured.err


@pytest.mark.parametrize(
    ("flags", "expected"),
    [
        ([], [False, False]),
        (["--approve-fresh"], [True, False]),
        (["--approve-reuse"], [False, True]),
        (["--approve-fresh", "--approve-reuse"], [True, True]),
    ],
)
def test_noninteractive_approvals_remain_independent(
    tmp_path, monkeypatch, capsys, flags, expected
) -> None:
    config = _use_config(monkeypatch, tmp_path)
    monkeypatch.setattr(sys, "stdin", io.StringIO())
    decisions = []

    def run(_config, *, approval):
        for phase in ("fresh", "reuse"):
            decisions.append(
                approval(
                    phase, f"{phase}:{config.repository_full_name}@{config.target_sha}"
                )
            )
        raise OperatorLifecycleFailure("fresh_approval_denied")

    monkeypatch.setattr(lifecycle, "run_validation_lifecycle", run)
    with pytest.raises(SystemExit):
        dev.main(["validation-lifecycle", "--config", "unused", *flags])
    captured = capsys.readouterr()
    assert decisions == expected
    assert json.loads(captured.out)["reason"] == "fresh_approval_denied"
    assert "Approval required" in captured.err
    assert "Approval required" not in captured.out


def test_interactive_prompt_uses_stderr_and_exact_identity(
    tmp_path, monkeypatch, capsys
) -> None:
    config = _use_config(monkeypatch, tmp_path)
    identity = f"fresh:{config.repository_full_name}@{config.target_sha}"
    stream = io.StringIO(f"APPROVE {identity}\n")
    monkeypatch.setattr(stream, "isatty", lambda: True)
    monkeypatch.setattr(sys, "stdin", stream)
    report = make_operator_report()

    def run(_config, *, approval):
        assert approval("fresh", identity)
        return report

    monkeypatch.setattr(lifecycle, "run_validation_lifecycle", run)
    dev.main(["validation-lifecycle", "--config", "unused", "--format", "json"])
    captured = capsys.readouterr()
    assert json.loads(captured.out) == report.as_dict()
    assert "Type 'APPROVE " in captured.err
    assert "APPROVE" not in captured.out


def test_progress_does_not_pollute_machine_report(
    tmp_path, monkeypatch, capsys
) -> None:
    _use_config(monkeypatch, tmp_path)
    report = make_operator_report()

    def run(_config, *, approval, observer):
        assert callable(approval)
        observer(ProgressEvent(sequence=1, event="preflight_started"))
        return report

    monkeypatch.setattr(lifecycle, "run_validation_lifecycle", run)
    dev.main(["validation-lifecycle", "--config", "unused", "--progress"])
    captured = capsys.readouterr()
    assert json.loads(captured.out) == report.as_dict()
    assert "preflight_started" in captured.err


class BrokenOutput(io.StringIO):
    def write(self, _text):
        raise OSError("private output failure")


def test_broken_prompt_cannot_grant_interactive_approval(tmp_path, monkeypatch) -> None:
    config = _use_config(monkeypatch, tmp_path)
    monkeypatch.setattr(sys, "stderr", BrokenOutput())
    stream = io.StringIO("should never be read")
    monkeypatch.setattr(stream, "isatty", lambda: True)
    monkeypatch.setattr(sys, "stdin", stream)

    def run(_config, *, approval):
        assert not approval(
            "fresh", f"fresh:{config.repository_full_name}@{config.target_sha}"
        )
        assert stream.tell() == 0
        raise OperatorLifecycleFailure("fresh_approval_denied")

    monkeypatch.setattr(lifecycle, "run_validation_lifecycle", run)
    with pytest.raises(SystemExit):
        dev.main(["validation-lifecycle", "--config", "unused"])


def test_output_failure_occurs_after_lifecycle_cleanup(tmp_path, monkeypatch) -> None:
    _use_config(monkeypatch, tmp_path)
    stopped = []

    def run(_config, *, approval):
        assert callable(approval)
        stopped.append(True)
        return make_operator_report()

    monkeypatch.setattr(lifecycle, "run_validation_lifecycle", run)
    monkeypatch.setattr(sys, "stdout", BrokenOutput())
    with pytest.raises(SystemExit) as error:
        dev.main(["validation-lifecycle", "--config", "unused"])
    assert error.value.code == 1
    assert stopped == [True]


@pytest.mark.parametrize("output_format", ["human", "json"])
def test_stored_inspection_preserves_report_and_labels_scope(
    tmp_path, capsys, output_format
) -> None:
    layout, report = _runtime(tmp_path)
    write_report(layout, report, maximum_bytes=16384)
    before = {
        path: (path.read_bytes(), path.stat().st_mtime_ns)
        for path in layout.root.rglob("*")
        if path.is_file()
    }
    dev.main(
        ["inspect-validation-runtime", str(layout.root), "--format", output_format]
    )
    captured = capsys.readouterr()
    if output_format == "json":
        assert json.loads(captured.out) == report.as_dict()
        assert "stored state only; live evidence not reverified" in captured.err
    else:
        assert "stored state only; live evidence not reverified" in captured.out
    after = {
        path: (path.read_bytes(), path.stat().st_mtime_ns)
        for path in layout.root.rglob("*")
        if path.is_file()
    }
    assert after == before


@pytest.mark.parametrize(
    "reason",
    [
        "admin_token_missing",
        "worker_capability_mismatch",
        "source_checkout_dirty",
        "source_origin_mismatch",
        "runtime_root_already_exists",
        "loopback_port_occupied",
        "manifest_timeout_exceeds_worker_budget",
        "terminal_timeout_below_manifest_budget",
    ],
)
def test_diagnostics_retain_known_actionable_categories(reason) -> None:
    diagnostic = operator_diagnostic(reason)
    assert diagnostic.reason == reason
    assert 20 < len(diagnostic.guidance) < 256


@pytest.mark.parametrize(
    "value",
    [
        "private_secret_value",
        "file:///private/input",
        "https://private.example/raw",
        "invalid_configuration:private-value",
    ],
)
def test_unknown_diagnostic_values_never_escape(value) -> None:
    diagnostic = operator_diagnostic(value)
    assert value not in diagnostic.reason + diagnostic.guidance


def test_human_lifecycle_uses_existing_verified_report_model(
    tmp_path, monkeypatch, capsys
) -> None:
    _use_config(monkeypatch, tmp_path)
    report = make_operator_report()
    monkeypatch.setattr(
        lifecycle, "run_validation_lifecycle", lambda _config, **_options: report
    )
    dev.main(["validation-lifecycle", "--config", "unused", "--format", "human"])
    assert (
        capsys.readouterr().out.strip()
        == report.as_text(maximum_bytes=16384).decode().strip()
    )


@pytest.mark.parametrize("failure_type", [KeyboardInterrupt, RuntimeError])
def test_readiness_interrupt_or_unexpected_error_is_one_safe_json_object(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    failure_type: type[BaseException],
) -> None:
    config = _use_config(monkeypatch, tmp_path)
    private_failure = "private readiness failure"

    def fail_readiness(_config: OperatorLifecycleConfig) -> None:
        raise failure_type(private_failure)

    monkeypatch.setattr(readiness, "inspect_validation_readiness", fail_readiness)
    with pytest.raises(SystemExit) as error:
        dev.main(["validation-preflight", "--config", "unused", "--format", "json"])
    assert error.value.code == 1
    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    assert payload["schema_version"] == 1
    assert payload["kind"] == "operator-command-error"
    assert payload["command"] == "validation-preflight"
    assert payload["outcome"] == "failed"
    assert payload["reason"] == "operator_lifecycle_failure"
    assert isinstance(payload["guidance"], str)
    assert private_failure not in captured.out + captured.err
    assert "Traceback" not in captured.out + captured.err
    assert not config.runtime_root.exists()


def test_unexpected_stdout_error_exits_after_lifecycle_shutdown(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _use_config(monkeypatch, tmp_path)
    transitions: list[str] = []
    private_failure = "private unexpected output failure"

    def run(_config: OperatorLifecycleConfig, *, approval):
        assert callable(approval)
        transitions.append("shutdown_complete")
        return make_operator_report()

    class RuntimeBrokenOutput(io.StringIO):
        def write(self, _text: str) -> int:
            assert transitions == ["shutdown_complete"]
            raise RuntimeError(private_failure)

    monkeypatch.setattr(lifecycle, "run_validation_lifecycle", run)
    with monkeypatch.context() as broken_stream:
        broken_stream.setattr(sys, "stdout", RuntimeBrokenOutput())
        with pytest.raises(SystemExit) as error:
            dev.main(["validation-lifecycle", "--config", "unused"])
    assert error.value.code == 1
    assert transitions == ["shutdown_complete"]
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "Operator output unavailable" in captured.err
    assert private_failure not in captured.err
    assert "Traceback" not in captured.err


@pytest.mark.parametrize("output_format", [None, "human", "json"])
def test_readiness_success_uses_shared_checks_and_requested_output(
    ready_config: OperatorLifecycleConfig,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    output_format: str | None,
) -> None:
    monkeypatch.setattr(
        OperatorLifecycleConfig, "from_file", lambda _path: ready_config
    )
    expected = readiness.inspect_validation_readiness(ready_config)
    assert expected.ready
    args = ["validation-preflight", "--config", "unused"]
    if output_format is not None:
        args.extend(["--format", output_format])
    dev.main(args)
    captured = capsys.readouterr()
    if output_format == "json":
        assert json.loads(captured.out) == expected.as_dict()
    else:
        assert captured.out.strip() == expected.as_text().decode().strip()
    assert captured.err == ""
    assert not ready_config.runtime_root.exists()
