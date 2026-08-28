# ruff: noqa: PLR2004, S603, S607
"""Security boundaries for the marker-owned operator lifecycle."""

from __future__ import annotations

import datetime as dt
import json
import os
import shutil
import socket
import stat
import subprocess
import tempfile
import uuid
from dataclasses import asdict, replace
from pathlib import Path
from types import SimpleNamespace

import pytest
from scripts.dev import build_parser

from client.python.execution_operator import (
    lifecycle as lifecycle_module,
    preflight as preflight_module,
    processes as processes_module,
    runtime as runtime_module,
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
    ArtifactSummary,
    OperatorLifecycleFailure,
    OperatorLifecycleReport,
    RunSummary,
    RuntimeSummary,
)
from client.python.execution_operator.preflight import (
    PreflightResult,
    SourceSnapshot,
    github_origin_identity,
    run_preflight,
    runtime_path_budget_ok,
)
from client.python.execution_operator.processes import OwnedProcess
from client.python.execution_operator.runtime import (
    create_runtime,
    inspect_runtime,
    touch_owned_stop,
    verify_runtime_ownership,
    write_report,
)
from server.execution.evidence import (
    EvidenceReuseIdentity,
    compute_reuse_identity_hash,
)
from server.execution.registry import get_trusted_manifest
from server.execution.schemas import RouteProvenanceOut


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


class _FakeProcess:
    def poll(self) -> None:
        return None


class _FakeHost:
    def __init__(self) -> None:
        self.process = _FakeProcess()
        self.terminate_calls = 0
        self.finalize_calls = 0

    def terminate(self, *, grace_seconds: float) -> None:
        _ = grace_seconds
        self.terminate_calls += 1

    def finalize_after_exit(self, *, grace_seconds: float) -> SimpleNamespace:
        _ = grace_seconds
        self.finalize_calls += 1
        return SimpleNamespace(cleanup_verified=True)


def _replace_marker(
    layout: runtime_module.RuntimeLayout, summary: RuntimeSummary
) -> None:
    replacement = replace(summary, runtime_id=str(uuid.uuid4()))
    layout.marker.write_text(
        json.dumps(asdict(replacement), sort_keys=True, separators=(",", ":")),
        encoding="utf-8",
    )


def test_valid_marker_replacement_blocks_every_mutation_and_process_action(
    tmp_path: Path,
) -> None:
    config = _config(tmp_path)
    layout, summary = create_runtime(config, _preflight())
    host = _FakeHost()
    owned = OwnedProcess(
        kind="server",
        host=host,  # type: ignore[arg-type]
        layout=layout,
        expected_runtime=summary,
        stop_file=layout.stop_server,
        _redacted_token=b"private-token",
    )
    report = OperatorLifecycleReport(runtime=summary)
    _replace_marker(layout, summary)

    with pytest.raises(OperatorLifecycleFailure, match="runtime_ownership_lost"):
        processes_module._record_process(layout, summary, "worker", 1234)
    with pytest.raises(OperatorLifecycleFailure, match="runtime_ownership_lost"):
        owned.stop(timeout=0.01)
    with pytest.raises(OperatorLifecycleFailure, match="runtime_ownership_lost"):
        write_report(layout, report, maximum_bytes=4096)

    assert not layout.stop_server.exists()
    assert not (layout.process_records / "worker.json").exists()
    assert not (layout.reports / runtime_module.REPORT_JSON_NAME).exists()
    assert not (layout.reports / runtime_module.REPORT_TEXT_NAME).exists()
    assert host.terminate_calls == host.finalize_calls == 0
    assert layout.root.is_dir()


@pytest.mark.parametrize("marker_state", ["missing", "malformed", "duplicate"])
def test_runtime_ownership_rejects_missing_or_malformed_marker(
    tmp_path: Path, marker_state: str
) -> None:
    layout, summary = create_runtime(_config(tmp_path), _preflight())
    if marker_state == "missing":
        layout.marker.unlink()
    elif marker_state == "malformed":
        layout.marker.write_text("{", encoding="utf-8")
    else:
        layout.marker.write_text(
            '{"schema_version":1,"schema_version":1}',
            encoding="utf-8",
        )
    with pytest.raises(OperatorLifecycleFailure, match="runtime_ownership_lost"):
        verify_runtime_ownership(layout, summary)
    assert layout.root.is_dir()


