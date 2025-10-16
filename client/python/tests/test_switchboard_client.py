"""Unit tests for the Switchboard Python client."""

from __future__ import annotations

from unittest.mock import Mock

import pytest

try:
    import requests
except ImportError:  # pragma: no cover - handled by skip
    pytest.skip("requests is required for client tests", allow_module_level=True)  # type: ignore[arg-type]

from switchboard_client import DEFAULT_REQUEST_TIMEOUT, SwitchboardClient


def _successful_response(json_payload):
    response = Mock(spec=requests.Response)
    response.json.return_value = json_payload
    response.raise_for_status.return_value = None
    return response


def test_checkout_success_uses_shared_session_and_timeout():
    session = Mock(spec=requests.Session)
    response = _successful_response({"task": {"id": 1}})
    session.request.return_value = response

    client = SwitchboardClient(
        "http://example.com",
        "agent-007",
        session=session,
        timeout=5,
        auto_register=False,
    )

    task = client.checkout()

    assert task == {"id": 1}
    assert client.last_checkout_reason is None
    session.request.assert_called_once_with(
        "post",
        "http://example.com/api/tasks/checkout",
        params={"agent_id": "agent-007"},
        timeout=5,
    )
    response.raise_for_status.assert_called_once()


def test_checkout_failure_propagates_http_error():
    session = Mock(spec=requests.Session)
    response = Mock(spec=requests.Response)
    response.raise_for_status.side_effect = requests.HTTPError("boom")
    session.request.return_value = response

    client = SwitchboardClient(
        "http://example.com",
        "agent-007",
        session=session,
        auto_register=False,
    )

    with pytest.raises(requests.HTTPError):
        client.checkout()

    session.request.assert_called_once_with(
        "post",
        "http://example.com/api/tasks/checkout",
        params={"agent_id": "agent-007"},
        timeout=DEFAULT_REQUEST_TIMEOUT,
    )
    response.json.assert_not_called()


def test_put_file_returns_url_and_uses_shared_timeout():
    session = Mock(spec=requests.Session)
    response = _successful_response({"url": "http://example.com/live/foo"})
    session.request.return_value = response

    client = SwitchboardClient(
        "http://example.com",
        "agent-007",
        session=session,
        timeout=3,
        auto_register=False,
    )

    url = client.put_file("foo", b"payload")

    assert url == "http://example.com/live/foo"
    session.request.assert_called_once_with(
        "put",
        "http://example.com/api/files/foo",
        data=b"payload",
        timeout=3,
    )
    response.raise_for_status.assert_called_once()
