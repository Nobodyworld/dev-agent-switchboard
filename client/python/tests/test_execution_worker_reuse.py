# ruff: noqa: S603, S607
"""Worker lifecycle proof for exact local evidence reuse and fallback."""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any
from unittest.mock import patch

from client.python.execution_worker.client import ExecutionOwnershipLostError
from client.python.execution_worker.config import WorkerConfig
from client.python.execution_worker.runner import run_step as execute_trusted_step
from client.python.execution_worker.worker import LocalWorker
from client.python.tests.execution_worker_test_support import (
    remote_manifest_payload,
    work_order_payload,
)
from server.execution.evidence import ReuseCandidate
from server.execution.registry import TrustedManifest, get_trusted_manifest

_TOKEN = "reuse-test-token"  # noqa: S105 - synthetic fixture
_SOURCE_RUN_ID = 7
_REUSED_RUN_ID = 8


def _git(path: Path, *argv: str) -> str:
    return subprocess.run(
        ["git", "-C", str(path), *argv],
        check=True,
        shell=False,
        capture_output=True,
        text=True,
    ).stdout.strip()


def _repository(tmp_path: Path) -> tuple[Path, str]:
    repository = tmp_path / "canonical"
    subprocess.run(["git", "init", str(repository)], check=True, shell=False)
    _git(repository, "config", "user.email", "worker@example.test")
    _git(repository, "config", "user.name", "Worker Test")
    (repository / "README.md").write_text("initial\n", encoding="utf-8")
    _git(repository, "add", "README.md")
    _git(repository, "commit", "-m", "initial")
    return repository, _git(repository, "rev-parse", "HEAD")


def _config(tmp_path: Path, repository: Path) -> WorkerConfig:
    return WorkerConfig(
        base_url="http://localhost:8000",
        worker_id="worker-1",
        display_name="Reuse Worker",
        admin_token=_TOKEN,
        worker_root=tmp_path / "worker-root",
        evidence_root=tmp_path / "evidence-root",
        repositories={"Nobodyworld/dev-agent-switchboard": repository},
        heartbeat_interval_seconds=0.05,
    )


class _ReuseClient:
    def __init__(
        self,
        *,
        run_id: int,
        order: dict[str, Any],
        manifest: TrustedManifest,
        candidate: ReuseCandidate | None = None,
        lose_lookup_ownership: bool = False,
    ) -> None:
        self.run_id = run_id
        self.order = order
        self.manifest = manifest
        self.candidate = candidate
        self.lose_lookup_ownership = lose_lookup_ownership
        self.completed: list[dict[str, Any]] = []
        self.lookup_calls = 0

    def checkout(self) -> dict[str, object]:
        return {
            "run": {
                "id": self.run_id,
                "work_order_id": self.order["id"],
                "status": "assigned",
            }
        }

    def get_work_order(self, _work_order_id: int) -> dict[str, Any]:
        return self.order

    def get_manifest(self, _name: str, _version: str) -> dict[str, Any]:
        return remote_manifest_payload(self.manifest)

    def heartbeat_worker(self, *, status: str | None = None) -> dict[str, object]:
        _ = status
        return {}

    def heartbeat_run(self, _run_id: int) -> dict[str, object]:
        return {"id": self.run_id, "status": "running"}

    def get_run(self, _run_id: int) -> dict[str, object]:
        return {"id": self.run_id, "status": "running"}

    def resolve_reuse_candidate(
        self,
        _run_id: int,
        *,
        reuse_identity: dict[str, object],
        reuse_identity_hash: str,
    ) -> dict[str, object]:
        _ = (reuse_identity, reuse_identity_hash)
        self.lookup_calls += 1
        if self.lose_lookup_ownership:
            raise ExecutionOwnershipLostError(409)
        if self.candidate is None:
            return {
                "decision": "unavailable",
                "reason": "exact_candidate_not_found",
                "candidate": None,
            }
        return {
            "decision": "candidate_available",
            "reason": "exact_candidate_available",
            "candidate": self.candidate.model_dump(mode="json"),
        }

    def complete_run(self, _run_id: int, **payload: object) -> dict[str, object]:
        self.completed.append(dict(payload))
        return {"id": self.run_id, "status": payload["status"]}


def _candidate_from_completion(
    run_id: int, completion: dict[str, Any]
) -> ReuseCandidate:
    evidence = completion["evidence_metadata"]
    identity = completion["reuse_identity"]
    assert isinstance(evidence, dict)
    assert isinstance(identity, dict)
    return ReuseCandidate.model_validate(
        {
            "source_run_id": run_id,
            "expected_source_worker_id": "worker-1",
            "expected_source_evidence_fingerprint": evidence["fingerprint"],
            "reuse_identity": identity,
            "reuse_identity_hash": completion["reuse_identity_hash"],
            "source_created_at": evidence["started_at"],
            "retention_expires_at": completion["evidence_retention_expires_at"],
            "artifacts": completion["artifact_metadata"],
        }
    )


