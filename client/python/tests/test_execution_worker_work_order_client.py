"""Coverage for retrieving the work-order identity behind an assigned run."""

from __future__ import annotations

from unittest.mock import Mock

import requests

from client.python.execution_worker import ExecutionClient
from client.python.tests.execution_worker_test_support import work_order_payload
from server.execution.registry import get_trusted_manifest

_TEST_TOKEN = "work-order-test-token"  # noqa: S105 - non-secret test fixture


def test_execution_client_retrieves_assigned_work_order_metadata() -> None:
    session = Mock(spec=requests.Session)
    response = Mock(spec=requests.Response)
    response.status_code = 200
    response.raise_for_status.return_value = None
    manifest = get_trusted_manifest("worker-smoke", "1")
    assert manifest is not None
    response.json.return_value = work_order_payload("a" * 40, manifest, id=17)
    session.request.return_value = response
    client = ExecutionClient(
        "http://example.com", "worker-1", _TEST_TOKEN, session=session
    )

    work_order = client.get_work_order(17)

    assert work_order["repository_full_name"] == "Nobodyworld/dev-agent-switchboard"
    assert work_order["commit_sha"] == "a" * 40
    assert work_order["manifest_name"] == "worker-smoke"
    assert work_order["repository_write_allowed"] is False
    session.request.assert_called_once_with(
        "get",
        "http://example.com/api/execution/work-orders/17",
        headers={
            "Authorization": f"Bearer {_TEST_TOKEN}",
            "Accept": "application/json",
        },
        timeout=10.0,
    )
