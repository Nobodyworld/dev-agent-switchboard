"""Client utilities for interacting with the Switchboard API."""

from __future__ import annotations

import time
from collections.abc import Mapping
from types import TracebackType
from typing import Any, cast

import requests
from requests import Response, Session

DEFAULT_REQUEST_TIMEOUT = 10.0
DEFAULT_PUT_FILE_TIMEOUT = 120.0
DEFAULT_MAX_RETRIES = 3
DEFAULT_RETRY_BACKOFF = 0.5

_RETRYABLE_METHODS = {"GET", "HEAD", "OPTIONS"}
RETRYABLE_STATUS_MIN = 500
RETRYABLE_STATUS_MAX = 600

__all__ = ["DEFAULT_REQUEST_TIMEOUT", "SwitchboardClient"]


class SwitchboardClient:
    """Thin wrapper around the Switchboard REST API."""

    def __init__(  # noqa: PLR0913 - constructor intentionally exposes tuning knobs
        self,
        base_url: str,
        agent_id: str,
        *,
        session: Session | None = None,
        timeout: float = DEFAULT_REQUEST_TIMEOUT,
        operation_timeouts: Mapping[str, float] | None = None,
        auto_register: bool = True,
        max_retries: int = DEFAULT_MAX_RETRIES,
        retry_backoff: float = DEFAULT_RETRY_BACKOFF,
    ) -> None:
        """Create a client.

        Args:
            base_url: Root URL of the Switchboard deployment.
            agent_id: Identifier used when interacting with the API.
            session: Optional ``requests.Session`` to reuse connections.
            timeout: Timeout applied to every request made by the client.
            operation_timeouts: Optional mapping of operation names to timeout
                overrides. The supported keys are the public method names such
                as ``"put_file"``.
            auto_register: When ``True`` the client registers immediately.
            max_retries: Maximum number of retries for transient failures. Set
                to ``0`` to disable retry behaviour.
            retry_backoff: Base seconds used for exponential backoff between
                retry attempts.

        The provided session is reused for all requests. When no session is
        supplied a fresh ``requests.Session`` is created. The timeout is stored
        as shared state so each API method uses consistent request settings.
        """

        self.base = base_url.rstrip("/")
        self.agent_id = agent_id
        self._session = session or Session()
        self._timeout = timeout
        self._operation_timeouts = {
            "put_file": DEFAULT_PUT_FILE_TIMEOUT,
        }
        if operation_timeouts:
            for key, value in operation_timeouts.items():
                self._operation_timeouts[key] = float(value)
        self.last_checkout_reason: str | None = None
        self._max_retries = max(0, int(max_retries))
        self._retry_backoff = max(0.0, float(retry_backoff))

        if auto_register:
            self.register()

    @property
    def session(self) -> Session:
        """Return the underlying :class:`requests.Session`."""

        return self._session

    @property
    def timeout(self) -> float:
        """Return the request timeout applied to outbound calls."""

        return self._timeout

    def close(self) -> None:
        """Close the underlying :class:`requests.Session`."""

        self._session.close()

    def __enter__(self) -> SwitchboardClient:
        """Support ``with`` statements for deterministic cleanup."""

        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        """Ensure the underlying session is closed when leaving a context."""

        self.close()

    def _request(self, method: str, path: str, **kwargs: Any) -> Response:
        """Helper that performs a request with shared timeout/session settings."""

        url = f"{self.base}{path}"
        timeout = kwargs.pop("timeout", None)
        if timeout is None:
            timeout = self._timeout
        kwargs["timeout"] = timeout

        attempt = 0
        last_error: Exception | None = None
        while True:
            try:
                response = self._session.request(method, url, **kwargs)
                response.raise_for_status()
                return response
            except requests.HTTPError as exc:
                status = exc.response.status_code if exc.response else None
                if not self._should_retry(method, status=status, attempt=attempt):
                    raise
                last_error = exc
            except requests.RequestException as exc:
                if not self._should_retry(method, attempt=attempt):
                    raise
                last_error = exc

            if not self._sleep_for_retry(attempt):
                if last_error is not None:
                    raise last_error
                raise RuntimeError("Retry aborted without error context")
            attempt += 1

    def _sleep_for_retry(self, attempt: int) -> bool:
        """Sleep based on the configured retry backoff."""

        if attempt >= self._max_retries:
            return False
        if self._retry_backoff <= 0:
            return True
        delay = self._retry_backoff * (2 ** attempt)
        time.sleep(delay)
        return True

    def _should_retry(
        self, method: str, *, status: int | None = None, attempt: int
    ) -> bool:
        """Return ``True`` when another retry attempt should be attempted."""

        if attempt >= self._max_retries:
            return False
        if status is not None and (
            status < RETRYABLE_STATUS_MIN or status >= RETRYABLE_STATUS_MAX
        ):
            return False
        if method.upper() not in _RETRYABLE_METHODS and status is None:
            # Non-idempotent requests retry only on network errors, not 5xx
            # responses, to avoid double-submitting writes.
            return True
        return True

    def register(self) -> dict[str, Any]:
        """Register this agent with Switchboard using the configured session."""

        response = self._request(
            "post", "/api/agents", json={"agent_name": self.agent_id}
        )
        payload = cast(dict[str, Any], response.json())
        return payload

    def get_settings(self) -> dict[str, Any]:
        """Return the current server configuration settings."""

        timeout = self._operation_timeouts.get("get_settings", self._timeout)
        response = self._request("get", "/api/settings", timeout=timeout)
        payload = cast(dict[str, Any], response.json())
        return payload

    def checkout(self) -> dict[str, Any] | None:
        """Checkout the next task for this agent.

        Returns the task dictionary if one is available, otherwise ``None``.
        The server may include a ``reason`` when no task is returned; this is
        exposed via :attr:`last_checkout_reason` to help with diagnostics.
        """

        response = self._request(
            "post",
            "/api/tasks/checkout",
            params={"agent_id": self.agent_id},
        )
        data = cast(dict[str, Any], response.json())
        self.last_checkout_reason = data.get("reason")
        task_data = data.get("task")
        return cast(dict[str, Any] | None, task_data)

    def heartbeat(self, task_id: int) -> bool:
        """Send a heartbeat for the given task and return the server status."""

        response = self._request(
            "post",
            f"/api/tasks/{task_id}/heartbeat",
            params={"agent_id": self.agent_id},
        )
        payload = cast(dict[str, Any], response.json())
        return bool(payload.get("ok", False))

    def complete(self, task_id: int, notes: str = "") -> bool:
        """Mark the task as complete and return the server acknowledgement."""

        response = self._request(
            "post",
            f"/api/tasks/{task_id}/complete",
            params={"agent_id": self.agent_id},
            json={"notes": notes},
        )
        payload = cast(dict[str, Any], response.json())
        return bool(payload.get("ok", False))

    def abandon(self, task_id: int) -> bool:
        """Abandon the task and return the server acknowledgement."""

        response = self._request(
            "post",
            f"/api/tasks/{task_id}/abandon",
            params={"agent_id": self.agent_id},
        )
        payload = cast(dict[str, Any], response.json())
        return bool(payload.get("ok", False))

    def put_file(self, path: str, content: bytes) -> str:
        """Upload ``content`` to ``path`` and return the published file URL."""

        timeout = self._operation_timeouts.get("put_file", self._timeout)
        response = self._request(
            "put", f"/api/files/{path}", data=content, timeout=timeout
        )
        payload = cast(dict[str, Any], response.json())
        url = payload.get("url")
        if not isinstance(url, str):
            raise ValueError("Upload response did not include a URL")
        return url

    def list_tasks(self, status: str | None = None) -> list[dict[str, Any]]:
        """Return a list of tasks, optionally filtered by ``status``."""

        params = {"status": status} if status else None
        response = self._request("get", "/api/tasks", params=params)
        payload = cast(list[dict[str, Any]], response.json())
        return payload
