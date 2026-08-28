# ruff: noqa: PLR2004, S603, S607
"""Security boundaries for the marker-owned operator lifecycle."""

from __future__ import annotations

import json
import os
import shutil
import socket
import subprocess
import tempfile
import uuid
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import pytest
from scripts.dev import build_parser

from client.python.execution_operator import (
    lifecycle as lifecycle_module,
    preflight as preflight_module,
)
from client.python.execution_operator.config import (
    OperatorConfigurationError,
    OperatorLifecycleConfig,
)
from client.python.execution_operator.lifecycle import (
    inspect_validation_runtime,
    run_validation_lifecycle,
)
from client.python.execution_operator.models import (
    OperatorLifecycleFailure,
    OperatorLifecycleReport,
    RuntimeSummary,
)
from client.python.execution_operator.preflight import (
    PreflightResult,
    SourceSnapshot,
    run_preflight,
    runtime_path_budget_ok,
)
from client.python.execution_operator.runtime import create_runtime, inspect_runtime
from server.execution.registry import get_trusted_manifest


def _mapping(tmp_path: Path) -> dict[str, object]:
    return {
        "schema_version": 1,
        "repository_full_name": "Nobodyworld/dev-agent-switchboard",
        "canonical_checkout": str(tmp_path / "canonical"),
        "target_sha": "a" * 40,
        "manifest_name": "validate-switchboard",
        "manifest_version": "1",
        "mode": "fresh-then-exact-reuse",
        "runtime_root": str(tmp_path / "runtime"),
        "worker_id": "operator-test-worker",
        "worker_display_name": "Operator test worker",
        "port": 18765,
    }


def _config(tmp_path: Path) -> OperatorLifecycleConfig:
    return OperatorLifecycleConfig.from_mapping(_mapping(tmp_path))


def _preflight() -> PreflightResult:
    manifest = get_trusted_manifest("validate-switchboard", "1")
    assert manifest is not None
    return PreflightResult(
        source=SourceSnapshot("a" * 40, "b" * 40, "c" * 64),
        manifest_digest=manifest.digest,
        manifest_steps=tuple(
            (step.id, step.required) for step in manifest.execution_steps
        ),
        token_present=True,
    )


def test_configuration_accepts_only_the_strict_versioned_shape(tmp_path: Path) -> None:
    config = _config(tmp_path)
    assert config.mode == "fresh-then-exact-reuse"
    assert config.routing_policy == "first_available"
    assert config.runtime_root.is_absolute()
    assert "token" not in repr(config).lower()

    cases: list[tuple[str, object]] = [
        ("schema_version", 2),
        ("target_sha", "A" * 40),
        ("mode", "reuse-only"),
        ("host", "0.0.0.0"),  # noqa: S104 - explicit rejection case
        ("routing_policy", "cheapest_capable"),
        ("port", 80),
        ("poll_interval_seconds", 0.5),
        ("expected_manifest_digest", "x" * 64),
        ("runtime_root", "relative/runtime"),
        ("runtime_root", "\\\\server\\share\\runtime"),
    ]
    for key, value in cases:
        payload = {**_mapping(tmp_path), key: value}
        with pytest.raises(OperatorConfigurationError, match="invalid_configuration"):
            OperatorLifecycleConfig.from_mapping(payload)

    with pytest.raises(OperatorConfigurationError, match="unknown_field"):
        OperatorLifecycleConfig.from_mapping({**_mapping(tmp_path), "token": "secret"})


def test_configuration_file_is_bounded_and_rejects_non_object(tmp_path: Path) -> None:
    invalid = tmp_path / "invalid.json"
    invalid.write_text("[]", encoding="utf-8")
    with pytest.raises(OperatorConfigurationError, match="root"):
        OperatorLifecycleConfig.from_file(invalid)
    oversized = tmp_path / "oversized.json"
    oversized.write_bytes(b" " * (64 * 1024 + 1))
    with pytest.raises(OperatorConfigurationError, match="file_size"):
        OperatorLifecycleConfig.from_file(oversized)


def test_runtime_is_marker_first_and_inspection_is_read_only(tmp_path: Path) -> None:
    config = _config(tmp_path)
    layout, summary = create_runtime(config, _preflight())
    assert layout.marker.is_file()
    assert layout.temporary != layout.temporary_alt
    assert layout.temporary.is_dir() and layout.temporary_alt.is_dir()
    assert summary.command_identity == "validation-lifecycle@1"
    assert inspect_runtime(layout.root)[1] == summary
    before = {item: item.stat().st_mtime_ns for item in layout.root.rglob("*")}
    report = inspect_validation_runtime(layout.root)
    after = {item: item.stat().st_mtime_ns for item in layout.root.rglob("*")}
    assert report.outcome == "inspected"
    assert report.reason == "runtime_marker_verified"
    assert before == after
    with pytest.raises(OperatorLifecycleFailure, match="runtime_creation_failed"):
        create_runtime(config, _preflight())


