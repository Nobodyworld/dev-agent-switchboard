# ruff: noqa: S603, S607
"""Worker orchestration, ownership-loss, retention, and restart coverage."""

from __future__ import annotations

import subprocess
import sys
import time
from pathlib import Path
from typing import Any

import pytest

from client.python.execution_worker.client import ExecutionOwnershipLostError
from client.python.execution_worker.config import WorkerConfig
from client.python.execution_worker.worker import LocalWorker
from client.python.tests.execution_worker_test_support import (
    remote_manifest_payload,
    work_order_payload,
)
from server.execution.enums import NetworkPolicy, RepositoryWritePolicy
from server.execution.registry import TrustedManifest, TrustedStep, get_trusted_manifest

_TOKEN = "worker-test-token"  # noqa: S105 - non-secret test fixture
_CANCELLATION_SECONDS = 5
_DUPLICATE_COMPLETION_COUNT = 2


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


class _FakeClient:
    def __init__(self, order: dict[str, Any], manifest: TrustedManifest) -> None:
        self.order = order
        self.manifest = manifest
        self.checkout_count = 0
        self.completed: list[dict[str, Any]] = []
        self.heartbeat_count = 0

    def checkout(self) -> dict[str, object]:
        self.checkout_count += 1
        return {"run": {"id": 7, "work_order_id": 3, "status": "assigned"}}

    def get_work_order(self, _work_order_id: int) -> dict[str, Any]:
        return self.order

    def get_manifest(self, _name: str, _version: str) -> dict[str, Any]:
        return remote_manifest_payload(self.manifest)

    def heartbeat_worker(self, *, status: str | None = None) -> dict[str, object]:
        _ = status
        return {}

    def heartbeat_run(self, _run_id: int) -> dict[str, object]:
        self.heartbeat_count += 1
        return {"id": 7, "status": "running"}

    def get_run(self, _run_id: int) -> dict[str, object]:
        return {"id": 7, "status": "running"}

    def complete_run(self, _run_id: int, **payload: object) -> dict[str, object]:
        self.completed.append(dict(payload))
        return {"id": 7, "status": payload["status"]}

    def register_worker(self, _registration: dict[str, object]) -> dict[str, object]:
        return {}


def _config(tmp_path: Path, repository: Path, **overrides: object) -> WorkerConfig:
    values: dict[str, object] = {
        "base_url": "http://localhost:8000",
        "worker_id": "worker-1",
        "display_name": "Worker 1",
        "admin_token": _TOKEN,
        "worker_root": tmp_path / "worker-root",
        "repositories": {"Nobodyworld/dev-agent-switchboard": repository},
        "heartbeat_interval_seconds": 0.05,
    }
    values.update(overrides)
    return WorkerConfig(**values)  # type: ignore[arg-type]


def _order(sha: str, manifest: TrustedManifest) -> dict[str, object]:
    return work_order_payload(sha, manifest)


def test_worker_smoke_retains_logs_removes_checkout_and_reports_exact_sha(
    tmp_path: Path,
) -> None:
    canonical, sha = _repository(tmp_path)
    manifest = get_trusted_manifest("worker-smoke", "1")
    assert manifest is not None
    client = _FakeClient(_order(sha, manifest), manifest)
    worker = LocalWorker(_config(tmp_path, canonical), client)  # type: ignore[arg-type]

    assert worker.poll_once() is True

    run_directory = next((tmp_path / "worker-root").glob("run-*"))
    assert not (run_directory / "checkout").exists()
    assert (run_directory / "logs" / "python-version.stdout.log").exists()
    assert (run_directory / "result.json").is_file()
    assert _git(canonical, "rev-parse", "HEAD") == sha
    assert client.completed[0]["status"] == "succeeded"
    assert sha in str(client.completed[0]["result_summary"])
    assert "logs/python-version.stdout.log" in str(
        client.completed[0]["result_summary"]
    )


