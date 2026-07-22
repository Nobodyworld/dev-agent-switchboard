"""Strict compact evidence contracts and canonical fingerprint coverage."""

from __future__ import annotations

import datetime as dt

import pytest
from pydantic import ValidationError

from server.execution.evidence import (
    ArtifactRecord,
    EnvironmentIdentity,
    ExecutionEvidence,
    ExecutionEvidenceDraft,
    StepEvidence,
    compute_evidence_fingerprint,
    finalize_evidence,
)
from server.execution.schemas import ExecutionCompletionIn

_NOW = dt.datetime(2026, 7, 21, 12, tzinfo=dt.UTC)
_DIGEST = "a" * 64
_SHA = "b" * 40


def _draft(**overrides: object) -> ExecutionEvidenceDraft:
    artifact = ArtifactRecord(
        kind="command-log",
        relative_path="logs/tests.stdout.log",
        size_bytes=4,
        sha256="c" * 64,
        media_type="text/plain",
        retention_expires_at=_NOW + dt.timedelta(days=14),
        redaction_state="none",
        produced_by_step="tests",
    )
    values: dict[str, object] = {
        "work_order_id": 3,
        "run_id": 7,
        "repository_full_name": "Nobodyworld/dev-agent-switchboard",
        "tested_sha": _SHA,
        "manifest_name": "validate-switchboard",
        "manifest_version": "1",
        "manifest_digest": _DIGEST,
        "worker_id": "worker-1",
        "environment": EnvironmentIdentity(
            operating_system="windows",
            architecture="amd64",
            python_version="3.11.9",
            fingerprint="d" * 64,
        ),
        "started_at": _NOW,
        "finished_at": _NOW + dt.timedelta(seconds=1),
        "duration_seconds": 1.0,
        "terminal_status": "succeeded",
        "steps": [
            StepEvidence(
                step_id="tests",
                title="Run tests",
                status="succeeded",
                started_at=_NOW,
                finished_at=_NOW + dt.timedelta(seconds=1),
                duration_seconds=1.0,
                exit_code=0,
                summary="1 passed",
                log_artifact_paths=[artifact.relative_path],
            )
        ],
        "artifacts": [artifact],
        "dependency_lock_status": "not_declared",
        "artifact_finalization_status": "succeeded",
        "source_cleanup_status": "succeeded",
        "local_record_status": "succeeded",
    }
    values.update(overrides)
    return ExecutionEvidenceDraft.model_validate(values)


def test_fingerprint_is_deterministic_and_identity_sensitive() -> None:
    first = finalize_evidence(_draft())
    second = finalize_evidence(_draft())
    changed = finalize_evidence(_draft(tested_sha="e" * 40))

    assert first == second
    assert first.fingerprint == compute_evidence_fingerprint(first)
    assert changed.fingerprint != first.fingerprint
    assert ExecutionEvidence.model_validate(first.model_dump(mode="json")) == first


@pytest.mark.parametrize(
    "path",
    [
        "C:/worker/log.txt",
        "/var/log.txt",
        "../escape.log",
        "logs/../escape.log",
        "logs\\escape.log",
        "logs//escape.log",
        "logs/CON",
    ],
)
def test_artifact_paths_reject_absolute_traversal_and_device_forms(path: str) -> None:
    with pytest.raises(ValidationError):
        ArtifactRecord(
            kind="command-log",
            relative_path=path,
            size_bytes=1,
            sha256="a" * 64,
            media_type="text/plain",
            retention_expires_at=_NOW,
            redaction_state="none",
        )


def test_models_forbid_unknown_fields_lowercase_hashes_and_nonfinite_numbers() -> None:
    payload = _draft().model_dump(mode="json")
    payload["unknown"] = True
    with pytest.raises(ValidationError):
        ExecutionEvidenceDraft.model_validate(payload)

    payload = _draft().model_dump(mode="json")
    payload["manifest_digest"] = "A" * 64
    with pytest.raises(ValidationError):
        ExecutionEvidenceDraft.model_validate(payload)

    payload = _draft().model_dump(mode="json")
    payload["duration_seconds"] = float("nan")
    with pytest.raises(ValidationError):
        ExecutionEvidenceDraft.model_validate(payload)


def test_fingerprint_mismatch_and_oversized_summary_are_rejected() -> None:
    evidence = finalize_evidence(_draft())
    payload = evidence.model_dump(mode="json")
    payload["fingerprint"] = "0" * 64
    with pytest.raises(ValidationError, match="fingerprint"):
        ExecutionEvidence.model_validate(payload)

    step = payload["steps"][0]
    assert isinstance(step, dict)
    step["summary"] = "x" * 4097
    with pytest.raises(ValidationError):
        ExecutionEvidence.model_validate(payload)


def test_compact_evidence_contains_no_absolute_paths_or_executable_shapes() -> None:
    payload = finalize_evidence(_draft()).model_dump_json()
    assert "C:\\" not in payload
    assert "/var/" not in payload
    assert '"argv"' not in payload
    assert '"command"' not in payload
    assert '"script"' not in payload


def test_completion_normalizes_legacy_empty_evidence_sentinel() -> None:
    completion = ExecutionCompletionIn.model_validate(
        {
            "worker_id": "worker-1",
            "status": "failed",
            "evidence_metadata": {},
        }
    )

    assert completion.evidence_metadata is None