def test_runtime_marker_change_while_read_fails_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    layout, summary = create_runtime(_config(tmp_path), _preflight())
    monkeypatch.setattr(
        runtime_module,
        "_same_file_identity",
        SimpleNamespace(side_effect=None),
    )
    identities = iter((True, False))
    monkeypatch.setattr(
        runtime_module,
        "_same_file_identity",
        lambda _first, _second: next(identities),
    )
    with pytest.raises(OperatorLifecycleFailure, match="runtime_ownership_lost"):
        verify_runtime_ownership(layout, summary)
    assert layout.root.is_dir()


def test_runtime_marker_symlink_is_rejected(
    tmp_path: Path,
) -> None:
    layout, summary = create_runtime(_config(tmp_path), _preflight())
    outside = tmp_path / "outside-marker.json"
    outside.write_text(json.dumps(asdict(summary)), encoding="utf-8")
    layout.marker.unlink()
    try:
        layout.marker.symlink_to(outside)
    except OSError as error:
        pytest.skip(f"file symlink unavailable: {error.__class__.__name__}")
    with pytest.raises(OperatorLifecycleFailure, match="runtime_ownership_lost"):
        verify_runtime_ownership(layout, summary)
    assert outside.is_file()


@pytest.mark.skipif(os.name != "nt", reason="Windows junction ownership coverage")
@pytest.mark.parametrize("location", ["marker", "root", "ancestry"])
def test_runtime_ownership_rejects_real_windows_junctions(
    tmp_path: Path, location: str
) -> None:
    layout, summary = create_runtime(_config(tmp_path), _preflight())
    outside = tmp_path / f"outside-{location}"
    outside.mkdir()
    junction = tmp_path / f"junction-{location}"
    candidate_layout = layout
    if location == "marker":
        layout.marker.unlink()
        junction = layout.marker
    elif location == "root":
        junction = tmp_path / "runtime-root-junction"
        candidate_layout = runtime_module._layout(junction)
        outside = layout.root
    else:
        parent_target = tmp_path / "parent-target"
        parent_target.mkdir()
        nested = parent_target / "runtime"
        shutil.copytree(layout.root, nested)
        outside = parent_target
        candidate_layout = runtime_module._layout(junction / "runtime")
    subprocess.run(
        ["cmd", "/c", "mklink", "/J", str(junction), str(outside)],
        check=True,
        shell=False,
        capture_output=True,
        text=True,
    )
    try:
        with pytest.raises(OperatorLifecycleFailure, match="runtime_ownership_lost"):
            verify_runtime_ownership(candidate_layout, summary)
    finally:
        subprocess.run(
            ["cmd", "/c", "rmdir", str(junction)],
            check=False,
            shell=False,
            capture_output=True,
            text=True,
        )


@pytest.mark.skipif(os.name != "nt", reason="Windows destination junction coverage")
def test_runtime_mutation_rejects_junctioned_destination_parent(tmp_path: Path) -> None:
    layout, summary = create_runtime(_config(tmp_path), _preflight())
    outside = tmp_path / "outside-processes"
    outside.mkdir()
    layout.process_records.rmdir()
    subprocess.run(
        ["cmd", "/c", "mklink", "/J", str(layout.process_records), str(outside)],
        check=True,
        shell=False,
        capture_output=True,
        text=True,
    )
    try:
        with pytest.raises(OperatorLifecycleFailure, match="runtime_ownership_lost"):
            processes_module._record_process(layout, summary, "worker", 1234)
        assert not any(outside.iterdir())
    finally:
        subprocess.run(
            ["cmd", "/c", "rmdir", str(layout.process_records)],
            check=False,
            shell=False,
            capture_output=True,
            text=True,
        )


def test_matching_original_marker_allows_owned_stop_and_report(
    tmp_path: Path,
) -> None:
    layout, summary = create_runtime(_config(tmp_path), _preflight())
    assert verify_runtime_ownership(layout, summary) == summary
    touch_owned_stop(layout, summary, layout.stop_server)
    report = OperatorLifecycleReport(runtime=summary)
    write_report(layout, report, maximum_bytes=4096)
    assert layout.stop_server.read_bytes() == b"stop\n"
    assert (layout.reports / runtime_module.REPORT_JSON_NAME).is_file()
    assert (layout.reports / runtime_module.REPORT_TEXT_NAME).is_file()


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


