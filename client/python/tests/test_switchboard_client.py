"""Unit tests for the Switchboard Python client."""

from __future__ import annotations

from unittest.mock import Mock, patch

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


def test_put_file_raises_when_url_missing():
    session = Mock(spec=requests.Session)
    response = _successful_response({"ok": True})
    session.request.return_value = response

    client = SwitchboardClient(
        "http://example.com", "agent-007", session=session, auto_register=False
    )

    with pytest.raises(ValueError):
        client.put_file("foo", b"payload")

    session.request.assert_called_once_with(
        "put",
        "http://example.com/api/files/foo",
        data=b"payload",
        timeout=DEFAULT_REQUEST_TIMEOUT,
    )


def test_register_returns_json_payload():
    session = Mock(spec=requests.Session)
    response = _successful_response({"ok": True, "agent_id": "agent-007"})
    session.request.return_value = response

    client = SwitchboardClient(
        "http://example.com/", "agent-007", session=session, auto_register=False
    )

    payload = client.register()

    assert payload == {"ok": True, "agent_id": "agent-007"}
    session.request.assert_called_once_with(
        "post",
        "http://example.com/api/agents",
        json={"agent_name": "agent-007"},
        timeout=DEFAULT_REQUEST_TIMEOUT,
    )


def test_auto_register_triggers_registration_by_default():
    session = Mock(spec=requests.Session)
    with patch.object(SwitchboardClient, "register", autospec=True) as register:
        client = SwitchboardClient("http://example.com", "agent-99", session=session)

    register.assert_called_once_with(client)


def test_checkout_records_reason_when_task_missing():
    session = Mock(spec=requests.Session)
    response = _successful_response({"task": None, "reason": "no_available"})
    session.request.return_value = response

    client = SwitchboardClient(
        "http://example.com", "agent-007", session=session, auto_register=False
    )

    assert client.checkout() is None
    assert client.last_checkout_reason == "no_available"


def test_heartbeat_returns_boolean_status():
    session = Mock(spec=requests.Session)
    response = _successful_response({"ok": True})
    session.request.return_value = response

    client = SwitchboardClient(
        "http://example.com", "agent-007", session=session, auto_register=False
    )

    assert client.heartbeat(42) is True
    session.request.assert_called_once_with(
        "post",
        "http://example.com/api/tasks/42/heartbeat",
        params={"agent_id": "agent-007"},
        timeout=DEFAULT_REQUEST_TIMEOUT,
    )


def test_complete_returns_boolean_status():
    session = Mock(spec=requests.Session)
    response = _successful_response({"ok": False})
    session.request.return_value = response

    client = SwitchboardClient(
        "http://example.com", "agent-007", session=session, auto_register=False
    )

    assert client.complete(42, notes="done") is False
    session.request.assert_called_once_with(
        "post",
        "http://example.com/api/tasks/42/complete",
        params={"agent_id": "agent-007"},
        json={"notes": "done"},
        timeout=DEFAULT_REQUEST_TIMEOUT,
    )


def test_abandon_returns_boolean_status():
    session = Mock(spec=requests.Session)
    response = _successful_response({"ok": True})
    session.request.return_value = response

    client = SwitchboardClient(
        "http://example.com", "agent-007", session=session, auto_register=False
    )

    assert client.abandon(55) is True
    session.request.assert_called_once_with(
        "post",
        "http://example.com/api/tasks/55/abandon",
        params={"agent_id": "agent-007"},
        timeout=DEFAULT_REQUEST_TIMEOUT,
    )


def test_list_tasks_without_status_excludes_params():
    session = Mock(spec=requests.Session)
    response = _successful_response([{"id": 1}])
    session.request.return_value = response

    client = SwitchboardClient(
        "http://example.com", "agent-007", session=session, auto_register=False
    )

    tasks = client.list_tasks()

    assert tasks == [{"id": 1}]
    session.request.assert_called_once_with(
        "get",
        "http://example.com/api/tasks",
        params=None,
        timeout=DEFAULT_REQUEST_TIMEOUT,
    )


def test_list_tasks_with_status_passes_filter():
    session = Mock(spec=requests.Session)
    response = _successful_response([{"id": 2}])
    session.request.return_value = response

    client = SwitchboardClient(
        "http://example.com", "agent-007", session=session, auto_register=False
    )

    tasks = client.list_tasks(status="completed")

    assert tasks == [{"id": 2}]
    session.request.assert_called_once_with(
        "get",
        "http://example.com/api/tasks",
        params={"status": "completed"},
        timeout=DEFAULT_REQUEST_TIMEOUT,
    )
