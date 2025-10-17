"""Client utilities for interacting with the Switchboard API."""

from __future__ import annotations

from typing import Any, Dict, List, Optional, cast

from requests import Response, Session


DEFAULT_REQUEST_TIMEOUT = 10.0

__all__ = ["DEFAULT_REQUEST_TIMEOUT", "SwitchboardClient"]


class SwitchboardClient:
    """Thin wrapper around the Switchboard REST API."""

    def __init__(
        self,
        base_url: str,
        agent_id: str,
        *,
        session: Optional[Session] = None,
        timeout: float = DEFAULT_REQUEST_TIMEOUT,
        auto_register: bool = True,
    ) -> None:
        """Create a client.

        Args:
            base_url: Root URL of the Switchboard deployment.
            agent_id: Identifier used when interacting with the API.
            session: Optional ``requests.Session`` to reuse connections.
            timeout: Timeout applied to every request made by the client.
            auto_register: When ``True`` the client registers immediately.

        The provided session is reused for all requests. When no session is
        supplied a fresh ``requests.Session`` is created. The timeout is stored
        as shared state so each API method uses consistent request settings.
        """

        self.base = base_url.rstrip("/")
        self.agent_id = agent_id
        self._session = session or Session()
        self._timeout = timeout
        self.last_checkout_reason: Optional[str] = None

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

    def __enter__(self) -> "SwitchboardClient":
        """Support ``with`` statements for deterministic cleanup."""

        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()

    def _request(self, method: str, path: str, **kwargs: Any) -> Response:
        """Helper that performs a request with shared timeout/session settings."""

        kwargs.setdefault("timeout", self._timeout)
        url = f"{self.base}{path}"
        response = self._session.request(method, url, **kwargs)
        response.raise_for_status()
        return response

    def register(self) -> Dict[str, Any]:
        """Register this agent with Switchboard using the configured session."""

        response = self._request(
            "post", "/api/agents", json={"agent_name": self.agent_id}
        )
        payload = cast(Dict[str, Any], response.json())
        return payload

    def checkout(self) -> Optional[Dict[str, Any]]:
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
        data = cast(Dict[str, Any], response.json())
        self.last_checkout_reason = data.get("reason")
        task_data = data.get("task")
        return cast(Optional[Dict[str, Any]], task_data)

    def heartbeat(self, task_id: int) -> bool:
        """Send a heartbeat for the given task and return the server status."""

        response = self._request(
            "post",
            f"/api/tasks/{task_id}/heartbeat",
            params={"agent_id": self.agent_id},
        )
        payload = cast(Dict[str, Any], response.json())
        return bool(payload.get("ok", False))

    def complete(self, task_id: int, notes: str = "") -> bool:
        """Mark the task as complete and return the server acknowledgement."""

        response = self._request(
            "post",
            f"/api/tasks/{task_id}/complete",
            params={"agent_id": self.agent_id},
            json={"notes": notes},
        )
        payload = cast(Dict[str, Any], response.json())
        return bool(payload.get("ok", False))

    def abandon(self, task_id: int) -> bool:
        """Abandon the task and return the server acknowledgement."""

        response = self._request(
            "post",
            f"/api/tasks/{task_id}/abandon",
            params={"agent_id": self.agent_id},
        )
        payload = cast(Dict[str, Any], response.json())
        return bool(payload.get("ok", False))

    def put_file(self, path: str, content: bytes) -> str:
        """Upload ``content`` to ``path`` and return the published file URL."""

        response = self._request("put", f"/api/files/{path}", data=content)
        payload = cast(Dict[str, Any], response.json())
        url = payload.get("url")
        if not isinstance(url, str):
            raise ValueError("Upload response did not include a URL")
        return url

    def list_tasks(self, status: Optional[str] = None) -> List[Dict[str, Any]]:
        """Return a list of tasks, optionally filtered by ``status``."""

        params = {"status": status} if status else None
        response = self._request("get", "/api/tasks", params=params)
        payload = cast(List[Dict[str, Any]], response.json())
        return payload
