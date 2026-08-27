"""Unit coverage for safe pull-worker client foundations."""

from __future__ import annotations

import json
from http import HTTPStatus
from pathlib import Path
from unittest.mock import Mock

import pytest
import requests

from client.python.execution_worker import (
    ExecutionClient,
    ExecutionHttpError,
    ExecutionOwnershipLostError,
    WorkerConfig,
    discover_worker_registration,
)

_TEST_TOKEN = "worker-test-token"  # noqa: S105 - non-secret test fixture
_TWO_REQUESTS = 2
_MAX_SAFE_VALIDATION_ERRORS = 8
_MAX_SAFE_VALIDATION_MESSAGE_LENGTH = 256


def _response(payload: object, *, status_code: int = 200) -> Mock:
    response = Mock(spec=requests.Response)
    response.status_code = status_code
    response.json.return_value = payload
    response.content = json.dumps(payload).encode("utf-8")
    response.raise_for_status.return_value = None
    return response


def _config(tmp_path: Path) -> WorkerConfig:
    return WorkerConfig(
        base_url="http://localhost:8000",
        worker_id="worker-1",
        display_name="Worker 1",
        admin_token=_TEST_TOKEN,
        worker_root=tmp_path / "worker-root",
        evidence_root=tmp_path / "evidence-root",
        repositories={
            "Nobodyworld/dev-agent-switchboard": tmp_path / "canonical-repository"
        },
    )


def test_execution_client_requires_credentials() -> None:
    with pytest.raises(ValueError, match="admin_token"):
        ExecutionClient("http://example.com", "worker-1", "")
    with pytest.raises(ValueError, match="worker_id"):
        ExecutionClient("http://example.com", "", _TEST_TOKEN)


def test_execution_client_authenticates_and_uses_expected_manifest_endpoint() -> None:
    session = Mock(spec=requests.Session)
    session.request.return_value = _response([{"name": "worker-smoke"}])
    client = ExecutionClient(
        "http://example.com/",
        "worker-1",
        _TEST_TOKEN,
        session=session,
        timeout=3,
    )

    assert client.list_manifests() == [{"name": "worker-smoke"}]
    session.request.assert_called_once_with(
        "get",
        "http://example.com/api/execution/manifests",
        headers={
            "Authorization": f"Bearer {_TEST_TOKEN}",
            "Accept": "application/json",
        },
        timeout=3.0,
    )


def test_execution_client_registration_cannot_impersonate_another_worker() -> None:
    client = ExecutionClient("http://example.com", "worker-1", _TEST_TOKEN)

    with pytest.raises(ValueError, match="must match"):
        client.register_worker({"worker_id": "worker-2"})


