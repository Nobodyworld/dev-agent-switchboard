# ruff: noqa: PLR2004, S603, S607
"""Regressions for report inspection, preflight limits, URLs, and JSON input."""

from __future__ import annotations

import io
import json
import os
import subprocess
from dataclasses import asdict, replace
from pathlib import Path
from types import SimpleNamespace

import pytest

from client.python.execution_operator import lifecycle, preflight, processes, runtime
from client.python.execution_operator.config import (
    OperatorConfigurationError,
    OperatorLifecycleConfig,
)
from client.python.execution_operator.models import (
    OperatorLifecycleFailure,
    OperatorLifecycleReport,
)
from client.python.tests.execution_operator_test_support import make_operator_report
from server.execution.registry import get_trusted_manifest


def _config(root: Path) -> OperatorLifecycleConfig:
    return OperatorLifecycleConfig.from_mapping(
        {
            "schema_version": 1,
            "repository_full_name": "Nobodyworld/dev-agent-switchboard",
            "canonical_checkout": str(root / "canonical"),
            "target_sha": "a" * 40,
            "manifest_name": "worker-smoke",
            "manifest_version": "1",
            "mode": "fresh-then-exact-reuse",
            "runtime_root": str(root / "runtime"),
            "worker_id": "operator-test-worker",
            "worker_display_name": "Operator test worker",
        }
    )


def _runtime(root: Path) -> tuple[runtime.RuntimeLayout, OperatorLifecycleReport]:
    config = _config(root)
    manifest = get_trusted_manifest(config.manifest_name, config.manifest_version)
    assert manifest is not None
    result = preflight.PreflightResult(
        source=preflight.SourceSnapshot("a" * 40, "b" * 40, "c" * 64),
        manifest_digest=manifest.digest,
        manifest_steps=tuple(
            (step.id, step.required) for step in manifest.execution_steps
        ),
        token_present=True,
    )
    layout, summary = runtime.create_runtime(config, result)
    return layout, make_operator_report(runtime=summary)


@pytest.mark.parametrize("mode", ["fresh-only", "fresh-then-exact-reuse"])
def test_complete_recorded_reports_remain_valid(mode: str) -> None:
    report = make_operator_report(mode=mode)
    assert report.as_dict()["outcome"] == "succeeded"
    assert report.as_json_bytes(maximum_bytes=16384)
    assert report.as_text(maximum_bytes=16384)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("schema_version", True),
        ("schema_version", 3),
        ("outcome", "approved"),
        ("fresh_approved", "true"),
        ("reuse_approved", 1),
        ("active_lease_count", False),
        ("operator_action_count", True),
        ("runs", []),
        ("phases", []),
        ("preflight_checks", []),
        ("preflight_passed", False),
        ("fresh_approved", False),
        ("owned_processes_stopped", False),
        ("port_released", False),
        ("canonical_checkout_unchanged", False),
        ("active_lease_count", 1),
        ("worker_active_run_count", None),
        ("operator_action_count", 0),
        ("avoided_deterministic_step_count", 1),
        ("failed_runtime_preserved", True),
        ("completed_at", None),
        ("completed_at", "not-a-timestamp"),
        ("completed_at", "2026-08-27T00:00:00Z"),
        ("reason", "not_started"),
    ],
)
def test_report_serializers_reject_false_success(field: str, value: object) -> None:
    report = make_operator_report()
    setattr(report, field, value)
    for serialize in (
        report.as_dict,
        lambda: report.as_json_bytes(maximum_bytes=16384),
        lambda: report.as_text(maximum_bytes=16384),
    ):
        with pytest.raises(OperatorLifecycleFailure):
            serialize()


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("run_id", 2),
        ("work_order_id", 1),
        ("source_run_id", 99),
        ("worker_id", "other-worker"),
        ("reuse_identity_hash", "e" * 64),
        ("evidence_retention_expires_at", "2026-09-12T00:00:00Z"),
        ("step_count", 1),
        ("artifact_count", 1),
        ("schema_version", True),
        ("route_verified", "true"),
    ],
)
def test_report_rejects_inconsistent_reuse_links(field: str, value: object) -> None:
    report = make_operator_report(mode="fresh-then-exact-reuse")
    report.runs[1] = replace(report.runs[1], **{field: value})
    with pytest.raises(OperatorLifecycleFailure):
        report.as_dict()