def test_foreign_or_malformed_runtime_is_never_accepted(tmp_path: Path) -> None:
    root = tmp_path / "foreign"
    root.mkdir()
    (root / "operator-runtime.json").write_text(
        json.dumps({"schema_version": 1, "runtime_id": "foreign"}),
        encoding="utf-8",
    )
    with pytest.raises(OperatorLifecycleFailure, match="runtime_marker_invalid"):
        inspect_runtime(root)


def test_report_rejects_paths_secrets_and_oversize() -> None:
    report = OperatorLifecycleReport(reason="lifecycle_verified", outcome="succeeded")
    report.runtime = RuntimeSummary(
        schema_version=1,
        runtime_id="5c75a6df-cd63-4b86-9eca-38408a4a6650",
        repository_full_name="Nobodyworld/dev-agent-switchboard",
        target_sha="a" * 40,
        manifest_name="validate-switchboard",
        manifest_version="1",
        manifest_digest="b" * 64,
        mode="fresh-only",
        command_identity="validation-lifecycle@1",
        created_at="2026-08-28T00:00:00Z",
    )
    encoded = report.as_json_bytes(maximum_bytes=4096)
    assert b"token" not in encoded.lower()
    report.reason = "C:\\private\\checkout"
    with pytest.raises(OperatorLifecycleFailure, match="report_text_policy_rejected"):
        report.as_dict()
    report.reason = "lifecycle_verified"
    with pytest.raises(OperatorLifecycleFailure, match="report_size_limit_exceeded"):
        report.as_json_bytes(maximum_bytes=8)


def _git(repository: Path, *arguments: str) -> str:
    return subprocess.run(
        ["git", "-C", str(repository), *arguments],
        check=True,
        shell=False,
        capture_output=True,
        text=True,
    ).stdout.strip()


def _repository(tmp_path: Path) -> tuple[Path, str]:
    repository = tmp_path / "canonical"
    subprocess.run(["git", "init", str(repository)], check=True, shell=False)
    _git(repository, "config", "user.email", "operator@example.test")
    _git(repository, "config", "user.name", "Operator Test")
    (repository / "README.md").write_text("fixture\n", encoding="utf-8")
    _git(repository, "add", "README.md")
    _git(repository, "commit", "-m", "fixture")
    _git(
        repository,
        "remote",
        "add",
        "origin",
        "https://github.com/Nobodyworld/dev-agent-switchboard.git",
    )
    return repository, _git(repository, "rev-parse", "HEAD")


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
        listener.bind(("127.0.0.1", 0))
        return int(listener.getsockname()[1])


