"""Coverage for retrieving the work-order identity behind an assigned run."""

from __future__ import annotations

from unittest.mock import Mock

import requests

from client.python.execution_worker import ExecutionClient

_TEST_TOKEN = "work-order-test-token"  # noqa: S105 - non-secret test fixture


def test_execution_client_retrieves_assigned_work_order_metadata() -> None:
    session = Mock(spec=requests.Session)
    response = Mock(spec=requests.Response)
    response.status_code = 200
    response.raise_for_status.return_value = None
    response.json.return_value = {
        "id": 17,
        "repository_full_name": "Nobodyworld/dev-agent-switchboard",
        "commit_sha": "a" * 40,
        "manifest_name": "worker-smoke",
        "manifest_version": "1",
        "manifest_digest": "b" * 64,
        "repository_write_allowed": False,
    }
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
