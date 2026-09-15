# ruff: noqa: S105 - explicit synthetic test credentials
"""Narrow client surface, no retries, process-private configuration and leakage."""

from __future__ import annotations

from unittest.mock import Mock

import pytest
import requests

from client.python.execution_operator.models import (
    OperatorLifecycleFailure,
    OperatorLifecycleReport,
)
from client.python.execution_worker.client import (
    ExecutionCredentialRejectedError,
    WorkerExecutionClient,
)
from client.python.execution_worker.config import WorkerConfig
from client.python.execution_worker.runner import _redact
from client.python.tests.test_execution_worker_config_models import _payload
from client.python.tests.test_execution_worker_foundations import _config, _response


def test_worker_client_has_only_reviewed_methods():
    names = {name for name in dir(WorkerExecutionClient) if not name.startswith("_")}
    assert names == {
        "close",
        "register_worker",
        "heartbeat_worker",
        "checkout",
        "get_manifest",
        "get_work_order",
        "get_run",
        "heartbeat_run",
        "resolve_reuse_candidate",
        "complete_run",
    }


@pytest.mark.parametrize("status", [401, 403])
def test_credential_loss_latches_without_retry_or_completion(status):
    session = Mock(spec=requests.Session)
    session.request.return_value = _response({}, status_code=status)
    client = WorkerExecutionClient(
        "http://localhost", "worker-a", "synthetic-worker", session=session
    )
    for operation in [
        client.checkout,
        client.checkout,
        lambda: client.complete_run(1, status="succeeded"),
    ]:
        with pytest.raises(ExecutionCredentialRejectedError) as error:
            operation()
        assert "synthetic-worker" not in str(error.value)
    session.request.assert_called_once()


def test_manual_configuration_requires_worker_secret_and_rejects_admin(
    tmp_path, monkeypatch
):
    monkeypatch.delenv("SWITCHBOARD_ADMIN_TOKEN", raising=False)
    monkeypatch.delenv("SWITCHBOARD_WORKER_TOKEN", raising=False)
    with pytest.raises(ValueError, match="worker_token"):
        WorkerConfig.from_mapping(_payload(tmp_path))
    monkeypatch.setenv("SWITCHBOARD_WORKER_TOKEN", "synthetic-worker-value")
    config = WorkerConfig.from_mapping(_payload(tmp_path))
    assert config.worker_token == "synthetic-worker-value"
    assert not hasattr(config, "admin_token")
    assert config.worker_token not in repr(config)
    for key in ("worker_token", "admin_token", "secret"):
        with pytest.raises(ValueError, match="credentials"):
            WorkerConfig.from_mapping({**_payload(tmp_path), key: "synthetic-value"})
    monkeypatch.setenv("SWITCHBOARD_ADMIN_TOKEN", "synthetic-admin")
    with pytest.raises(ValueError, match="administrator credential"):
        WorkerConfig.from_mapping(_payload(tmp_path))


def test_scoped_credential_shapes_are_redacted_and_reports_reject_them(tmp_path):
    token = "swb_w1." + "a" * 32 + "." + "b" * 64
    config = _config(tmp_path)
    assert token not in _redact(token, config)
    assert config.worker_token not in _redact(config.worker_token, config)
    report = OperatorLifecycleReport(reason=token)
    with pytest.raises(OperatorLifecycleFailure, match="report_text_policy"):
        report.as_dict()