@pytest.mark.parametrize("manifest_name", ["validate-switchboard", "worker-smoke"])
def test_manifest_rejection_creates_no_worktree_or_process(
    tmp_path: Path, manifest_name: str
) -> None:
    canonical, sha = _repository(tmp_path)
    manifest = get_trusted_manifest(manifest_name, "1")
    assert manifest is not None
    client = _FakeClient(_order(sha, manifest), manifest)
    if manifest_name == "worker-smoke":
        client.order["manifest_digest"] = "0" * 64
    worker = LocalWorker(_config(tmp_path, canonical), client)  # type: ignore[arg-type]

    assert worker.poll_once() is True

    assert not (tmp_path / "worker-root").exists()
    assert client.completed[0]["status"] == "failed"
    assert client.completed[0]["cleanup_status"] == "not_started"


def test_ownership_loss_before_worktree_skips_completion(tmp_path: Path) -> None:
    canonical, sha = _repository(tmp_path)
    manifest = get_trusted_manifest("worker-smoke", "1")
    assert manifest is not None
    client = _FakeClient(_order(sha, manifest), manifest)

    def lost(_run_id: int) -> dict[str, object]:
        raise ExecutionOwnershipLostError(409)

    client.heartbeat_run = lost  # type: ignore[method-assign]
    worker = LocalWorker(_config(tmp_path, canonical), client)  # type: ignore[arg-type]

    assert worker.poll_once() is True
    assert not (tmp_path / "worker-root").exists()
    assert client.completed == []


def test_mid_step_ownership_loss_cancels_without_success(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    canonical, sha = _repository(tmp_path)
    step = TrustedStep(
        id="long-safe-step",
        title="Long fixed test step",
        argv=(sys.executable, "-c", "import time; time.sleep(10)"),
        required=True,
        timeout_seconds=10,
        output_summary_limit=4096,
    )
    manifest = TrustedManifest(
        name="test-runtime",
        version="1",
        schema_version=1,
        description="fixed runtime test manifest",
        registry_source="client/python/tests",
        required_capabilities={"repository_write": False},
        fixed_step_metadata=[step.safe_metadata()],
        environment_policy={},
        network_policy=NetworkPolicy.WORKER_RESTRICTED,
        repository_write_policy=RepositoryWritePolicy.READ_ONLY,
        timeout_seconds=10,
        artifact_declarations=[],
        execution_steps=(step,),
    )
    client = _FakeClient(_order(sha, manifest), manifest)
    original = client.heartbeat_run

    def lose_after_initial(run_id: int) -> dict[str, object]:
        if client.heartbeat_count >= 1:
            raise ExecutionOwnershipLostError(409)
        return original(run_id)

    client.heartbeat_run = lose_after_initial  # type: ignore[method-assign]
    monkeypatch.setattr(
        "client.python.execution_worker.worker.get_trusted_manifest",
        lambda _name, _version: manifest,
    )
    worker = LocalWorker(
        _config(tmp_path, canonical, execution_timeout_seconds=10),
        client,  # type: ignore[arg-type]
    )

    started = time.monotonic()
    assert worker.poll_once() is True

    assert time.monotonic() - started < _CANCELLATION_SECONDS
    assert client.completed == []
    run_directory = next((tmp_path / "worker-root").glob("run-*"))
    assert not (run_directory / "checkout").exists()


def test_same_local_run_id_is_never_executed_twice(tmp_path: Path) -> None:
    canonical, sha = _repository(tmp_path)
    manifest = get_trusted_manifest("worker-smoke", "1")
    assert manifest is not None
    client = _FakeClient(_order(sha, manifest), manifest)
    worker = LocalWorker(_config(tmp_path, canonical), client)  # type: ignore[arg-type]

    assert worker.poll_once() is True
    assert worker.poll_once() is True
    assert len(client.completed) == _DUPLICATE_COMPLETION_COUNT
    assert client.completed[1]["status"] == "cancelled"
    assert (
        client.completed[1]["terminal_reason"]
        == "local_duplicate_execution_rejected_after_checkout"
    )
