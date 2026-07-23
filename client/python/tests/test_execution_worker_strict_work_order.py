"""Complete work-order validation before any local execution side effect."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from client.python.execution_worker.config import WorkerConfig
from client.python.execution_worker.models import AssignedWorkOrder
from client.python.execution_worker.worker import LocalWorker
from client.python.tests.execution_worker_test_support import work_order_payload
from client.python.tests.test_execution_worker_runtime import _FakeClient
from server.execution.registry import get_trusted_manifest

_TOKEN = "strict-work-order-token"  # noqa: S105 - non-secret test fixture


def _payload(**overrides: object) -> dict[str, object]:
    manifest = get_trusted_manifest("worker-smoke", "1")
    assert manifest is not None
    return work_order_payload("a" * 40, manifest, **overrides)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("manifest_parameters", {"nested": [{"shell-command": "no"}]}),
        ("resource_metadata", {"nested": {"SCRIPT CONTENTS": "no"}}),
        ("required_capabilities", {"nested": [{"executable_path": "no"}]}),
    ],
)
def test_recursive_executable_fields_are_rejected(field: str, value: object) -> None:
    with pytest.raises(ValueError, match="executable field"):
        AssignedWorkOrder.from_payload(_payload(**{field: value}))


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("manifest_parameters", []),
        ("resource_metadata", []),
        ("required_capabilities", []),
        ("permitted_paths", {}),
        ("expected_artifact_kinds", {}),
    ],
)
def test_malformed_mapping_and_list_roots_are_rejected(
    field: str, value: object
) -> None:
    with pytest.raises(ValueError, match="invalid"):
        AssignedWorkOrder.from_payload(_payload(**{field: value}))


def test_unknown_work_order_response_field_is_rejected() -> None:
    payload = _payload()
    payload["future_field"] = "unreviewed"

    with pytest.raises(ValueError, match="response fields"):
        AssignedWorkOrder.from_payload(payload)


@pytest.mark.parametrize("created_at", [True, 7, "2026-07-16", "not-a-datetime"])
def test_lifecycle_datetime_fields_require_exact_iso_datetime_strings(
    created_at: object,
) -> None:
    with pytest.raises(ValueError, match="created_at"):
        AssignedWorkOrder.from_payload(_payload(created_at=created_at))


@pytest.mark.parametrize(
    "required_capabilities",
    [
        {"repository_write": True},
        {"nested": {"repository_write": False}},
        {"nested": {"repository_write_policy": "read_only"}},
    ],
)
def test_nested_or_write_enabling_repository_policy_is_rejected(
    required_capabilities: object,
) -> None:
    with pytest.raises(ValueError, match="repository-write"):
        AssignedWorkOrder.from_payload(
            _payload(required_capabilities=required_capabilities)
        )


def test_known_read_only_capability_is_accepted() -> None:
    order = AssignedWorkOrder.from_payload(
        _payload(required_capabilities={"repository_write": False})
    )

    assert order.required_capabilities == {"repository_write": False}


def test_unsupported_manifest_parameters_reject_before_worktree_or_process(
    tmp_path: Path,
) -> None:
    manifest = get_trusted_manifest("worker-smoke", "1")
    assert manifest is not None
    order = work_order_payload(
        "a" * 40, manifest, manifest_parameters={"unsupported": "value"}
    )
    client = _FakeClient(order, manifest)
    config = WorkerConfig(
        base_url="http://localhost:8000",
        worker_id="worker-1",
        display_name="Worker 1",
        admin_token=_TOKEN,
        worker_root=tmp_path / "worker-root",
        evidence_root=tmp_path / "evidence-root",
        repositories={"Nobodyworld/dev-agent-switchboard": tmp_path / "canonical"},
    )
    worker = LocalWorker(config, client)  # type: ignore[arg-type]

    with (
        patch("client.python.execution_worker.worker.create_worktree") as create,
        patch("client.python.execution_worker.runner.subprocess.Popen") as popen,
    ):
        assert worker.poll_once() is True

    create.assert_not_called()
    popen.assert_not_called()
    assert client.completed[0]["status"] == "failed"
    assert client.completed[0]["cleanup_status"] == "not_started"


def test_nonempty_worker_smoke_parameters_are_rejected_before_side_effects(
    tmp_path: Path,
) -> None:
    test_unsupported_manifest_parameters_reject_before_worktree_or_process(tmp_path)
