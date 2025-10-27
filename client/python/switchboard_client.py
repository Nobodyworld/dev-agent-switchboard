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
        admin_token: str | None = None,
    ) -> None:
        """Initialize a :class:`SwitchboardClient`.

        Parameters
        ----------
        base_url:
            Root URL of the Switchboard deployment.
        agent_id:
            Identifier used when interacting with the API.
        session:
            Optional :class:`requests.Session` instance reused for requests.
        timeout:
            Default timeout, in seconds, applied to every request made by the
            client.
        operation_timeouts:
            Optional mapping of operation names to timeout overrides. Supported
            keys are public method names such as ``"put_file"``.
        auto_register:
            When ``True`` the client registers immediately upon creation.
        max_retries:
            Maximum number of retries for transient failures. Set to ``0`` to
            disable retry behaviour.
        retry_backoff:
            Base number of seconds used for exponential backoff between retry
            attempts.
        admin_token:
            Optional token used for administrative endpoints such as
            maintenance mode toggles. When provided the token is attached to
            requests that explicitly opt-in to admin authentication.

        Notes
        -----
        The provided session is reused for all requests. When no session is
        supplied a fresh :class:`requests.Session` is created. The timeout is
        stored as shared state so each API method uses consistent request
        settings.
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
        self.last_checkout_message: str | None = None
        self._max_retries = max(0, int(max_retries))
        self._retry_backoff = max(0.0, float(retry_backoff))
        self._admin_token = admin_token

        if auto_register:
            self.register()

    @property
    def session(self) -> Session:
        """Return the underlying :class:`requests.Session`.

        Returns
        -------
        Session
            Persistent HTTP session leveraged for API calls.
        """

        return self._session

    @property
    def timeout(self) -> float:
        """Return the request timeout applied to outbound calls.

        Returns
        -------
        float
            Timeout in seconds applied when no per-operation override exists.
        """

        return self._timeout

    def close(self) -> None:
        """Close the underlying :class:`requests.Session`.

        Returns
        -------
        None
            This method performs side effects only.
        """

        self._session.close()

    def set_admin_token(self, token: str | None) -> None:
        """Set or clear the admin token used for privileged endpoints."""

        self._admin_token = token

    def __enter__(self) -> SwitchboardClient:
        """Support ``with`` statements for deterministic cleanup.

        Returns
        -------
        SwitchboardClient
            The instance itself to enable context-manager usage.
        """

        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        """Ensure the underlying session is closed when leaving a context.

        Parameters
        ----------
        exc_type:
            Exception type raised inside the context, if any.
        exc:
            Exception instance raised inside the context, if any.
        tb:
            Traceback associated with ``exc`` when present.
        """

        self.close()

    def _request(self, method: str, path: str, **kwargs: Any) -> Response:
        """Perform an HTTP request using shared session and timeout settings.

        Parameters
        ----------
        method:
            HTTP method to invoke (``"GET"``, ``"POST"``, etc.).
        path:
            API path relative to :attr:`base`.
        **kwargs:
            Additional arguments forwarded to :meth:`requests.Session.request`.

        Returns
        -------
        Response
            HTTP response object with status validation already applied.
        """

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
        """Sleep based on the configured retry backoff.

        Parameters
        ----------
        attempt:
            Zero-based retry attempt counter.

        Returns
        -------
        bool
            ``True`` when another retry should proceed, ``False`` otherwise.
        """

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
        """Return ``True`` when another retry attempt should be attempted.

        Parameters
        ----------
        method:
            HTTP method submitted for the request.
        status:
            HTTP status code received from the server, when available.
        attempt:
            Zero-based retry attempt counter.

        Returns
        -------
        bool
            ``True`` if another retry should be attempted; ``False`` otherwise.
        """

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
        """Register this agent with Switchboard using the configured session.

        Returns
        -------
        dict[str, Any]
            JSON payload returned by the registration endpoint.
        """

        response = self._request(
            "post", "/api/agents", json={"agent_name": self.agent_id}
        )
        payload = cast(dict[str, Any], response.json())
        return payload

    def get_settings(self) -> dict[str, Any]:
        """Return the current server configuration settings.

        Returns
        -------
        dict[str, Any]
            JSON payload describing rate limit and lease settings.
        """

        timeout = self._operation_timeouts.get("get_settings", self._timeout)
        response = self._request("get", "/api/settings", timeout=timeout)
        payload = cast(dict[str, Any], response.json())
        return payload

    def get_configuration(self) -> dict[str, Any]:
        """Return a detailed configuration snapshot for the deployment."""

        timeout = self._operation_timeouts.get(
            "get_configuration", self._timeout
        )
        response = self._request(
            "get", "/api/configuration", timeout=timeout
        )
        return cast(dict[str, Any], response.json())

    def get_system_state(self) -> dict[str, Any]:
        """Return the server's global maintenance state."""

        response = self._request("get", "/api/system-state")
        return cast(dict[str, Any], response.json())

    def get_task_analytics(self) -> dict[str, Any]:
        """Return aggregated analytics about task flow and dependencies."""

        response = self._request("get", "/api/tasks/analytics")
        return cast(dict[str, Any], response.json())

    def set_system_state(
        self,
        maintenance_mode: bool,
        *,
        message: str | None = None,
        expected_version: int | None = None,
        admin_token: str | None = None,
    ) -> dict[str, Any]:
        """Update the server's maintenance state via the admin endpoint."""

        payload: dict[str, Any] = {
            "maintenance_mode": bool(maintenance_mode),
            "message": message,
        }
        if expected_version is not None:
            payload["expected_version"] = expected_version

        token = admin_token if admin_token is not None else self._admin_token
        headers: dict[str, str] = {"Content-Type": "application/json"}
        if token:
            headers["Authorization"] = f"Bearer {token}"

        response = self._request(
            "put",
            "/api/system-state",
            json=payload,
            headers=headers,
        )
        return cast(dict[str, Any], response.json())

    def checkout(self) -> dict[str, Any] | None:
        """Checkout the next task for this agent.

        Returns
        -------
        dict[str, Any] | None
            Task dictionary when a checkout succeeds, otherwise ``None``.

        Notes
        -----
        The server may include a ``reason`` when no task is returned. The value
        is mirrored to :attr:`last_checkout_reason` for diagnostics.
        """

        response = self._request(
            "post",
            "/api/tasks/checkout",
            params={"agent_id": self.agent_id},
        )
        data = cast(dict[str, Any], response.json())
        self.last_checkout_reason = data.get("reason")
        self.last_checkout_message = data.get("message")
        task_data = data.get("task")
        return cast(dict[str, Any] | None, task_data)

    def heartbeat(self, task_id: int) -> bool:
        """Send a heartbeat for the given task and return the server status.

        Parameters
        ----------
        task_id:
            Identifier of the task whose lease should be extended.

        Returns
        -------
        bool
            ``True`` when the heartbeat succeeds, ``False`` otherwise.
        """

        response = self._request(
            "post",
            f"/api/tasks/{task_id}/heartbeat",
            params={"agent_id": self.agent_id},
        )
        payload = cast(dict[str, Any], response.json())
        return bool(payload.get("ok", False))

    def complete(self, task_id: int, notes: str = "") -> bool:
        """Mark the task as complete and return the server acknowledgement.

        Parameters
        ----------
        task_id:
            Identifier of the task being completed.
        notes:
            Optional completion notes to persist.

        Returns
        -------
        bool
            ``True`` when the completion succeeds, ``False`` otherwise.
        """

        response = self._request(
            "post",
            f"/api/tasks/{task_id}/complete",
            params={"agent_id": self.agent_id},
            json={"notes": notes},
        )
        payload = cast(dict[str, Any], response.json())
        return bool(payload.get("ok", False))

    def abandon(self, task_id: int) -> bool:
        """Abandon the task and return the server acknowledgement.

        Parameters
        ----------
        task_id:
            Identifier of the task being abandoned.

        Returns
        -------
        bool
            ``True`` when the abandon succeeds, ``False`` otherwise.
        """

        response = self._request(
            "post",
            f"/api/tasks/{task_id}/abandon",
            params={"agent_id": self.agent_id},
        )
        payload = cast(dict[str, Any], response.json())
        return bool(payload.get("ok", False))

    def put_file(self, path: str, content: bytes) -> str:
        """Upload ``content`` to ``path`` and return the published file URL.

        Parameters
        ----------
        path:
            Repository-relative path to publish.
        content:
            Raw bytes that should be written to storage.

        Returns
        -------
        str
            Absolute URL where the uploaded file can be retrieved.

        Raises
        ------
        ValueError
            Raised when the upload response omits a URL.
        """

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
        """Return a list of tasks, optionally filtered by ``status``.

        Parameters
        ----------
        status:
            Optional status filter (``"pending"``, ``"in_progress"``, etc.).

        Returns
        -------
        list[dict[str, Any]]
            Serialized task dictionaries.
        """

        params = {"status": status} if status else None
        response = self._request("get", "/api/tasks", params=params)
        payload = cast(list[dict[str, Any]], response.json())
        return payload
