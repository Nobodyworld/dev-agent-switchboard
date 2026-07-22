# ruff: noqa: S603, S607
"""Contained evidence storage, hashing, parser, and retention boundaries."""

from __future__ import annotations

import datetime as dt
import hashlib
import os
import subprocess
from pathlib import Path

import pytest

from client.python.execution_worker.evidence import (
    EvidenceLimits,
    create_evidence_store,
    prune_expired_evidence,
)
from client.python.execution_worker.parsers import parse_result
from server.execution.registry import TrustedArtifact

_NOW = dt.datetime(2026, 7, 1, tzinfo=dt.UTC)


def _store(tmp_path: Path, **limits: int):
    repository = tmp_path / "repository"
    worker = tmp_path / "worker"
    repository.mkdir(exist_ok=True)
    return create_evidence_store(
        evidence_root=tmp_path / "evidence",
        worker_root=worker,
        repository_roots=(repository,),
        worker_id="worker-1",
        run_id=7,
        created_at=_NOW,
        retention_days=14,
        limits=EvidenceLimits(
            maximum_artifact_count=limits.get("count", 4),
            maximum_artifact_bytes=limits.get("artifact_bytes", 1024),
            maximum_total_bytes=limits.get("total_bytes", 2048),
        ),
    )


def _declaration(path: str = "logs/step.stdout.log") -> TrustedArtifact:
    return TrustedArtifact(
        kind="command-log",
        relative_path=path,
        media_type="text/plain",
        redaction_state="none",
    )


def test_marker_artifact_hash_size_and_deterministic_expiry(tmp_path: Path) -> None:
    store = _store(tmp_path)
    content = b"bounded evidence\n"
    path = store.logs / "step.stdout.log"
    path.write_bytes(content)

    records = store.finalize_artifacts((("step", _declaration()),))

    assert store.expected_marker()["schema_version"] == 1
    assert records[0].relative_path == "logs/step.stdout.log"
    assert records[0].size_bytes == len(content)
    assert records[0].sha256 == hashlib.sha256(content).hexdigest()
    assert records[0].retention_expires_at == _NOW + dt.timedelta(days=14)


@pytest.mark.parametrize(
    ("limits", "message"),
    [
        ({"count": 1}, "count"),
        ({"artifact_bytes": 2, "total_bytes": 4}, "per artifact"),
        ({"artifact_bytes": 8, "total_bytes": 8}, "total evidence"),
    ],
)
def test_artifact_count_and_byte_limits(
    tmp_path: Path, limits: dict[str, int], message: str
) -> None:
    store = _store(tmp_path, **limits)
    (store.logs / "step.stdout.log").write_bytes(b"123456")
    (store.logs / "step.stderr.log").write_bytes(b"123456")
    declarations = (
        ("step", _declaration()),
        ("step", _declaration("logs/step.stderr.log")),
    )

    with pytest.raises(ValueError, match=message):
        store.finalize_artifacts(declarations)


def test_artifact_must_be_regular_and_evidence_root_must_not_overlap(
    tmp_path: Path,
) -> None:
    store = _store(tmp_path)
    (store.logs / "step.stdout.log").mkdir()
    with pytest.raises(ValueError, match="regular"):
        store.finalize_artifacts((("step", _declaration()),))

    repository = tmp_path / "overlap-repository"
    repository.mkdir()
    with pytest.raises(ValueError, match="must not overlap"):
        create_evidence_store(
            evidence_root=repository / "evidence",
            worker_root=tmp_path / "other-worker",
            repository_roots=(repository,),
            worker_id="worker-1",
            run_id=8,
            created_at=_NOW,
            retention_days=14,
            limits=EvidenceLimits(1, 1, 1),
        )


@pytest.mark.skipif(os.name == "nt", reason="POSIX symlink artifact coverage")
def test_artifact_symlink_is_rejected(tmp_path: Path) -> None:
    store = _store(tmp_path)
    outside = tmp_path / "outside.log"
    outside.write_text("outside", encoding="utf-8")
    (store.logs / "step.stdout.log").symlink_to(outside)
    with pytest.raises(ValueError, match=r"symlink|reparse"):
        store.finalize_artifacts((("step", _declaration()),))


@pytest.mark.skipif(os.name != "nt", reason="Windows reparse artifact coverage")
def test_artifact_junction_is_rejected(tmp_path: Path) -> None:
    store = _store(tmp_path)
    outside = tmp_path / "outside"
    outside.mkdir()
    junction = store.logs / "linked"
    subprocess.run(
        ["cmd", "/c", "mklink", "/J", str(junction), str(outside)],
        check=True,
        shell=False,
        capture_output=True,
        text=True,
    )
    try:
        with pytest.raises(ValueError, match=r"reparse|escaped"):
            store.finalize_artifacts(
                (("step", _declaration("logs/linked/output.log")),)
            )
    finally:
        subprocess.run(
            ["cmd", "/c", "rmdir", str(junction)],
            check=False,
            shell=False,
            capture_output=True,
            text=True,
        )


def test_marker_verified_retention_prunes_only_expired_owned_runs(
    tmp_path: Path,
) -> None:
    store = _store(tmp_path)
    result = prune_expired_evidence(
        store.root, worker_id="worker-1", now=_NOW + dt.timedelta(days=15)
    )
    assert result.removed_run_ids == (7,)
    assert result.failures == ()
    assert not store.run_directory.exists()
    assert (
        prune_expired_evidence(
            store.root, worker_id="worker-1", now=_NOW + dt.timedelta(days=15)
        ).removed_run_ids
        == ()
    )


def test_retention_refuses_ambiguous_marker(tmp_path: Path) -> None:
    store = _store(tmp_path)
    store.marker.write_text("{}", encoding="utf-8")
    result = prune_expired_evidence(
        store.root, worker_id="worker-1", now=_NOW + dt.timedelta(days=15)
    )
    assert result.removed_run_ids == ()
    assert result.failures == ("run-7:RuntimeError",)
    assert store.run_directory.exists()


def test_trusted_parsers_report_counts_coverage_audits_and_failure(
    tmp_path: Path,
) -> None:
    stdout = tmp_path / "stdout.log"
    stderr = tmp_path / "stderr.log"
    stderr.write_text("", encoding="utf-8")
    stdout.write_text(
        "TOTAL 100 25 75%\n2 passed, 1 skipped in 0.1s\n", encoding="utf-8"
    )
    parsed = parse_result(
        "pytest-coverage",
        stdout_path=stdout,
        stderr_path=stderr,
        command_succeeded=True,
    )
    assert parsed.status == "parsed"
    expected_test_total = len(("passed", "passed", "skipped"))
    expected_coverage_percent = float("75")
    assert parsed.tests is not None and parsed.tests.total == expected_test_total
    assert (
        parsed.coverage is not None
        and parsed.coverage.measured_percent == expected_coverage_percent
    )

    stdout.write_text("No broken requirements found.\n", encoding="utf-8")
    audit = parse_result(
        "dependency-audit",
        stdout_path=stdout,
        stderr_path=stderr,
        command_succeeded=True,
    )
    assert audit.audit is not None and audit.audit.findings == 0

    stdout.write_text("unstructured", encoding="utf-8")
    failed = parse_result(
        "pytest",
        stdout_path=stdout,
        stderr_path=stderr,
        command_succeeded=False,
    )
    assert failed.status == "parser_failed"
    assert failed.tests is None