def test_preflight_proves_exact_clean_origin_and_is_non_mutating(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repository, sha = _repository(tmp_path)
    payload = _mapping(tmp_path)
    payload.update(
        {
            "canonical_checkout": str(repository),
            "target_sha": sha,
            "port": _free_port(),
            "runtime_root": str(
                Path("C:/tmp") / f"pf-{uuid.uuid4().hex[:8]}"
                if os.name == "nt"
                else tmp_path / "runtime"
            ),
        }
    )
    config = OperatorLifecycleConfig.from_mapping(payload)
    monkeypatch.setenv("SWITCHBOARD_ADMIN_TOKEN", "operator-test-token")
    before = _git(repository, "status", "--porcelain=v2", "--untracked-files=all")
    result = run_preflight(config)
    after = _git(repository, "status", "--porcelain=v2", "--untracked-files=all")
    assert result.source.head_sha == sha
    assert result.token_present is True
    assert before == after == ""

    (repository / "untracked.txt").write_text("dirty\n", encoding="utf-8")
    with pytest.raises(OperatorLifecycleFailure, match="source_checkout_dirty"):
        run_preflight(
            replace(
                config,
                runtime_root=config.runtime_root.with_name(
                    f"pf-dirty-{uuid.uuid4().hex[:8]}"
                ),
            )
        )


def test_preflight_fails_closed_before_runtime_creation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repository, sha = _repository(tmp_path)
    payload = _mapping(tmp_path)
    payload.update(
        {
            "canonical_checkout": str(repository),
            "target_sha": sha,
            "port": _free_port(),
            "runtime_root": str(
                Path("C:/tmp") / f"pf-bounds-{uuid.uuid4().hex[:8]}"
                if os.name == "nt"
                else tmp_path / "runtime"
            ),
        }
    )
    config = OperatorLifecycleConfig.from_mapping(payload)
    monkeypatch.setenv("SWITCHBOARD_ADMIN_TOKEN", "operator-preflight-test")

    config.runtime_root.mkdir()
    with pytest.raises(OperatorLifecycleFailure, match="runtime_root_already_exists"):
        run_preflight(config)
    config.runtime_root.rmdir()

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
        listener.bind(("127.0.0.1", 0))
        listener.listen()
        occupied = replace(config, port=int(listener.getsockname()[1]))
        with pytest.raises(OperatorLifecycleFailure, match="loopback_port_occupied"):
            run_preflight(occupied)

    monkeypatch.delenv("SWITCHBOARD_ADMIN_TOKEN")
    with pytest.raises(OperatorLifecycleFailure, match="admin_token_missing"):
        run_preflight(config)
    monkeypatch.setenv("SWITCHBOARD_ADMIN_TOKEN", "operator-preflight-test")

    mismatch = replace(config, expected_manifest_digest="f" * 64)
    with pytest.raises(
        OperatorLifecycleFailure, match="trusted_manifest_digest_mismatch"
    ):
        run_preflight(mismatch)

    monkeypatch.setattr(
        preflight_module,
        "_manifest_capabilities_compatible",
        lambda _requirements: False,
    )
    with pytest.raises(OperatorLifecycleFailure, match="worker_capability_mismatch"):
        run_preflight(config)


def test_windows_runtime_path_budget_reserves_nested_worktree_space() -> None:
    assert runtime_path_budget_ok(Path("C:/tmp/sb151-12345678"), platform_name="nt")
    assert not runtime_path_budget_ok(
        Path("C:/") / ("nested-operator-runtime-" * 5), platform_name="nt"
    )
    assert runtime_path_budget_ok(
        Path("/long") / ("nested-operator-runtime-" * 20), platform_name="posix"
    )


def test_cli_requires_separate_noninteractive_approval_flags(tmp_path: Path) -> None:
    parser = build_parser()
    arguments = parser.parse_args(
        ["validation-lifecycle", "--config", str(tmp_path / "config.json")]
    )
    assert arguments.approve_fresh is False
    assert arguments.approve_reuse is False
    arguments = parser.parse_args(
        [
            "validation-lifecycle",
            "--config",
            str(tmp_path / "config.json"),
            "--approve-fresh",
            "--approve-reuse",
        ]
    )
    assert arguments.approve_fresh is True
    assert arguments.approve_reuse is True


def test_fresh_denial_preserves_the_created_pending_work_order(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config = _config(tmp_path)
    layout, _summary = create_runtime(config, _preflight())

    class RejectingClient:
        created = False

        def create_work_order(self, _payload: object) -> dict[str, object]:
            self.created = True
            return {}

    client = RejectingClient()
    monkeypatch.setattr(
        lifecycle_module,
        "_validate_order",
        lambda *_args, **_kwargs: SimpleNamespace(id=1),
    )
    report = OperatorLifecycleReport()
    with pytest.raises(OperatorLifecycleFailure, match="fresh_approval_denied"):
        lifecycle_module._execute_phase(
            client=client,  # type: ignore[arg-type]
            config=config,
            layout=layout,
            preflight=_preflight(),
            approval=lambda _phase, _identity: False,
            phase="fresh",
            source=None,
            worker=None,  # type: ignore[arg-type]
            report=report,
        )
    assert client.created is True
    assert report.phases == ["fresh_created", "fresh_approval_required"]


def test_reuse_denial_precedes_work_order_creation(tmp_path: Path) -> None:
    config = _config(tmp_path)
    layout, _summary = create_runtime(config, _preflight())

    class RejectingClient:
        created = False

        def create_work_order(self, _payload: object) -> dict[str, object]:
            self.created = True
            return {}

    client = RejectingClient()
    report = OperatorLifecycleReport(phases=["fresh_verified"])
    with pytest.raises(OperatorLifecycleFailure, match="reuse_approval_denied"):
        lifecycle_module._execute_phase(
            client=client,  # type: ignore[arg-type]
            config=config,
            layout=layout,
            preflight=_preflight(),
            approval=lambda _phase, _identity: False,
            phase="reuse",
            source=None,
            worker=None,  # type: ignore[arg-type]
            report=report,
        )
    assert client.created is False
    assert report.phases[-1] == "reuse_approval_required"


def test_terminal_wait_fails_immediately_when_owned_worker_exits(
    tmp_path: Path,
) -> None:
    config = replace(_config(tmp_path), terminal_timeout_seconds=60)

    class ExitedWorker:
        @staticmethod
        def running() -> bool:
            return False

    class UnusedClient:
        @staticmethod
        def list_runs(_work_order_id: int) -> list[dict[str, object]]:
            raise AssertionError("API polling must not continue after worker exit")

    with pytest.raises(OperatorLifecycleFailure, match="worker_process_exited"):
        lifecycle_module._wait_terminal_run(
            UnusedClient(),  # type: ignore[arg-type]
            config,
            ExitedWorker(),  # type: ignore[arg-type]
            1,
        )


@pytest.mark.parametrize(
    ("mode", "expected_decisions", "expected_actions"),
    [
        ("fresh-only", ["fresh"], 1),
        ("fresh-then-exact-reuse", ["fresh", "reused"], 2),
    ],
)
def test_real_server_worker_synthetic_lifecycle_modes(
    mode: str,
    expected_decisions: list[str],
    expected_actions: int,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repository = Path.cwd().resolve()
    sha = _git(repository, "rev-parse", "HEAD")
    manifest = get_trusted_manifest("worker-smoke", "1")
    assert manifest is not None
    runtime_parent = Path("C:/tmp") if os.name == "nt" else Path(tempfile.gettempdir())
    runtime_root = runtime_parent / f"sb151-synthetic-{uuid.uuid4().hex[:8]}"
    payload = _mapping(runtime_parent)
    payload.update(
        {
            "canonical_checkout": str(repository),
            "target_sha": sha,
            "manifest_name": "worker-smoke",
            "manifest_version": "1",
            "expected_manifest_digest": manifest.digest,
            "mode": mode,
            "runtime_root": str(runtime_root),
            "port": _free_port(),
            "startup_timeout_seconds": 60,
            "terminal_timeout_seconds": 180,
        }
    )
    config = OperatorLifecycleConfig.from_mapping(payload)
    token = f"operator-synthetic-{uuid.uuid4().hex}"
    monkeypatch.setenv("SWITCHBOARD_ADMIN_TOKEN", token)
    approvals: list[str] = []
    verified = False
    try:
        report = run_validation_lifecycle(
            config,
            approval=lambda _phase, identity: not approvals.append(identity),
        )
        assert report.outcome == "succeeded"
        assert [run.reuse_decision for run in report.runs] == expected_decisions
        assert report.operator_action_count == expected_actions
        assert len(approvals) == expected_actions
        assert report.active_lease_count == report.worker_active_run_count == 0
        assert report.owned_processes_stopped and report.port_released
        assert report.phases[-3:] == [
            "shutdown_started",
            "cleanup_verified",
            "completed",
        ]
        if mode == "fresh-then-exact-reuse":
            assert report.runs[1].step_count == report.runs[1].artifact_count == 0
            assert report.runs[1].reused_from_run_id == report.runs[0].run_id
            assert report.avoided_deterministic_step_count == len(
                manifest.execution_steps
            )
        assert inspect_validation_runtime(runtime_root).as_dict() == report.as_dict()
        for path in (
            runtime_root / "operator-runtime.json",
            runtime_root / "worker-config.json",
            *(runtime_root / "processes").glob("*"),
            *(runtime_root / "reports").glob("*"),
        ):
            if path.is_file():
                assert token.encode("utf-8") not in path.read_bytes()
        verified = True
    finally:
        if verified:
            inspected, _summary = inspect_runtime(runtime_root)
            assert inspected.root == runtime_root
            shutil.rmtree(runtime_root)


@pytest.mark.skipif(
    os.environ.get("RUN_OPERATOR_LIFECYCLE_INTEGRATION") != "1",
    reason="explicit bounded operator lifecycle acceptance only",
)
def test_real_server_worker_fresh_then_exact_reuse(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repository = Path.cwd().resolve()
    sha = _git(repository, "rev-parse", "HEAD")
    manifest = get_trusted_manifest("validate-switchboard", "1")
    assert manifest is not None
    payload = _mapping(tmp_path)
    runtime_parent = Path("C:/tmp") if os.name == "nt" else tmp_path
    payload.update(
        {
            "canonical_checkout": str(repository),
            "target_sha": sha,
            "runtime_root": str(runtime_parent / f"sb151-{uuid.uuid4().hex[:8]}"),
            "port": _free_port(),
            "expected_manifest_digest": manifest.digest,
            "startup_timeout_seconds": 60,
            "terminal_timeout_seconds": 7200,
        }
    )
    config = OperatorLifecycleConfig.from_mapping(payload)
    monkeypatch.setenv("SWITCHBOARD_ADMIN_TOKEN", "operator-integration-token")
    approvals: list[str] = []

    def approve(_phase: str, identity: str) -> bool:
        approvals.append(identity)
        return True

    report = run_validation_lifecycle(config, approval=approve)
    assert report.outcome == "succeeded"
    assert [run.reuse_decision for run in report.runs] == ["fresh", "reused"]
    assert report.runs[1].step_count == report.runs[1].artifact_count == 0
    assert report.runs[1].reused_from_run_id == report.runs[0].run_id
    assert len(approvals) == 2
    assert report.active_lease_count == report.worker_active_run_count == 0
    assert report.owned_processes_stopped and report.port_released
    assert inspect_validation_runtime(config.runtime_root).as_dict() == report.as_dict()