def test_report_rejects_phase_reordering_and_duplicates() -> None:
    report = make_operator_report()
    report.phases[0], report.phases[1] = report.phases[1], report.phases[0]
    with pytest.raises(OperatorLifecycleFailure):
        report.as_dict()
    report = make_operator_report()
    report.phases.insert(1, report.phases[0])
    with pytest.raises(OperatorLifecycleFailure):
        report.as_dict()


def test_partial_failure_after_approval_attempt_can_be_reported() -> None:
    report = make_operator_report()
    report.outcome = "failed"
    report.reason = "operator_lifecycle_failure"
    report.phases = report.phases[:6] + ["shutdown_started", "cleanup_verified"]
    report.fresh_approved = False
    report.runs = []
    report.failed_runtime_preserved = True
    assert report.as_dict()["operator_action_count"] == 1


def test_inspection_is_labeled_and_never_rewrites_report(tmp_path: Path) -> None:
    layout, report = _runtime(tmp_path)
    runtime.write_report(layout, report, maximum_bytes=16384)
    path = layout.reports / runtime.REPORT_JSON_NAME
    before = (path.read_bytes(), path.stat().st_mtime_ns)
    inspected = lifecycle.inspect_validation_runtime(layout.root)
    assert inspected.as_dict() == report.as_dict()
    assert b"live evidence not reverified" in inspected.as_text(maximum_bytes=16384)
    assert (path.read_bytes(), path.stat().st_mtime_ns) == before
    text_size = len(inspected.as_text(maximum_bytes=16384))
    with pytest.raises(OperatorLifecycleFailure, match="report_size_limit_exceeded"):
        inspected.as_text(maximum_bytes=text_size - 1)


@pytest.mark.parametrize(
    "mutation", ["empty_success", "missing", "extra", "bool_count"]
)
def test_inspection_rejects_inconsistent_or_incomplete_reports(
    tmp_path: Path, mutation: str
) -> None:
    layout, report = _runtime(tmp_path)
    payload = report.as_dict()
    if mutation == "empty_success":
        payload = asdict(
            OperatorLifecycleReport(outcome="succeeded", runtime=report.runtime)
        )
    elif mutation == "missing":
        payload.pop("fresh_approved")
    elif mutation == "extra":
        payload["unrecognized"] = True
    else:
        payload["active_lease_count"] = False
    path = layout.reports / runtime.REPORT_JSON_NAME
    raw = json.dumps(payload).encode("utf-8")
    path.write_bytes(raw)
    before = path.stat().st_mtime_ns
    with pytest.raises(OperatorLifecycleFailure, match="runtime_report_invalid"):
        lifecycle.inspect_validation_runtime(layout.root)
    assert path.read_bytes() == raw and path.stat().st_mtime_ns == before


@pytest.mark.parametrize("raw", [b"null", b"[]", b'{"x":1,"x":2}', b"NaN"])
def test_inspection_rejects_nonobjects_duplicate_keys_and_nonfinite_json(
    tmp_path: Path, raw: bytes
) -> None:
    layout, _report = _runtime(tmp_path)
    path = layout.reports / runtime.REPORT_JSON_NAME
    path.write_bytes(raw)
    with pytest.raises(OperatorLifecycleFailure, match="runtime_record_invalid"):
        lifecycle.inspect_validation_runtime(layout.root)
    assert path.read_bytes() == raw


def test_inspection_rejects_oversized_or_nonregular_report(tmp_path: Path) -> None:
    layout, _report = _runtime(tmp_path)
    path = layout.reports / runtime.REPORT_JSON_NAME
    path.write_bytes(b" " * (1024 * 1024 + 1))
    with pytest.raises(OperatorLifecycleFailure, match="runtime_record_invalid"):
        lifecycle.inspect_validation_runtime(layout.root)
    path.unlink()
    path.mkdir()
    with pytest.raises(OperatorLifecycleFailure, match="runtime_record_invalid"):
        lifecycle.inspect_validation_runtime(layout.root)


@pytest.mark.parametrize("location", ["file", "parent"])
def test_inspection_rejects_symlinked_report_boundaries(
    tmp_path: Path, location: str
) -> None:
    layout, report = _runtime(tmp_path)
    outside = tmp_path / "outside"
    outside.mkdir()
    external = outside / runtime.REPORT_JSON_NAME
    raw = report.as_json_bytes(maximum_bytes=16384)
    external.write_bytes(raw)
    target = layout.reports / runtime.REPORT_JSON_NAME
    try:
        if location == "parent":
            layout.reports.rmdir()
            target = layout.reports
            target.symlink_to(outside, target_is_directory=True)
        else:
            target.symlink_to(external)
    except OSError as error:
        pytest.skip(f"symlink unavailable: {error.__class__.__name__}")
    try:
        with pytest.raises(OperatorLifecycleFailure):
            lifecycle.inspect_validation_runtime(layout.root)
        assert external.read_bytes() == raw
    finally:
        target.unlink()


