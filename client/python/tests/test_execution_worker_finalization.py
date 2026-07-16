"""Valid bounded result JSON and truthful local-record failure coverage."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from client.python.execution_worker.models import AssignedWorkOrder
from client.python.execution_worker.runner import StepResult
from client.python.execution_worker.worker import RESULT_SUMMARY_LIMIT, LocalWorker
from client.python.tests.execution_worker_test_support import work_order_payload
from client.python.tests.test_execution_worker_runtime import (
    _config,
    _FakeClient,
    _repository,
)
from server.execution.enums import NetworkPolicy, RepositoryWritePolicy
from server.execution.registry import TrustedManifest, TrustedStep, get_trusted_manifest

_FAILED_EXIT_CODE = 17
_ROUNDED_DURATION = 1.235


def _large_result(step_id: str) -> StepResult:
    return StepResult(
        step_id=step_id,
        status="failed",
        exit_code=_FAILED_EXIT_CODE,
        duration_seconds=1.23456,
        stdout_summary="out" * 5000,
        stderr_summary="err" * 5000,
        summaries_truncated=True,
        stdout_log=f"{step_id}.stdout.log",
        stderr_log=f"{step_id}.stderr.log",
        environment_summary={"PATH": "[SET]", "TOKEN": "[REDACTED]"},
        terminal_reason="total_output_limit_exceeded",
    )


def test_large_result_compacts_fields_but_preserves_valid_required_metadata(
    tmp_path: Path,
) -> None:
    manifest = get_trusted_manifest("worker-smoke", "1")
    assert manifest is not None
    order = AssignedWorkOrder.from_payload(work_order_payload("a" * 40, manifest))
    results = [_large_result("first"), _large_result("second")]

    summary = LocalWorker._summary(order, results)
    serialized = LocalWorker._serialize_summary(summary)
    parsed = json.loads(serialized)

    assert len(serialized) <= RESULT_SUMMARY_LIMIT
    assert parsed["checked_out_sha"] == "a" * 40
    assert parsed["result_summary_truncated"] is True
    assert [step["id"] for step in parsed["steps"]] == ["first", "second"]
    for step in parsed["steps"]:
        assert step["status"] == "failed"
        assert step["exit_code"] == _FAILED_EXIT_CODE
        assert step["duration_seconds"] == _ROUNDED_DURATION
        assert step["terminal_reason"] == "total_output_limit_exceeded"
        assert step["truncated"] is True
        assert step["logs"] == [
            f"logs/{step['id']}.stdout.log",
            f"logs/{step['id']}.stderr.log",
        ]
        assert step["environment"] == {"PATH": "[SET]", "TOKEN": "[REDACTED]"}

    LocalWorker._write_run_record(
        SimpleNamespace(run_directory=tmp_path),  # type: ignore[arg-type]
        terminal="failed",
        reason="total_output_limit_exceeded",
        cleanup="succeeded",
        summary=summary,
    )
    record = json.loads((tmp_path / "result.json").read_text(encoding="utf-8"))
    assert record["result_summary"] == parsed


def test_local_record_write_failure_downgrades_success_and_completes_once(
    tmp_path: Path,
) -> None:
    canonical, sha = _repository(tmp_path)
    manifest = get_trusted_manifest("worker-smoke", "1")
    assert manifest is not None
    client = _FakeClient(work_order_payload(sha, manifest), manifest)
    worker = LocalWorker(_config(tmp_path, canonical), client)  # type: ignore[arg-type]

    with patch.object(LocalWorker, "_write_run_record", side_effect=OSError("disk")):
        assert worker.poll_once() is True

    assert len(client.completed) == 1
    completion = client.completed[0]
    assert completion["status"] == "failed"
    assert completion["terminal_reason"] == "local_result_record_failed"
    assert "local_record_failed:OSError" in str(completion["cleanup_status"])
    assert completion["evidence_metadata"]["local_record"] is None
    assert worker._active_run_id is None


def test_local_record_failure_preserves_original_execution_failure(
    tmp_path: Path, monkeypatch
) -> None:
    canonical, sha = _repository(tmp_path)
    step = TrustedStep(
        id="failing-step",
        title="Fixed failing test step",
        argv=(sys.executable, "-c", "raise SystemExit(3)"),
        required=True,
        timeout_seconds=10,
    )
    manifest = TrustedManifest(
        name="test-failure",
        version="1",
        schema_version=1,
        description="fixed failure manifest",
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
    client = _FakeClient(work_order_payload(sha, manifest), manifest)
    monkeypatch.setattr(
        "client.python.execution_worker.worker.get_trusted_manifest",
        lambda _name, _version: manifest,
    )
    worker = LocalWorker(_config(tmp_path, canonical), client)  # type: ignore[arg-type]

    with patch.object(LocalWorker, "_write_run_record", side_effect=OSError("disk")):
        assert worker.poll_once() is True

    assert len(client.completed) == 1
    completion = client.completed[0]
    assert completion["status"] == "failed"
    assert completion["terminal_reason"] == "required_step_failed:failing-step"
    assert "local_record_failed:OSError" in str(completion["cleanup_status"])
