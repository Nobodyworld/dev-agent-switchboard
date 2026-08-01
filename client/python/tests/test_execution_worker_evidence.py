# ruff: noqa: S603, S607
"""Contained evidence storage, hashing, parser, and retention boundaries."""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import os
import subprocess
from pathlib import Path
from unittest.mock import patch

import pytest

from client.python.execution_worker import evidence as evidence_module
from client.python.execution_worker.evidence import (
    EvidenceLimits,
    create_evidence_store,
    prune_expired_evidence,
    verify_reuse_candidate,
)
from client.python.execution_worker.parsers import parse_result
from server.execution.evidence import (
    ArtifactRecord,
    EnvironmentIdentity,
    EvidenceReuseIdentity,
    EvidenceReuseProvenance,
    ExecutionEvidence,
    ExecutionEvidenceDraft,
    ReuseCandidate,
    compute_reuse_identity_hash,
    finalize_evidence,
)
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
    with pytest.raises(ValueError, match=r"symlink|reparse|escaped"):
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


def _reusable_source(
    tmp_path: Path, *, content: bytes = b"verified evidence\n"
) -> tuple[Path, ReuseCandidate]:
    tmp_path.mkdir(parents=True, exist_ok=True)
    store = _store(tmp_path, artifact_bytes=8192, total_bytes=16384)
    artifact_path = store.logs / "step.stdout.log"
    artifact_path.write_bytes(content)
    artifacts = store.finalize_artifacts((("step", _declaration()),))
    identity = EvidenceReuseIdentity(
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
    identity_hash = compute_reuse_identity_hash(identity)
    evidence = finalize_evidence(
        ExecutionEvidenceDraft(
            work_order_id=3,
            run_id=7,
            repository_full_name=identity.repository_full_name,
            tested_sha=identity.tested_sha,
            manifest_name=identity.manifest_name,
            manifest_version=identity.manifest_version,
            manifest_digest=identity.manifest_digest,
            worker_id="worker-1",
            environment=EnvironmentIdentity(
                operating_system="test",
                architecture="test",
                python_version="3.11",
                fingerprint=identity.worker_environment_fingerprint,
            ),
            started_at=_NOW,
            finished_at=_NOW + dt.timedelta(seconds=1),
            duration_seconds=1,
            terminal_status="succeeded",
            steps=[],
            artifacts=artifacts,
            dependency_lock_status="not_declared",
            artifact_finalization_status="succeeded",
            source_cleanup_status="succeeded",
            local_record_status="succeeded",
            reuse_provenance=EvidenceReuseProvenance(
                decision="fresh",
                reason="reuse_policy_never",
                reuse_identity_hash=identity_hash,
            ),
        )
    )
    store.write_result(
        {
            "evidence": evidence.model_dump(mode="json"),
            "result_summary": {"steps": []},
            "reuse_identity": identity.model_dump(mode="json"),
            "reuse_identity_hash": identity_hash,
        }
    )
    return store.root, ReuseCandidate(
        source_run_id=7,
        expected_source_worker_id="worker-1",
        expected_source_evidence_fingerprint=evidence.fingerprint,
        reuse_identity=identity,
        reuse_identity_hash=identity_hash,
        source_created_at=store.created_at,
        retention_expires_at=store.retention_expires_at,
        artifacts=artifacts,
    )


def _verify(root: Path, candidate: ReuseCandidate, **limits: int):
    return verify_reuse_candidate(
        evidence_root=root,
        worker_id="worker-1",
        candidate=candidate,
        now=_NOW + dt.timedelta(minutes=1),
        limits=EvidenceLimits(
            maximum_artifact_count=4,
            maximum_artifact_bytes=limits.get("artifact_bytes", 4096),
            maximum_total_bytes=limits.get("total_bytes", 8192),
        ),
    )


def test_reuse_candidate_requires_complete_local_cryptographic_proof(
    tmp_path: Path,
) -> None:
    root, candidate = _reusable_source(tmp_path)
    assert _verify(root, candidate).reason == "exact_evidence_verified"

    (root / "run-7" / "logs" / "step.stdout.log").write_bytes(b"changed bytes\n")
    changed = _verify(root, candidate)
    assert not changed.verified
    assert changed.reason in {
        "source_artifact_size_mismatch",
        "source_artifact_hash_mismatch",
    }


def test_reuse_rejects_missing_expired_wrong_worker_and_wrong_marker(
    tmp_path: Path,
) -> None:
    root, candidate = _reusable_source(tmp_path)
    missing = candidate.model_copy(update={"source_run_id": 8})
    assert _verify(root, missing).reason == "source_evidence_missing"

    expired = verify_reuse_candidate(
        evidence_root=root,
        worker_id="worker-1",
        candidate=candidate,
        now=candidate.retention_expires_at,
        limits=EvidenceLimits(4, 4096, 8192),
    )
    assert expired.reason == "source_evidence_expired"

    wrong_worker = verify_reuse_candidate(
        evidence_root=root,
        worker_id="worker-2",
        candidate=candidate,
        now=_NOW + dt.timedelta(minutes=1),
        limits=EvidenceLimits(4, 4096, 8192),
    )
    assert wrong_worker.reason == "source_worker_mismatch"

    marker = root / "run-7" / "ownership.json"
    payload = json.loads(marker.read_text(encoding="utf-8"))
    payload["worker_id"] = "worker-2"
    marker.write_text(json.dumps(payload), encoding="utf-8")
    assert _verify(root, candidate).reason == "source_marker_invalid"


def test_reuse_rejects_database_only_and_malformed_result_records(
    tmp_path: Path,
) -> None:
    root, candidate = _reusable_source(tmp_path)
    result = root / "run-7" / "result.json"
    result.unlink()
    assert _verify(root, candidate).reason == "source_evidence_missing"

    root, candidate = _reusable_source(tmp_path / "malformed")
    result = root / "run-7" / "result.json"
    result.write_text('{"unexpected":true}', encoding="utf-8")
    assert _verify(root, candidate).reason == "source_result_invalid"


def test_reuse_rejects_nonregular_and_oversized_artifacts(tmp_path: Path) -> None:
    root, candidate = _reusable_source(tmp_path / "nonregular")
    artifact = root / "run-7" / "logs" / "step.stdout.log"
    artifact.unlink()
    artifact.mkdir()
    assert _verify(root, candidate).reason == "source_artifact_unsafe"

    root, candidate = _reusable_source(tmp_path / "oversized", content=b"x" * 8192)
    oversized = _verify(root, candidate, artifact_bytes=4096, total_bytes=16384)
    assert oversized.reason == "source_artifact_oversized"

    too_many = verify_reuse_candidate(
        evidence_root=root,
        worker_id="worker-1",
        candidate=candidate,
        now=_NOW + dt.timedelta(minutes=1),
        limits=EvidenceLimits(0, 16384, 16384),
    )
    assert too_many.reason == "source_artifact_count_oversized"


def test_reuse_fails_closed_when_pruning_races_artifact_hash(
    tmp_path: Path,
) -> None:
    root, candidate = _reusable_source(tmp_path)
    artifact = root / "run-7" / "logs" / "step.stdout.log"
    original_sha256 = hashlib.sha256

    def hash_then_prune(path: Path) -> str:
        digest = original_sha256(path.read_bytes()).hexdigest()
        path.unlink()
        return digest

    with patch(
        "client.python.execution_worker.evidence._sha256", side_effect=hash_then_prune
    ):
        result = _verify(root, candidate)
    assert not result.verified
    assert result.reason == "source_evidence_pruned"
    assert not artifact.exists()


@pytest.mark.skipif(os.name == "nt", reason="POSIX symlink reuse coverage")
def test_reuse_rejects_symlinked_source_artifact(tmp_path: Path) -> None:
    root, candidate = _reusable_source(tmp_path)
    artifact = root / "run-7" / "logs" / "step.stdout.log"
    outside = tmp_path / "outside.log"
    outside.write_bytes(artifact.read_bytes())
    artifact.unlink()
    artifact.symlink_to(outside)
    assert _verify(root, candidate).reason == "source_artifact_unsafe"


@pytest.mark.skipif(os.name != "nt", reason="Windows junction reuse coverage")
def test_reuse_rejects_junctioned_source_artifact(tmp_path: Path) -> None:
    root, candidate = _reusable_source(tmp_path)
    logs = root / "run-7" / "logs"
    original = logs / "step.stdout.log"
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "step.stdout.log").write_bytes(original.read_bytes())
    original.unlink()
    junction = logs / "linked"
    subprocess.run(
        ["cmd", "/c", "mklink", "/J", str(junction), str(outside)],
        check=True,
        shell=False,
        capture_output=True,
        text=True,
    )
    try:
        result_path = root / "run-7" / "result.json"
        result_payload = json.loads(result_path.read_text(encoding="utf-8"))
        source_evidence = ExecutionEvidence.model_validate(result_payload["evidence"])
        linked_record = ArtifactRecord.model_validate(
            {
                **candidate.artifacts[0].model_dump(mode="json"),
                "relative_path": "logs/linked/step.stdout.log",
            }
        )
        evidence_payload = source_evidence.model_dump(
            mode="json", exclude={"fingerprint"}
        )
        evidence_payload["artifacts"] = [linked_record.model_dump(mode="json")]
        linked_evidence = finalize_evidence(
            ExecutionEvidenceDraft.model_validate(evidence_payload)
        )
        result_payload["evidence"] = linked_evidence.model_dump(mode="json")
        result_payload["reuse_identity"] = candidate.reuse_identity.model_dump(
            mode="json"
        )
        result_payload["reuse_identity_hash"] = candidate.reuse_identity_hash
        result_path.write_text(
            json.dumps(result_payload, sort_keys=True, separators=(",", ":")),
            encoding="utf-8",
        )
        linked_payload = candidate.model_dump(mode="json")
        linked_payload["expected_source_evidence_fingerprint"] = (
            linked_evidence.fingerprint
        )
        linked_payload["artifacts"] = [linked_record.model_dump(mode="json")]
        linked = ReuseCandidate.model_validate(linked_payload)

        original_safe_path = evidence_module._safe_path
        with patch.object(
            evidence_module,
            "_safe_path",
            wraps=original_safe_path,
        ) as safe_path_check:
            verification = _verify(root, linked)
        assert verification.reason == "source_artifact_unsafe"
        assert any(
            call.args[0] == root / "run-7"
            and call.args[1] == "logs/linked/step.stdout.log"
            for call in safe_path_check.call_args_list
        )
    finally:
        subprocess.run(
            ["cmd", "/c", "rmdir", str(junction)],
            check=False,
            shell=False,
            capture_output=True,
            text=True,
        )