@pytest.mark.skipif(os.name != "nt", reason="Windows report-directory junction")
def test_inspection_rejects_windows_report_directory_junction(tmp_path: Path) -> None:
    layout, report = _runtime(tmp_path)
    outside = tmp_path / "outside"
    outside.mkdir()
    external = outside / runtime.REPORT_JSON_NAME
    raw = report.as_json_bytes(maximum_bytes=16384)
    external.write_bytes(raw)
    layout.reports.rmdir()
    subprocess.run(
        ["cmd", "/c", "mklink", "/J", str(layout.reports), str(outside)],
        check=True,
        shell=False,
        capture_output=True,
    )
    try:
        with pytest.raises(OperatorLifecycleFailure, match="runtime_ownership_lost"):
            lifecycle.inspect_validation_runtime(layout.root)
        assert external.read_bytes() == raw
    finally:
        subprocess.run(
            ["cmd", "/c", "rmdir", str(layout.reports)],
            check=True,
            shell=False,
            capture_output=True,
        )


def test_inspection_rechecks_marker_after_report_read(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    layout, report = _runtime(tmp_path)
    runtime.write_report(layout, report, maximum_bytes=16384)
    original = runtime._read_json

    def replace_marker(path: Path, *, maximum: int) -> object:
        result = original(path, maximum=maximum)
        if path.name == runtime.REPORT_JSON_NAME:
            assert report.runtime is not None
            marker = asdict(replace(report.runtime, runtime_id="replacement"))
            layout.marker.write_text(json.dumps(marker), encoding="utf-8")
        return result

    monkeypatch.setattr(runtime, "_read_json", replace_marker)
    with pytest.raises(OperatorLifecycleFailure, match="runtime_ownership_lost"):
        lifecycle.inspect_validation_runtime(layout.root)


def test_inspection_uses_stable_record_identity_checks(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    layout, report = _runtime(tmp_path)
    runtime.write_report(layout, report, maximum_bytes=16384)
    target = layout.reports / runtime.REPORT_JSON_NAME
    inode = target.stat().st_ino
    original = runtime._same_file_identity

    def unstable(first: os.stat_result, second: os.stat_result) -> bool:
        return first.st_ino != inode and original(first, second)

    monkeypatch.setattr(runtime, "_same_file_identity", unstable)
    with pytest.raises(OperatorLifecycleFailure, match="runtime_record_unstable"):
        lifecycle.inspect_validation_runtime(layout.root)


def test_configuration_read_is_bounded_before_parsing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    sizes: list[int] = []

    class BoundedReader(io.BytesIO):
        def read(self, size: int = -1) -> bytes:
            sizes.append(size)
            assert 0 <= size <= 64 * 1024 + 1
            return super().read(size)

    reader = BoundedReader(b" " * (64 * 1024 + 2))
    monkeypatch.setattr(Path, "open", lambda *_args, **_kwargs: reader)
    with pytest.raises(OperatorConfigurationError, match="file_size"):
        OperatorLifecycleConfig.from_file(tmp_path / "large.json")
    assert sizes == [64 * 1024 + 1]


@pytest.mark.parametrize(
    "raw",
    [
        '{"target_sha":"private-first","target_sha":"private-second"}',
        '{"outer":{"runtime_root":"private-first","runtime_root":"private-second"}}',
        '{"value":NaN}',
        '{"value":Infinity}',
        '{"value":-Infinity}',
    ],
)
def test_configuration_rejects_ambiguous_json_without_echoing_values(
    tmp_path: Path, raw: str
) -> None:
    path = tmp_path / "config.json"
    path.write_text(raw, encoding="utf-8")
    with pytest.raises(OperatorConfigurationError) as caught:
        OperatorLifecycleConfig.from_file(path)
    assert "private-first" not in str(caught.value)
    assert "private-second" not in str(caught.value)


@pytest.mark.parametrize("version", [True, 1.0, "1"])
def test_configuration_schema_version_is_an_integer(version: object) -> None:
    with pytest.raises(OperatorConfigurationError, match="schema_version"):
        OperatorLifecycleConfig.from_mapping({"schema_version": version})


@pytest.mark.parametrize(
    ("host", "expected"),
    [
        ("127.0.0.1", "http://127.0.0.1:8765"),
        ("localhost", "http://localhost:8765"),
        ("::1", "http://[::1]:8765"),
    ],
)
def test_both_http_consumers_use_one_bracket_aware_origin(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, host: str, expected: str
) -> None:
    config = replace(_config(tmp_path), host=host)
    assert config.base_url == expected
    layout, report = _runtime(tmp_path)
    captured: dict[str, object] = {}
    monkeypatch.setattr(
        processes, "_control_plane_source_root", lambda _config: tmp_path
    )
    monkeypatch.setattr(processes, "_launch", lambda **_kwargs: None)

    def capture(
        _layout: runtime.RuntimeLayout,
        _summary: object,
        _path: Path,
        payload: dict[str, object],
    ) -> None:
        captured.update(payload)

    monkeypatch.setattr(processes, "_write_private_json", capture)
    assert report.runtime is not None
    processes.launch_worker(config, layout, report.runtime, "test-token")
    assert captured["base_url"] == expected
    observed: list[str] = []

    def client_origin(base_url: str, *_args: object, **_kwargs: object) -> None:
        observed.append(base_url)
        raise OperatorLifecycleFailure("test_stop_before_http")

    monkeypatch.setattr(
        lifecycle, "run_preflight", lambda _config: SimpleNamespace(source=None)
    )
    monkeypatch.setattr(
        lifecycle, "create_runtime", lambda *_args: (layout, report.runtime)
    )
    monkeypatch.setattr(lifecycle, "launch_server", lambda *_args: None)
    monkeypatch.setattr(lifecycle, "ExecutionClient", client_origin)
    monkeypatch.setattr(lifecycle, "_stop_owned", lambda *_args: True)
    monkeypatch.setattr(lifecycle, "port_is_released", lambda *_args: True)
    monkeypatch.setattr(lifecycle, "_source_is_unchanged", lambda *_args: True)
    monkeypatch.setattr(lifecycle, "write_report", lambda *_args, **_kwargs: None)
    monkeypatch.setenv("SWITCHBOARD_ADMIN_TOKEN", "test-token")
    with pytest.raises(OperatorLifecycleFailure, match="test_stop_before_http"):
        lifecycle.run_validation_lifecycle(config, approval=lambda *_args: False)
    assert observed == [expected]


def test_accounting_timeout_mismatch_is_rejected_during_preflight(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config = replace(
        _config(tmp_path),
        repository_full_name="Nobodyworld/app-accounting-modular",
        manifest_name="validate-accounting-modular",
    )
    config.canonical_checkout.mkdir()
    snapshot = preflight.SourceSnapshot("a" * 40, "b" * 40, "c" * 64)
    monkeypatch.setattr(preflight, "source_snapshot", lambda _config: snapshot)
    monkeypatch.setattr(preflight, "strict_containment_supported", lambda: True)
    monkeypatch.setattr(preflight, "runtime_path_budget_ok", lambda _path: True)
    monkeypatch.setattr(preflight, "_port_appears_available", lambda *_args: True)
    monkeypatch.setattr(
        preflight, "_manifest_capabilities_compatible", lambda _requirements: True
    )
    monkeypatch.setenv("SWITCHBOARD_ADMIN_TOKEN", "test-token")
    with pytest.raises(
        OperatorLifecycleFailure, match="manifest_timeout_exceeds_worker_budget"
    ):
        preflight.run_preflight(config)
    assert not config.runtime_root.exists()
    with pytest.raises(
        OperatorLifecycleFailure, match="terminal_timeout_below_manifest_budget"
    ):
        preflight.run_preflight(replace(config, work_order_timeout_seconds=5400))
    accepted = preflight.run_preflight(
        replace(config, work_order_timeout_seconds=5400, terminal_timeout_seconds=6000)
    )
    assert accepted.source == snapshot
    assert not config.runtime_root.exists()


def test_step_timeout_limit_is_checked_before_launch(tmp_path: Path) -> None:
    config = _config(tmp_path)
    manifest = SimpleNamespace(
        timeout_seconds=120,
        execution_steps=[SimpleNamespace(timeout_seconds=3601)],
    )
    with pytest.raises(
        OperatorLifecycleFailure, match="manifest_step_timeout_exceeds_worker_budget"
    ):
        preflight._validate_manifest_timeouts(
            config, manifest  # type: ignore[arg-type]
        )
    assert not config.runtime_root.exists()
