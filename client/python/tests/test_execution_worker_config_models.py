"""Strict configuration and transport-model regressions for the local worker."""

from __future__ import annotations

from pathlib import Path

import pytest

from client.python.execution_worker.config import WorkerConfig
from client.python.execution_worker.models import AssignedWorkOrder, Checkout

_TOKEN = "worker-test-token"  # noqa: S105 - non-secret test fixture


def _payload(root: Path) -> dict[str, object]:
    return {
        "base_url": "http://localhost:8000",
        "worker_id": "worker-1",
        "display_name": "Worker 1",
        "worker_root": str(root / "worker"),
        "repositories": {"Nobodyworld/example": str(root / "canonical")},
        "max_concurrency": 1,
    }


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("base_url", 3),
        ("max_concurrency", "1"),
        ("execution_timeout_seconds", True),
        ("inherited_environment_keys", "PATH"),
        ("redacted_key_patterns", ["TOKEN", 3]),
        ("repositories", {"Nobodyworld/example": 3}),
        ("network_policy_capability", ["worker_restricted"]),
    ],
)
def test_worker_config_rejects_wrong_json_types(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    field: str,
    value: object,
) -> None:
    monkeypatch.setenv("SWITCHBOARD_ADMIN_TOKEN", _TOKEN)
    payload = _payload(tmp_path)
    payload[field] = value

    with pytest.raises(ValueError):
        WorkerConfig.from_mapping(payload)


def test_worker_config_rejects_unsupported_concurrency(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("SWITCHBOARD_ADMIN_TOKEN", _TOKEN)
    payload = _payload(tmp_path)
    payload["max_concurrency"] = 2

    with pytest.raises(ValueError, match="max_concurrency"):
        WorkerConfig.from_mapping(payload)


@pytest.mark.parametrize("repository", ["./repo", "Nobodyworld/..", "../repo"])
def test_assigned_work_order_rejects_repository_dot_segments(repository: str) -> None:
    payload = {
        "id": 1,
        "repository_full_name": repository,
        "commit_sha": "a" * 40,
        "manifest_name": "worker-smoke",
        "manifest_version": "1",
        "manifest_digest": "b" * 64,
        "timeout_seconds": 60,
        "network_policy": "worker_restricted",
        "repository_write_allowed": False,
        "required_capabilities": {},
    }

    with pytest.raises(ValueError, match="work-order identity"):
        AssignedWorkOrder.from_payload(payload)


@pytest.mark.parametrize("payload", [[], {"run": []}, {"run": {"id": "1"}}])
def test_malformed_checkout_roots_raise_validation_errors(payload: object) -> None:
    with pytest.raises(ValueError):
        Checkout.from_payload(payload)  # type: ignore[arg-type]