def test_execution_client_checkout_and_completion_payloads_are_bounded() -> None:
    session = Mock(spec=requests.Session)
    session.request.side_effect = [
        _response({"run": None, "reason": "no_available"}),
        _response({"id": 9, "status": "failed"}),
    ]
    client = ExecutionClient(
        "http://example.com", "worker-1", _TEST_TOKEN, session=session
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
    assert session.request.call_args_list[0].kwargs["json"] == {"worker_id": "worker-1"}
    assert session.request.call_args_list[1].kwargs["json"] == {
        "worker_id": "worker-1",
        "status": "failed",
        "result_summary": "tests failed",
        "terminal_reason": "required_step_failed",
        "cleanup_status": "succeeded",
        "artifact_metadata": [],
        "evidence_metadata": {"failing_step": "tests"},
    }


@pytest.mark.parametrize(
    "status_code",
    [HTTPStatus.NOT_FOUND, HTTPStatus.CONFLICT],
)
def test_execution_client_preserves_ownership_loss_for_completion(
    status_code: HTTPStatus,
) -> None:
    session = Mock(spec=requests.Session)
    session.request.return_value = _response({}, status_code=status_code)
    client = ExecutionClient(
        "http://example.com", "worker-1", _TEST_TOKEN, session=session
    )

    with pytest.raises(ExecutionOwnershipLostError) as captured:
        client.complete_run(7, status="succeeded", result_summary="safe")

    assert captured.value.status_code == status_code
    session.request.assert_called_once()


def test_execution_client_surfaces_bounded_safe_validation_details() -> None:
    session = Mock(spec=requests.Session)
    response = _response(
        {
            "detail": [
                {
                    "type": "value_error",
                    "loc": ["body", "result_summary"],
                    "msg": "Value error, text must not contain an absolute local path",
                    "input": "private-token-value",
                }
            ]
        },
        status_code=HTTPStatus.UNPROCESSABLE_ENTITY,
    )
    session.request.return_value = response
    client = ExecutionClient(
        "http://example.com", "worker-1", _TEST_TOKEN, session=session
    )

    with pytest.raises(ExecutionHttpError) as captured:
        client.complete_run(9, status="succeeded", result_summary="safe")

    error = captured.value
    assert error.status_code == HTTPStatus.UNPROCESSABLE_ENTITY
    assert error.reason == "execution_validation_error"
    assert len(error.validation_errors) == 1
    assert error.validation_errors[0].location == ("body", "result_summary")
    assert error.validation_errors[0].error_type == "value_error"
    assert "absolute local path" in error.validation_errors[0].message
    assert "private-token-value" not in str(error)
    assert _TEST_TOKEN not in str(error)
    session.request.assert_called_once()


@pytest.mark.parametrize(
    "payload",
    [
        {"detail": "not-a-list"},
        {"unexpected": "shape"},
    ],
)
def test_execution_client_uses_stable_reason_for_unknown_error_json(
    payload: object,
) -> None:
    session = Mock(spec=requests.Session)
    session.request.return_value = _response(
        payload, status_code=HTTPStatus.UNPROCESSABLE_ENTITY
    )
    client = ExecutionClient(
        "http://example.com", "worker-1", _TEST_TOKEN, session=session
    )

    with pytest.raises(ExecutionHttpError) as captured:
        client.complete_run(9, status="succeeded")

    assert captured.value.reason == "execution_http_error"
    assert captured.value.validation_errors == ()
    session.request.assert_called_once()


def test_execution_client_excludes_oversized_and_sensitive_error_content() -> None:
    session = Mock(spec=requests.Session)
    oversized = _response({}, status_code=HTTPStatus.UNPROCESSABLE_ENTITY)
    oversized.content = b"x" * (64 * 1024 + 1)
    sensitive = _response(
        {
            "detail": [
                {
                    "type": "value_error",
                    "loc": ["body", r"C:\private\field"],
                    "msg": "Bearer private-token-value at /private/path",
                    "input": "private-token-value",
                }
            ]
        },
        status_code=HTTPStatus.UNPROCESSABLE_ENTITY,
    )
    session.request.side_effect = [oversized, sensitive]
    client = ExecutionClient(
        "http://example.com", "worker-1", _TEST_TOKEN, session=session
    )

    with pytest.raises(ExecutionHttpError) as oversized_error:
        client.complete_run(9, status="succeeded")
    with pytest.raises(ExecutionHttpError) as sensitive_error:
        client.complete_run(10, status="succeeded")

    assert oversized_error.value.validation_errors == ()
    assert sensitive_error.value.validation_errors[0].location == ("body", "[REDACTED]")
    assert sensitive_error.value.validation_errors[0].message == "[REDACTED]"
    assert "private-token-value" not in str(sensitive_error.value)
    assert r"C:\private" not in str(sensitive_error.value)
    assert session.request.call_count == _TWO_REQUESTS


def test_execution_client_drops_raw_html_and_local_database_error_content(
    caplog: pytest.LogCaptureFixture,
) -> None:
    unsafe_token = "raw-private-token-value"  # noqa: S105 - synthetic leak probe
    session = Mock(spec=requests.Session)
    html = Mock(spec=requests.Response)
    html.status_code = HTTPStatus.INTERNAL_SERVER_ERROR
    html.content = (
        f"<html>{unsafe_token} sqlite:///C:/private/result.db</html>"
    ).encode()
    sqlite_validation = _response(
        {
            "detail": [
                {
                    "type": "value_error",
                    "loc": ["body", "result_summary"],
                    "msg": "sqlite+aiosqlite:///tmp/private-result.db",
                    "input": unsafe_token,
                    "ctx": {"error": unsafe_token},
                }
            ]
        },
        status_code=HTTPStatus.UNPROCESSABLE_ENTITY,
    )
    session.request.side_effect = [html, sqlite_validation]
    client = ExecutionClient(
        "http://example.com", "worker-1", _TEST_TOKEN, session=session
    )

    with pytest.raises(ExecutionHttpError) as html_error:
        client.complete_run(9, status="failed", result_summary="safe")
    with pytest.raises(ExecutionHttpError) as sqlite_error:
        client.complete_run(10, status="failed", result_summary="safe")

    assert html_error.value.reason == "execution_http_error"
    assert html_error.value.validation_errors == ()
    assert sqlite_error.value.validation_errors[0].message == "[REDACTED]"
    retained_state = repr(
        (
            html_error.value.args,
            html_error.value.reason,
            html_error.value.validation_errors,
            sqlite_error.value.args,
            sqlite_error.value.reason,
            sqlite_error.value.validation_errors,
        )
    )
    for unsafe in (
        unsafe_token,
        _TEST_TOKEN,
        "private-result.db",
        "sqlite:///",
        "sqlite+aiosqlite:///",
        "<html>",
    ):
        assert unsafe not in retained_state
        assert unsafe not in caplog.text
    assert not hasattr(html_error.value, "response")
    assert not hasattr(sqlite_error.value, "request")
    assert session.request.call_count == _TWO_REQUESTS


def test_execution_client_bounds_validation_detail_count_and_message() -> None:
    session = Mock(spec=requests.Session)
    response = _response(
        {
            "detail": [
                {
                    "type": "value_error",
                    "loc": ["body", "field", index],
                    "msg": "x" * 1000,
                }
                for index in range(_MAX_SAFE_VALIDATION_ERRORS + 2)
            ]
        },
        status_code=HTTPStatus.UNPROCESSABLE_ENTITY,
    )
    session.request.return_value = response
    client = ExecutionClient(
        "http://example.com", "worker-1", _TEST_TOKEN, session=session
    )

    with pytest.raises(ExecutionHttpError) as captured:
        client.complete_run(9, status="succeeded")

    assert len(captured.value.validation_errors) == _MAX_SAFE_VALIDATION_ERRORS
    assert all(
        len(item.message) == _MAX_SAFE_VALIDATION_MESSAGE_LENGTH
        for item in captured.value.validation_errors
    )
    session.request.assert_called_once()


def test_worker_config_uses_only_registered_absolute_paths(tmp_path: Path) -> None:
    config = _config(tmp_path)

    assert config.repository_path("Nobodyworld/dev-agent-switchboard") == (
        tmp_path / "canonical-repository"
    )
    assert _TEST_TOKEN not in repr(config)
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
            admin_token=_TEST_TOKEN,
            worker_root=Path("relative-root"),
            evidence_root=tmp_path / "evidence-root",
            repositories={"Nobodyworld/repo": tmp_path / "repo"},
        )

    with pytest.raises(ValueError, match="invalid repository"):
        WorkerConfig(
            base_url="http://localhost:8000",
            worker_id="worker-1",
            display_name="Worker 1",
            admin_token=_TEST_TOKEN,
            worker_root=tmp_path / "worker-root",
            evidence_root=tmp_path / "evidence-root",
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