def _fresh_source(
    tmp_path: Path,
) -> tuple[Path, str, TrustedManifest, ReuseCandidate]:
    repository, sha = _repository(tmp_path)
    manifest = get_trusted_manifest("worker-smoke", "1")
    assert manifest is not None
    order = work_order_payload(sha, manifest, id=3, reuse_policy="never")
    client = _ReuseClient(run_id=_SOURCE_RUN_ID, order=order, manifest=manifest)
    worker = LocalWorker(_config(tmp_path, repository), client)  # type: ignore[arg-type]
    assert worker.poll_once() is True
    assert client.completed[0]["status"] == "succeeded"
    return (
        repository,
        sha,
        manifest,
        _candidate_from_completion(_SOURCE_RUN_ID, client.completed[0]),
    )


def test_fresh_then_allow_exact_reuses_without_validation_steps(tmp_path: Path) -> None:
    repository, sha, manifest, candidate = _fresh_source(tmp_path)
    order = work_order_payload(sha, manifest, id=4, reuse_policy="allow_exact")
    client = _ReuseClient(
        run_id=_REUSED_RUN_ID,
        order=order,
        manifest=manifest,
        candidate=candidate,
    )
    worker = LocalWorker(_config(tmp_path, repository), client)  # type: ignore[arg-type]

    with patch("client.python.execution_worker.worker.run_step") as run_step:
        assert worker.poll_once() is True

    run_step.assert_not_called()
    assert client.lookup_calls == 1
    assert client.completed[0]["status"] == "succeeded"
    assert client.completed[0]["reuse_decision"] == "reused"
    evidence = client.completed[0]["evidence_metadata"]
    assert evidence["run_id"] == _REUSED_RUN_ID
    assert evidence["reuse_provenance"]["source_run_id"] == _SOURCE_RUN_ID
    assert evidence["steps"] == []


def test_allow_exact_tamper_falls_back_fresh_exactly_once(tmp_path: Path) -> None:
    repository, sha, manifest, candidate = _fresh_source(tmp_path)
    result = tmp_path / "evidence-root" / "run-7" / "result.json"
    result.write_text('{"tampered":true}', encoding="utf-8")
    order = work_order_payload(sha, manifest, id=4, reuse_policy="allow_exact")
    client = _ReuseClient(
        run_id=_REUSED_RUN_ID,
        order=order,
        manifest=manifest,
        candidate=candidate,
    )
    worker = LocalWorker(_config(tmp_path, repository), client)  # type: ignore[arg-type]

    with patch(
        "client.python.execution_worker.worker.run_step", wraps=execute_trusted_step
    ) as run_step:
        assert worker.poll_once() is True

    assert client.lookup_calls == 1
    assert run_step.call_count == len(manifest.execution_steps)
    assert client.completed[0]["reuse_decision"] == "fresh"
    assert client.completed[0]["status"] == "succeeded"
    evidence = client.completed[0]["evidence_metadata"]
    assert len(evidence["steps"]) == len(manifest.execution_steps)


def test_require_exact_missing_candidate_never_invokes_validation(
    tmp_path: Path,
) -> None:
    repository, sha = _repository(tmp_path)
    manifest = get_trusted_manifest("worker-smoke", "1")
    assert manifest is not None
    order = work_order_payload(sha, manifest, id=3, reuse_policy="require_exact")
    client = _ReuseClient(run_id=7, order=order, manifest=manifest)
    worker = LocalWorker(_config(tmp_path, repository), client)  # type: ignore[arg-type]

    with patch("client.python.execution_worker.worker.run_step") as run_step:
        assert worker.poll_once() is True

    run_step.assert_not_called()
    assert client.completed[0]["status"] == "failed"
    assert client.completed[0]["reuse_decision"] == "unavailable"
    assert client.completed[0]["terminal_reason"] == "exact_candidate_not_found"


def test_ownership_loss_during_reuse_lookup_suppresses_execution_and_completion(
    tmp_path: Path,
) -> None:
    repository, sha = _repository(tmp_path)
    manifest = get_trusted_manifest("worker-smoke", "1")
    assert manifest is not None
    order = work_order_payload(sha, manifest, id=3, reuse_policy="allow_exact")
    client = _ReuseClient(
        run_id=7,
        order=order,
        manifest=manifest,
        lose_lookup_ownership=True,
    )
    worker = LocalWorker(_config(tmp_path, repository), client)  # type: ignore[arg-type]

    with patch("client.python.execution_worker.worker.run_step") as run_step:
        assert worker.poll_once() is True

    run_step.assert_not_called()
    assert client.completed == []