def _run_summary(*, artifact_size: int = 0) -> RunSummary:
    artifacts = (
        [
            ArtifactSummary(
                kind="command-log",
                relative_path="logs/result.log",
                size_bytes=artifact_size,
                sha256="d" * 64,
            )
        ]
        if artifact_size
        else []
    )
    return RunSummary(
        schema_version=1,
        work_order_id=1,
        run_id=2,
        source_run_id=2,
        phase="fresh",
        worker_id="operator-test-worker",
        status="succeeded",
        reuse_decision="fresh",
        reused_from_run_id=None,
        reuse_identity_hash="a" * 64,
        evidence_fingerprint="b" * 64,
        evidence_retention_expires_at="2026-09-11T00:00:00Z",
        routing_policy="first_available",
        route_reason="routing_selected",
        required_quota_units=0,
        reserved_quota_units=0,
        quota_reservation_state="not_required",
        eligible_candidate_count=1,
        step_count=0,
        artifact_count=len(artifacts),
        artifact_total_bytes=artifact_size,
        route_verified=True,
        evidence_verified=True,
        local_evidence_verified=True,
        source_checkout_unchanged=True,
        artifacts=artifacts,
    )


def test_report_derives_exact_artifact_bytes_and_route_identity_facts() -> None:
    report = OperatorLifecycleReport(runs=[_run_summary(artifact_size=37)])
    payload = report.as_dict()
    run = payload["runs"][0]
    assert run["artifact_total_bytes"] == 37
    assert run["reuse_identity_hash"] == "a" * 64
    assert run["routing_policy"] == "first_available"
    assert run["required_quota_units"] == run["reserved_quota_units"] == 0
    assert run["quota_reservation_state"] == "not_required"
    text = report.as_text(maximum_bytes=4096).decode("utf-8")
    for value in (
        "artifact_bytes=37",
        "identity_hash=" + "a" * 64,
        "route=first_available:routing_selected",
        "quota=0/0:not_required",
    ):
        assert value in text


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("reuse_identity_hash", "x" * 64),
        ("route_reason", "C:/private/route"),
        ("required_quota_units", 1),
        ("reserved_quota_units", 1),
        ("quota_reservation_state", "consumed"),
        ("artifact_total_bytes", 38),
    ],
)
def test_report_rejects_unsafe_or_inexact_run_facts(field: str, value: object) -> None:
    run = replace(_run_summary(artifact_size=37), **{field: value})
    report = OperatorLifecycleReport(runs=[run])
    with pytest.raises(OperatorLifecycleFailure, match="report_run_invalid"):
        report.as_dict()


def test_report_schema_cannot_expose_private_process_or_request_data() -> None:
    encoded = OperatorLifecycleReport(runs=[_run_summary()]).as_json_bytes(
        maximum_bytes=8192
    )
    for forbidden in (
        b"private-token",
        b"argv",
        b"raw_body",
        b"environment",
        b'reuse_identity"',
        b"C:\\private\\checkout",
        b"/private/checkout",
    ):
        assert forbidden not in encoded


def _route(**updates: object) -> RouteProvenanceOut:
    payload: dict[str, object] = {
        "schema_version": 1,
        "routing_policy": "first_available",
        "selected_worker_id": "operator-test-worker",
        "selected_routing_profile_revision": None,
        "estimated_cost_units": None,
        "required_quota_units": 0,
        "reserved_quota_units": 0,
        "quota_reservation_state": "not_required",
        "eligible_candidate_count": 1,
        "explicit_pin_applied": True,
        "reason": "routing_selected",
        "decision_timestamp": "2026-08-28T00:00:00Z",
    }
    payload.update(updates)
    return RouteProvenanceOut.model_validate(payload)


