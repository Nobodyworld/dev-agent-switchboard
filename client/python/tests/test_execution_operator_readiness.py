# ruff: noqa: PLR2004, S603, S607
"""Readiness observes the execution checks without granting execution authority."""

from __future__ import annotations

import hashlib
import json
import os
import socket
import subprocess
import uuid
from dataclasses import replace
from pathlib import Path

import pytest

from client.python.execution_operator import lifecycle, preflight, processes
from client.python.execution_operator.config import OperatorLifecycleConfig
from client.python.execution_operator.models import OperatorLifecycleFailure
from client.python.execution_operator.readiness import (
    ReadinessIdentity,
    ReadinessTimeouts,
    configuration_readiness_failure,
    inspect_validation_readiness,
)
from server.execution.registry import get_trusted_manifest


def _git(root: Path, *arguments: str) -> str:
    return subprocess.run(
        ["git", "-C", str(root), *arguments],
        check=True,
        shell=False,
        capture_output=True,
        text=True,
    ).stdout.strip()


@pytest.fixture
def ready_config(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> OperatorLifecycleConfig:
    target = tmp_path / "target"
    target.mkdir()
    _git(target, "init")
    _git(target, "config", "user.email", "operator@example.test")
    _git(target, "config", "user.name", "Operator Test")
    (target / "README.md").write_text("readiness fixture\n", encoding="utf-8")
    _git(target, "add", "README.md")
    _git(target, "commit", "-m", "fixture")
    _git(
        target,
        "remote",
        "add",
        "origin",
        "https://github.com/Example/readiness-fixture",
    )
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
        listener.bind(("127.0.0.1", 0))
        port = int(listener.getsockname()[1])
    root = (
        Path("C:/tmp") / f"pf157-{uuid.uuid4().hex[:8]}"
        if os.name == "nt"
        else tmp_path / "runtime"
    )
    monkeypatch.setenv("SWITCHBOARD_ADMIN_TOKEN", "test-only-readiness-admin")
    return OperatorLifecycleConfig.from_mapping(
        {
            "schema_version": 1,
            "repository_full_name": "Example/readiness-fixture",
            "canonical_checkout": str(target),
            "target_sha": _git(target, "rev-parse", "HEAD"),
            "manifest_name": "worker-smoke",
            "manifest_version": "1",
            "mode": "fresh-only",
            "runtime_root": str(root),
            "worker_id": "readiness-worker",
            "worker_display_name": "Readiness test worker",
            "port": port,
        }
    )


def _files(root: Path) -> dict[str, tuple[int, str]]:
    return {
        str(path.relative_to(root)): (
            path.stat().st_mtime_ns,
            hashlib.sha256(path.read_bytes()).hexdigest(),
        )
        for path in root.rglob("*")
        if path.is_file()
    }


def test_readiness_and_execution_share_checks_without_source_or_runtime_writes(
    ready_config: OperatorLifecycleConfig, monkeypatch: pytest.MonkeyPatch
) -> None:
    before = _files(ready_config.canonical_checkout)
    calls: list[list[str]] = []
    original = preflight.subprocess.run

    def read_only_probe(
        argv: list[str], **kwargs: object
    ) -> subprocess.CompletedProcess:
        calls.append(argv)
        assert kwargs["env"]["GIT_OPTIONAL_LOCKS"] == "0"
        assert "SWITCHBOARD_ADMIN_TOKEN" not in kwargs["env"]
        return original(argv, **kwargs)

    monkeypatch.setattr(preflight.subprocess, "run", read_only_probe)
    observed = inspect_validation_readiness(ready_config)
    executed = preflight.run_preflight(ready_config)
    repeated = inspect_validation_readiness(ready_config)
    assert observed.ready and repeated == observed
    assert executed.source.head_sha == ready_config.target_sha
    assert observed.identity.verified_manifest_digest == executed.manifest_digest
    assert observed.identity.repository_full_name == "Example/readiness-fixture"
    assert all(item.status == "pass" for item in observed.checks)
    assert all(item["checked"] for item in observed.as_dict()["checks"])
    assert observed.as_dict()["approval_granted"] is False
    assert _files(ready_config.canonical_checkout) == before
    assert not ready_config.runtime_root.exists()
    assert not (ready_config.canonical_checkout / "scripts/operator_server.py").exists()
    assert not (ready_config.canonical_checkout / "scripts/local_worker.py").exists()
    assert calls


@pytest.mark.parametrize(
    ("change", "reason", "failed_check"),
    [
        ("python", "python_version_unsupported", "python_runtime"),
        ("containment", "strict_containment_unsupported", "strict_containment"),
        ("root", "runtime_root_already_exists", "root_safety"),
        ("root_inspection", "canonical_checkout_invalid", "root_safety"),
        ("control_plane", "control_plane_source_invalid", "control_plane_source"),
        ("port", "loopback_port_occupied", "loopback_port"),
        ("token", "admin_token_missing", "process_token"),
        ("dirty", "source_checkout_dirty", "canonical_source"),
        ("sha", "source_head_mismatch", "canonical_source"),
        ("origin", "source_origin_mismatch", "canonical_source"),
        ("git", "git_probe_failed", "canonical_source"),
        ("manifest", "trusted_manifest_not_found", "manifest_contract"),
        ("digest", "trusted_manifest_digest_mismatch", "manifest_contract"),
        (
            "worker_timeout",
            "manifest_timeout_exceeds_worker_budget",
            "manifest_timeouts",
        ),
        (
            "terminal_timeout",
            "terminal_timeout_below_manifest_budget",
            "manifest_timeouts",
        ),
        ("capability", "worker_capability_mismatch", "worker_capabilities"),
    ],
)
def test_failure_parity_stops_unperformed_checks(  # noqa: PLR0912, PLR0913, PLR0917 - closed failure matrix
    ready_config: OperatorLifecycleConfig,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    change: str,
    reason: str,
    failed_check: str,
) -> None:
    config = ready_config
    if change == "python":
        monkeypatch.setattr(preflight.sys, "version_info", (3, 10))
    elif change == "containment":
        monkeypatch.setattr(preflight, "strict_containment_supported", lambda: False)
    elif change == "root":
        config = replace(config, runtime_root=tmp_path)
    elif change == "root_inspection":
        config = replace(config, canonical_checkout=tmp_path / "missing")
    elif change == "control_plane":

        def invalid_source(_config: OperatorLifecycleConfig) -> Path:
            raise OperatorLifecycleFailure("control_plane_source_invalid")

        monkeypatch.setattr(processes, "_control_plane_source_root", invalid_source)
    elif change == "port":
        monkeypatch.setattr(preflight, "_port_appears_available", lambda *_args: False)
    elif change == "token":
        monkeypatch.delenv("SWITCHBOARD_ADMIN_TOKEN")
    elif change == "dirty":
        (config.canonical_checkout / "untracked.txt").write_text("dirty\n")
    elif change == "sha":
        config = replace(config, target_sha="0" * 40)
    elif change == "origin":
        _git(
            config.canonical_checkout,
            "remote",
            "set-url",
            "origin",
            "https://wrong.test/private",
        )
    elif change == "git":
        monkeypatch.setattr(preflight.shutil, "which", lambda *_args, **_kwargs: None)
    elif change == "manifest":
        config = replace(config, manifest_name="unknown-manifest")
    elif change == "digest":
        config = replace(config, expected_manifest_digest="f" * 64)
    elif change == "worker_timeout":
        config = replace(config, work_order_timeout_seconds=1)
    elif change == "terminal_timeout":
        config = replace(config, terminal_timeout_seconds=1)
    elif change == "capability":
        monkeypatch.setattr(
            preflight, "_manifest_capabilities_compatible", lambda _requirements: False
        )
    before = (
        _files(config.canonical_checkout) if config.canonical_checkout.exists() else {}
    )
    result = inspect_validation_readiness(config)
    assert not result.ready and result.reason == reason
    names = [item.name for item in result.checks]
    failed_at = names.index(failed_check)
    assert all(item.status == "pass" for item in result.checks[:failed_at])
    assert result.checks[failed_at].status == "fail"
    assert all(item.status == "not_checked" for item in result.checks[failed_at + 1 :])
    assert result.as_json_bytes()
    with pytest.raises(OperatorLifecycleFailure, match=f"^{reason}$"):
        preflight.run_preflight(config)
    if config.canonical_checkout.exists():
        assert _files(config.canonical_checkout) == before
    assert not ready_config.runtime_root.exists()


def test_timeout_diagnostic_facts_retain_configured_and_required_limits(
    ready_config: OperatorLifecycleConfig,
) -> None:
    config = replace(ready_config, work_order_timeout_seconds=1)
    observed = inspect_validation_readiness(config)
    assert observed.timeouts.configured_worker_seconds == 1
    assert observed.timeouts.configured_terminal_seconds == 3900
    assert observed.timeouts.required_manifest_seconds == 120
    assert observed.timeouts.required_maximum_step_seconds == 60


@pytest.mark.parametrize("change", ["dirty", "occupied_port"])
def test_execution_rejects_readiness_that_became_stale(
    ready_config: OperatorLifecycleConfig, change: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    assert inspect_validation_readiness(ready_config).ready
    mutations: list[str] = []

    def forbidden_runtime(*_args: object) -> None:
        mutations.append("runtime")
        raise AssertionError("runtime must not be created")

    def forbidden_approval(_request: object) -> bool:
        mutations.append("approval")
        raise AssertionError("approval must not be requested")

    monkeypatch.setattr(lifecycle, "create_runtime", forbidden_runtime)
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
        if change == "dirty":
            (ready_config.canonical_checkout / "untracked.txt").write_text("dirty\n")
            reason = "source_checkout_dirty"
        else:
            listener.bind(("127.0.0.1", ready_config.port))
            listener.listen()
            reason = "loopback_port_occupied"
        with pytest.raises(OperatorLifecycleFailure, match=reason):
            lifecycle.run_validation_lifecycle(
                ready_config, approval=forbidden_approval
            )
    assert not mutations
    assert not ready_config.runtime_root.exists()


@pytest.mark.parametrize(
    "error",
    [OSError("private-path raw token"), OperatorLifecycleFailure("private_token")],
)
def test_probe_failures_never_expose_unreviewed_messages(
    ready_config: OperatorLifecycleConfig,
    monkeypatch: pytest.MonkeyPatch,
    error: Exception,
) -> None:
    def fail(_config: OperatorLifecycleConfig) -> preflight.SourceSnapshot:
        raise error

    monkeypatch.setattr(preflight, "source_snapshot", fail)
    result = inspect_validation_readiness(ready_config)
    assert result.reason == "preflight_probe_failed"
    for output in (result.as_json_bytes(), result.as_text()):
        assert b"private" not in output
        assert str(ready_config.canonical_checkout).encode() not in output
        assert b"test-only-readiness-admin" not in output


@pytest.mark.parametrize(
    "value",
    [
        "/private/path",
        "https://private.test",
        "secret=value",
        "test-only-readiness-admin",
    ],
)
def test_untrusted_manifest_version_is_not_echoed(
    ready_config: OperatorLifecycleConfig, value: str
) -> None:
    result = inspect_validation_readiness(replace(ready_config, manifest_version=value))
    assert result.identity.manifest_version is None
    assert result.reason == "invalid_configuration"
    assert not result.ready
    assert value.encode() not in result.as_json_bytes()
    assert value.encode() not in result.as_text()


@pytest.mark.parametrize(
    "value", ["ghp_test_only_fake_identity", "test-only-readiness-admin"]
)
def test_unsafe_worker_identity_fails_shared_configuration_check(
    ready_config: OperatorLifecycleConfig, value: str
) -> None:
    config = replace(ready_config, worker_id=value)
    result = inspect_validation_readiness(config)
    assert not result.ready and result.reason == "invalid_configuration"
    assert result.identity == ReadinessIdentity()
    with pytest.raises(OperatorLifecycleFailure, match="invalid_configuration"):
        preflight.run_preflight(config)
    assert value.encode() not in result.as_json_bytes()


def test_token_collision_with_manifest_digest_fails_without_publication(
    ready_config: OperatorLifecycleConfig, monkeypatch: pytest.MonkeyPatch
) -> None:
    manifest = get_trusted_manifest("worker-smoke", "1")
    assert manifest is not None
    monkeypatch.setenv("SWITCHBOARD_ADMIN_TOKEN", manifest.digest)
    result = inspect_validation_readiness(ready_config)
    assert not result.ready and result.reason == "public_identity_rejected"
    assert result.identity.verified_manifest_digest is None
    with pytest.raises(OperatorLifecycleFailure, match="public_identity_rejected"):
        preflight.run_preflight(ready_config)
    assert manifest.digest.encode() not in result.as_json_bytes()
    assert manifest.digest.encode() not in result.as_text()


def test_invalid_direct_configuration_is_safe_and_not_probed(
    ready_config: OperatorLifecycleConfig, monkeypatch: pytest.MonkeyPatch
) -> None:
    def fail() -> None:
        raise AssertionError("configuration failure must stop probes")

    monkeypatch.setattr(preflight, "_validate_python_runtime", fail)
    config = replace(ready_config, work_order_timeout_seconds=float("nan"))
    result = inspect_validation_readiness(config)
    assert result == configuration_readiness_failure("private values ignored")
    assert result.checks[0].status == "fail"
    assert all(item.status == "not_checked" for item in result.checks[1:])
    assert result.identity == ReadinessIdentity()
    assert result.timeouts == ReadinessTimeouts()


def test_readiness_report_serializers_are_bounded_and_consistent(
    ready_config: OperatorLifecycleConfig,
) -> None:
    result = inspect_validation_readiness(ready_config)
    assert json.loads(result.as_json_bytes()) == result.as_dict()
    assert b"approval: not granted" in result.as_text()
    assert b"execution reruns all checks" in result.as_text()
    for serializer in (result.as_json_bytes, result.as_text):
        with pytest.raises(OperatorLifecycleFailure, match="size_limit"):
            serializer(maximum_bytes=1)
    malformed = (
        replace(result, reason="private_value"),
        replace(result, ready=False),
        replace(result, checks=result.checks[:-1]),
        replace(result, identity=replace(result.identity, target_sha=None)),
        replace(
            result, identity=replace(result.identity, verified_manifest_digest=None)
        ),
        replace(
            result, identity=replace(result.identity, expected_manifest_digest="f" * 64)
        ),
        replace(
            result,
            identity=replace(result.identity, repository_full_name="/private/path"),
        ),
        replace(
            result, timeouts=ReadinessTimeouts(configured_worker_seconds=float("inf"))
        ),
        replace(result, timeouts=replace(result.timeouts, configured_worker_seconds=1)),
        replace(
            result, timeouts=replace(result.timeouts, configured_terminal_seconds=1)
        ),
        replace(
            result, timeouts=replace(result.timeouts, required_manifest_seconds=120.0)
        ),
        replace(
            result,
            timeouts=replace(result.timeouts, required_maximum_step_seconds=True),
        ),
    )
    for unsafe in malformed:
        for serialize in (unsafe.as_dict, unsafe.as_json_bytes, unsafe.as_text):
            with pytest.raises(
                OperatorLifecycleFailure, match="readiness_report_invalid"
            ):
                serialize()
