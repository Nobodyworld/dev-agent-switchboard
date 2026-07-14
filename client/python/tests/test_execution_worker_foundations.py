"""Unit coverage for safe pull-worker client foundations."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import Mock

import pytest
import requests

from client.python.execution_worker import (
    ExecutionClient,
    ExecutionOwnershipLost,
    WorkerConfig,
    discover_worker_registration,
)


def _response(payload: object, *, status_code: int = 200) -> Mock:
    response = Mock(spec=requests.Response)
    response.status_code = status_code
    response.json.return_value = payload
    response.raise_for_status.return_value = None
    return response


def _config(tmp_path: Path) -> WorkerConfig:
    return WorkerConfig(
        base_url="http://localhost:8000",
        worker_id="worker-1",
        display_name="Worker 1",
        admin_token="secret-token",
        worker_root=tmp_path / "worker-root",
        repositories={
            "Nobodyworld/dev-agent-switchboard": tmp_path / "canonical-repository"
        },
    )


def test_execution_client_requires_credentials() -> None:
    with pytest.raises(ValueError, match="admin_token"):
        ExecutionClient("http://example.com", "worker-1", "")
    with pytest.raises(ValueError, match="worker_id"):
        ExecutionClient("http://example.com", "", "token")


def test_execution_client_authenticates_and_uses_expected_manifest_endpoint() -> None:
    session = Mock(spec=requests.Session)
    session.request.return_value = _response([{"name": "worker-smoke"}])
    client = ExecutionClient(
        "http://example.com/",
        "worker-1",
        "token-value",
        session=session,
        timeout=3,
    )

    assert client.list_manifests() == [{"name": "worker-smoke"}]
    session.request.assert_called_once_with(
        "get",
        "http://example.com/api/execution/manifests",
        headers={
            "Authorization": "Bearer token-value",
            "Accept": "application/json",
        },
        timeout=3.0,
    )


def test_execution_client_registration_cannot_impersonate_another_worker() -> None:
    client = ExecutionClient("http://example.com", "worker-1", "token")

    with pytest.raises(ValueError, match="must match"):
        client.register_worker({"worker_id": "worker-2"})


def test_execution_client_checkout_and_completion_payloads_are_bounded() -> None:
    session = Mock(spec=requests.Session)
    session.request.side_effect = [
        _response({"run": None, "reason": "no_available"}),
        _response({"id": 9, "status": "failed"}),
    ]
    client = ExecutionClient(
        "http://example.com", "worker-1", "token", session=session
    )

    assert client.checkout()["reason"] == "no_available"
    completed = client.complete_run(
        9,
        status="failed",
        result_summary="tests failed",
        terminal_reason="required_step_failed",
        cleanup_status="succeeded",
        evidence_metadata={"failing_step": "tests"},
    )

    assert completed["status"] == "failed"
    assert session.request.call_args_list[0].kwargs["json"] == {
        "worker_id": "worker-1"
    }
    assert session.request.call_args_list[1].kwargs["json"] == {
        "worker_id": "worker-1",
        "status": "failed",
        "result_summary": "tests failed",
        "terminal_reason": "required_step_failed",
        "cleanup_status": "succeeded",
        "artifact_metadata": [],
        "evidence_metadata": {"failing_step": "tests"},
    }


def test_execution_client_surfaces_heartbeat_ownership_loss() -> None:
    session = Mock(spec=requests.Session)
    session.request.return_value = _response({}, status_code=409)
    client = ExecutionClient(
        "http://example.com", "worker-1", "token", session=session
    )

    with pytest.raises(ExecutionOwnershipLost) as captured:
        client.heartbeat_run(7)

    assert captured.value.status_code == 409


def test_worker_config_uses_only_registered_absolute_paths(tmp_path: Path) -> None:
    config = _config(tmp_path)

    assert config.repository_path("Nobodyworld/dev-agent-switchboard") == (
        tmp_path / "canonical-repository"
    )
    assert "secret-token" not in repr(config)
    with pytest.raises(KeyError, match="not registered"):
        config.repository_path("untrusted/example")


def test_worker_config_rejects_relative_and_invalid_registry_entries(
    tmp_path: Path,
) -> None:
    with pytest.raises(ValueError, match="worker_root"):
        WorkerConfig(
            base_url="http://localhost:8000",
            worker_id="worker-1",
            display_name="Worker 1",
            admin_token="token",
            worker_root=Path("relative-root"),
            repositories={"Nobodyworld/repo": tmp_path / "repo"},
        )

    with pytest.raises(ValueError, match="invalid repository"):
        WorkerConfig(
            base_url="http://localhost:8000",
            worker_id="worker-1",
            display_name="Worker 1",
            admin_token="token",
            worker_root=tmp_path / "worker-root",
            repositories={"../escape": tmp_path / "repo"},
        )


def test_capability_discovery_is_bounded_and_read_only(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    available = {"git", "docker", "firefox"}
    monkeypatch.setattr(
        "client.python.execution_worker.capabilities.shutil.which",
        lambda name: f"/bin/{name}" if name in available else None,
    )
    monkeypatch.setattr(
        "client.python.execution_worker.capabilities.platform.system",
        lambda: "Linux",
    )
    monkeypatch.setattr(
        "client.python.execution_worker.capabilities.platform.machine",
        lambda: "x86_64",
    )
    monkeypatch.setattr(
        "client.python.execution_worker.capabilities.platform.python_version",
        lambda: "3.11.9",
    )

    registration = discover_worker_registration(_config(tmp_path))

    assert registration["operating_system"] == "linux"
    assert registration["architecture"] == "x86_64"
    assert registration["python_version"] == "3.11.9"
    assert registration["docker_available"] is True
    assert registration["browsers"] == ["firefox"]
    assert registration["capabilities"]["git_available"] is True
    assert registration["repository_write_capability"] is False
    assert registration["network_policy_capability"] == "worker_restricted"