def test_exact_zero_quota_route_is_accepted(tmp_path: Path) -> None:
    assert lifecycle_module._route_is_exact(_route(), _config(tmp_path))


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("routing_policy", "cheapest_capable"),
        ("selected_worker_id", "another-worker"),
        ("explicit_pin_applied", False),
        ("required_quota_units", 1),
        ("reserved_quota_units", 1),
        ("quota_reservation_state", "consumed"),
    ],
)
def test_inexact_route_or_quota_is_rejected(
    tmp_path: Path, field: str, value: object
) -> None:
    assert not lifecycle_module._route_is_exact(
        _route(**{field: value}),
        _config(tmp_path),
    )


def _reuse_identity() -> EvidenceReuseIdentity:
    return EvidenceReuseIdentity(
        repository_full_name="Nobodyworld/dev-agent-switchboard",
        tested_sha="a" * 40,
        manifest_name="worker-smoke",
        manifest_version="1",
        manifest_digest="b" * 64,
        worker_environment_fingerprint="c" * 64,
        dependency_lock_hashes=[],
        execution_policy_hash="d" * 64,
        result_contract_hash="e" * 64,
    )


@pytest.mark.parametrize("mode", ["fresh-only", "fresh-then-exact-reuse"])
def test_fresh_verification_always_requires_identity_and_hash(
    tmp_path: Path, mode: str
) -> None:
    config = replace(_config(tmp_path), mode=mode)
    layout, _summary = create_runtime(config, _preflight())
    now = dt.datetime.now(dt.UTC)
    evidence = SimpleNamespace(started_at=now, fingerprint="f" * 64)
    base = {
        "id": 7,
        "evidence_retention_expires_at": now + dt.timedelta(days=14),
        "source_evidence_fingerprint": None,
        "artifact_metadata": [],
    }
    for missing in ("reuse_identity", "reuse_identity_hash"):
        values = {
            **base,
            "reuse_identity": _reuse_identity(),
            "reuse_identity_hash": compute_reuse_identity_hash(_reuse_identity()),
            missing: None,
        }
        assert not lifecycle_module._verify_local_fresh(
            config,
            layout,
            SimpleNamespace(**values),  # type: ignore[arg-type]
            evidence,  # type: ignore[arg-type]
        )


@pytest.mark.parametrize(
    "verification_reason",
    [
        "source_result_identity_mismatch",
        "source_result_unstable",
        "source_result_invalid",
        "source_artifact_unsafe",
        "source_artifact_size_mismatch",
        "source_artifact_hash_mismatch",
        "source_artifact_unstable",
    ],
)
def test_fresh_verification_uses_complete_retained_evidence_result(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    verification_reason: str,
) -> None:
    config = replace(_config(tmp_path), mode="fresh-only")
    layout, _summary = create_runtime(config, _preflight())
    now = dt.datetime.now(dt.UTC)
    identity = _reuse_identity()
    run = SimpleNamespace(
        id=7,
        evidence_retention_expires_at=now + dt.timedelta(days=14),
        source_evidence_fingerprint=None,
        artifact_metadata=[],
        reuse_identity=identity,
        reuse_identity_hash=compute_reuse_identity_hash(identity),
    )
    monkeypatch.setattr(
        lifecycle_module,
        "verify_reuse_candidate",
        lambda **_kwargs: SimpleNamespace(
            verified=False,
            reason=verification_reason,
        ),
    )
    evidence = SimpleNamespace(started_at=now, fingerprint="f" * 64)
    assert not lifecycle_module._verify_local_fresh(
        config,
        layout,
        run,  # type: ignore[arg-type]
        evidence,  # type: ignore[arg-type]
    )


def test_fresh_verification_rejects_mismatched_identity_hash(tmp_path: Path) -> None:
    config = replace(_config(tmp_path), mode="fresh-only")
    layout, _summary = create_runtime(config, _preflight())
    now = dt.datetime.now(dt.UTC)
    run = SimpleNamespace(
        id=7,
        evidence_retention_expires_at=now + dt.timedelta(days=14),
        source_evidence_fingerprint=None,
        artifact_metadata=[],
        reuse_identity=_reuse_identity(),
        reuse_identity_hash="0" * 64,
    )
    evidence = SimpleNamespace(started_at=now, fingerprint="f" * 64)
    assert not lifecycle_module._verify_local_fresh(
        config,
        layout,
        run,  # type: ignore[arg-type]
        evidence,  # type: ignore[arg-type]
    )


