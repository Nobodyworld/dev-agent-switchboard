import json
from typing import Any

import pytest
from requests import exceptions as req_exc
from switchboard_client import SwitchboardClient


class DummyResponse:
    def __init__(
        self,
        *,
        status_code: int = 200,
        payload: Any = None,
        url: str = "http://example/api",
    ) -> None:
        self.status_code = status_code
        self.url = url
        self._payload = payload if payload is not None else {}

    def json(self) -> Any:
        return json.loads(json.dumps(self._payload))

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise req_exc.HTTPError(f"status code {self.status_code}")


class RecordingSession:
    def __init__(self, response: DummyResponse | None = None) -> None:
        self.response = response or DummyResponse(payload={"ok": True})
        self.calls: list[tuple[str, str, dict[str, Any]]] = []

    def request(self, method: str, url: str, **kwargs: Any) -> DummyResponse:
        self.calls.append((method, url, kwargs))
        return self.response


class FlakySession:
    def __init__(self, succeed_after: int, payload: Any) -> None:
        self.succeed_after = succeed_after
        self.calls = 0
        self.payload = payload

    def request(self, _method: str, url: str, **_kwargs: Any) -> DummyResponse:
        self.calls += 1
        if self.calls <= self.succeed_after:
            raise req_exc.ConnectionError("temporary failure")
        return DummyResponse(payload=self.payload, url=url)


class FailingSession:
    def __init__(self) -> None:
        self.calls = 0

    def request(self, _method: str, _url: str, **_kwargs: Any) -> DummyResponse:
        self.calls += 1
        raise req_exc.Timeout("timeout")


def test_put_file_uses_custom_timeout() -> None:
    session = RecordingSession(response=DummyResponse(payload={"url": "http://example/live/foo"}))
    client = SwitchboardClient(
        "http://example",
        "agent",
        session=session,
        auto_register=False,
        operation_timeouts={"put_file": 42.0},
    )

    client.put_file("foo", b"payload")

    assert session.calls[0][2]["timeout"] == 42.0


def test_request_retries_transient_errors() -> None:
    session = FlakySession(succeed_after=2, payload=[])
    client = SwitchboardClient(
        "http://example",
        "agent",
        session=session,  # type: ignore[arg-type]
        auto_register=False,
        retry_backoff=0.0,
    )

    client.list_tasks()

    assert session.calls == 3


def test_request_raises_after_exhausting_retries() -> None:
    session = FailingSession()
    client = SwitchboardClient(
        "http://example",
        "agent",
        session=session,  # type: ignore[arg-type]
        auto_register=False,
        max_retries=2,
        retry_backoff=0.0,
    )

    with pytest.raises(req_exc.Timeout):
        client.checkout()

    assert session.calls == 3