def _git(repository: Path, *arguments: str) -> str:
    return subprocess.run(
        ["git", "-C", str(repository), *arguments],
        check=True,
        shell=False,
        capture_output=True,
        text=True,
    ).stdout.strip()


def _repository(
    tmp_path: Path,
    *,
    origin: str = "https://github.com/Nobodyworld/dev-agent-switchboard.git",
) -> tuple[Path, str]:
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
        origin,
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


def test_preflight_tool_versions_and_capability_contract_are_bounded(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        preflight_module.shutil,
        "which",
        lambda *_args, **_kwargs: "tool",
    )
    monkeypatch.setattr(
        preflight_module.subprocess,
        "run",
        lambda *_args, **_kwargs: SimpleNamespace(
            returncode=0,
            stdout=b"v24.12.0\n",
        ),
    )
    assert preflight_module._tool_version("node", allow_leading_v=True) == "24.12.0"

    monkeypatch.setattr(
        preflight_module.subprocess,
        "run",
        lambda *_args, **_kwargs: SimpleNamespace(
            returncode=0,
            stdout=b"1" * 257,
        ),
    )
    assert preflight_module._tool_version("pnpm") is None

    versions = {"node": "24.12.0", "pnpm": "10.18.1"}
    monkeypatch.setattr(
        preflight_module,
        "_tool_version",
        lambda name, **_kwargs: versions.get(name),
    )
    requirements: dict[str, object] = {
        "git_available": True,
        "node": {"minimum": "24.12.0"},
        "pnpm": {"exact": "10.18.1"},
        "python": {"minimum": "3.11"},
        "repository_write": False,
    }
    assert preflight_module._manifest_capabilities_compatible(requirements)
    assert not preflight_module._manifest_capabilities_compatible(
        {**requirements, "pnpm": {"exact": "0.0.0"}}
    )
    assert not preflight_module._manifest_capabilities_compatible({"unsupported": True})


@pytest.mark.parametrize(
    "origin",
    [
        "https://github.com/Nobodyworld/dev-agent-switchboard",
        "https://github.com/Nobodyworld/dev-agent-switchboard.git",
        "https://github.com/Nobodyworld/dev-agent-switchboard/",
        "https://github.com/NOBODYWORLD/DEV-AGENT-SWITCHBOARD.git/",
        "git@github.com:Nobodyworld/dev-agent-switchboard",
        "git@github.com:Nobodyworld/dev-agent-switchboard.git",
        "git@github.com:Nobodyworld/dev-agent-switchboard/",
        "ssh://git@github.com/Nobodyworld/dev-agent-switchboard",
        "ssh://git@github.com/Nobodyworld/dev-agent-switchboard.git",
        "ssh://git@github.com/Nobodyworld/dev-agent-switchboard/",
    ],
)
def test_github_origin_supported_forms_normalize_semantically(origin: str) -> None:
    assert github_origin_identity(origin) == (
        "nobodyworld",
        "dev-agent-switchboard",
    )


@pytest.mark.parametrize(
    "origin",
    [
        "http://github.com/Nobodyworld/dev-agent-switchboard",
        "https://user@github.com/Nobodyworld/dev-agent-switchboard",
        "https://user:secret@github.com/Nobodyworld/dev-agent-switchboard",
        "ssh://root@github.com/Nobodyworld/dev-agent-switchboard",
        "https://github.com.example/Nobodyworld/dev-agent-switchboard",
        "https://github.com/Nobodyworld/another-repository",
        "https://github.com:443/Nobodyworld/dev-agent-switchboard",
        "ssh://git@github.com:22/Nobodyworld/dev-agent-switchboard",
        "https://github.com/Nobodyworld/dev-agent-switchboard?ref=main",
        "https://github.com/Nobodyworld/dev-agent-switchboard#fragment",
        "https://github.com/Nobodyworld/dev-agent-switchboard/extra",
        "C:/checkout/dev-agent-switchboard",
        "file:///checkout/dev-agent-switchboard",
        "git@github.com",
        "git@github.com:Nobodyworld",
        "git@github.com:/dev-agent-switchboard",
        "git@github.com:Nobodyworld/",
        "git@github.com:Nobodyworld/../dev-agent-switchboard",
        "https://github.com/Nobodyworld/%2e%2e",
        "https://github.com//dev-agent-switchboard",
        "git@github.com:Nobodyworld/dev-agent-switchboard/extra",
    ],
)
def test_github_origin_rejects_closed_unsafe_matrix(origin: str) -> None:
    identity = github_origin_identity(origin)
    assert identity != ("nobodyworld", "dev-agent-switchboard")
    assert origin not in repr(identity)


def test_portable_reparse_metadata_uses_guarded_windows_attributes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    normal = SimpleNamespace(st_mode=stat.S_IFDIR)
    windows_normal = SimpleNamespace(st_mode=stat.S_IFDIR, st_file_attributes=0)
    windows_reparse = SimpleNamespace(
        st_mode=stat.S_IFDIR,
        st_file_attributes=0x0400,
    )
    assert not preflight_module._metadata_is_reparse(normal)
    assert not preflight_module._metadata_is_reparse(windows_normal)
    assert preflight_module._metadata_is_reparse(windows_reparse)
    monkeypatch.delattr(
        preflight_module.stat,
        "FILE_ATTRIBUTE_REPARSE_POINT",
        raising=False,
    )
    assert preflight_module._reparse_point_flag() == 0x0400
    assert preflight_module._metadata_is_reparse(windows_reparse)


def test_reparse_inspection_accepts_normal_directory_and_bounds_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    assert not preflight_module.path_is_reparse(tmp_path)

    def fail_inspection(_path: Path) -> os.stat_result:
        raise OSError("private path details")

    monkeypatch.setattr(Path, "lstat", fail_inspection)
    with pytest.raises(OperatorLifecycleFailure) as caught:
        preflight_module.path_is_reparse(tmp_path)
    assert caught.value.reason == "path_inspection_failed"
    assert "private path details" not in str(caught.value)


@pytest.mark.parametrize(
    "reason",
    ["canonical_checkout_reparse_ancestry", "runtime_parent_reparse_ancestry"],
)
def test_canonical_and_runtime_ancestry_reject_real_symlink(
    tmp_path: Path, reason: str
) -> None:
    target = tmp_path / "target"
    target.mkdir()
    linked = tmp_path / "linked"
    try:
        linked.symlink_to(target, target_is_directory=True)
    except OSError as error:
        pytest.skip(f"directory symlink unavailable: {error.__class__.__name__}")
    with pytest.raises(OperatorLifecycleFailure, match=reason):
        preflight_module.assert_no_reparse_ancestry(linked / "child", reason)


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
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repository, sha = _repository(
        tmp_path,
        origin="https://github.com/Nobodyworld/dev-agent-switchboard",
    )
    assert not (repository / "scripts" / "operator_server.py").exists()
    assert not (repository / "scripts" / "local_worker.py").exists()
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
    control_plane = processes_module._control_plane_source_root(config)
    assert control_plane != repository.resolve()
    assert (control_plane / "scripts" / "operator_server.py").is_file()
    assert (control_plane / "scripts" / "local_worker.py").is_file()
    token = f"operator-synthetic-{uuid.uuid4().hex}"
    monkeypatch.setenv("SWITCHBOARD_ADMIN_TOKEN", token)
    approvals: list[str] = []
    verified = False
    target_before = (
        _git(repository, "rev-parse", "HEAD"),
        _git(repository, "status", "--porcelain=v2", "--untracked-files=all"),
        (repository / "README.md").read_bytes(),
    )
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
        worker_config = json.loads(
            (runtime_root / "worker-config.json").read_text(encoding="utf-8")
        )
        assert worker_config["repositories"] == {
            "Nobodyworld/dev-agent-switchboard": str(repository)
        }
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
        target_after = (
            _git(repository, "rev-parse", "HEAD"),
            _git(repository, "status", "--porcelain=v2", "--untracked-files=all"),
            (repository / "README.md").read_bytes(),
        )
        assert target_after == target_before
        assert target_before[:2] == (sha, "")
        assert target_before[2] in {b"fixture\n", b"fixture\r\n"}
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
