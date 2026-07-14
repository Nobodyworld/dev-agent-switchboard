"""Authenticated HTTP client for the execution control-plane API."""

from __future__ import annotations

from collections.abc import Mapping
from types import TracebackType
from typing import Any, cast

from requests import Response, Session

DEFAULT_EXECUTION_TIMEOUT = 10.0
_OWNERSHIP_LOST_STATUSES = {404, 409}


class ExecutionClientError(RuntimeError):
    """Base error raised by the execution worker client."""


class ExecutionOwnershipLostError(ExecutionClientError):
    """Raised when the server no longer recognizes this worker as run owner."""

    def __init__(self, status_code: int) -> None:
        super().__init__(f"execution_run_ownership_lost:{status_code}")
        self.status_code = status_code


class ExecutionClient:
    """Small authenticated client dedicated to execution-plane endpoints."""

    def __init__(  # noqa: PLR0913 - transport construction exposes bounded tuning
        self,
        base_url: str,
        worker_id: str,
        admin_token: str,
        *,
        session: Session | None = None,
        timeout: float = DEFAULT_EXECUTION_TIMEOUT,
    ) -> None:
        if not admin_token.strip():
            raise ValueError("admin_token is required for Phase 1 execution endpoints")
        if not worker_id.strip():
            raise ValueError("worker_id must not be empty")

        self.base_url = base_url.rstrip("/")
        self.worker_id = worker_id
        self._admin_token = admin_token
        self._session = session or Session()
        self._timeout = float(timeout)

    def __enter__(self) -> ExecutionClient:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self.close()

    def close(self) -> None:
        """Close the underlying HTTP session."""

        self._session.close()

    def list_manifests(self) -> list[dict[str, Any]]:
        """Return safe metadata for all trusted manifests."""

        payload = self._request_json("get", "/api/execution/manifests")
        return cast(list[dict[str, Any]], payload)

    def get_manifest(self, name: str, version: str) -> dict[str, Any]:
        """Return safe metadata for one immutable manifest identity."""

        payload = self._request_json(
            "get", f"/api/execution/manifests/{name}/{version}"
        )
        return cast(dict[str, Any], payload)

    def register_worker(self, registration: Mapping[str, Any]) -> dict[str, Any]:
        """Register or refresh this worker's declared capabilities."""

        payload = dict(registration)
        if payload.get("worker_id") != self.worker_id:
            raise ValueError("registration worker_id must match the client worker_id")
        result = self._request_json("post", "/api/execution/workers", json=payload)
        return cast(dict[str, Any], result)

    def heartbeat_worker(self, *, status: str | None = None) -> dict[str, Any]:
        """Refresh worker liveness and optionally update availability status."""

        result = self._request_json(
            "post",
            f"/api/execution/workers/{self.worker_id}/heartbeat",
            json={"status": status},
        )
        return cast(dict[str, Any], result)

    def checkout(self) -> dict[str, Any]:
        """Attempt one non-retried atomic work-order checkout."""

        result = self._request_json(
            "post",
            "/api/execution/checkout",
            json={"worker_id": self.worker_id},
        )
        return cast(dict[str, Any], result)

    def get_work_order(self, work_order_id: int) -> dict[str, Any]:
        """Read repository, exact SHA, manifest, and policy for an assigned run."""

        result = self._request_json(
            "get", f"/api/execution/work-orders/{work_order_id}"
        )
        return cast(dict[str, Any], result)

    def get_run(self, run_id: int) -> dict[str, Any]:
        """Read one execution-run snapshot."""

        result = self._request_json("get", f"/api/execution/runs/{run_id}")
        return cast(dict[str, Any], result)

    def heartbeat_run(self, run_id: int) -> dict[str, Any]:
        """Renew the active run lease or raise when ownership has been lost."""

        result = self._request_json(
            "post",
            f"/api/execution/runs/{run_id}/heartbeat",
            json={"worker_id": self.worker_id},
            ownership_sensitive=True,
        )
        return cast(dict[str, Any], result)

    def complete_run(  # noqa: PLR0913 - mirrors the bounded completion contract
        self,
        run_id: int,
        *,
        status: str,
        result_summary: str | None = None,
        terminal_reason: str | None = None,
        cleanup_status: str | None = None,
        artifact_metadata: list[dict[str, Any]] | None = None,
        evidence_metadata: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Submit one terminal result without retrying ambiguous writes."""

        result = self._request_json(
            "post",
            f"/api/execution/runs/{run_id}/complete",
            json={
                "worker_id": self.worker_id,
                "status": status,
                "result_summary": result_summary,
                "terminal_reason": terminal_reason,
                "cleanup_status": cleanup_status,
                "artifact_metadata": artifact_metadata or [],
                "evidence_metadata": dict(evidence_metadata or {}),
            },
            ownership_sensitive=True,
        )
        return cast(dict[str, Any], result)

    def _request_json(
        self,
        method: str,
        path: str,
        *,
        ownership_sensitive: bool = False,
        **kwargs: Any,
    ) -> object:
        response = self._request(method, path, **kwargs)
        if ownership_sensitive and response.status_code in _OWNERSHIP_LOST_STATUSES:
            raise ExecutionOwnershipLostError(response.status_code)
        response.raise_for_status()
        return response.json()

    def _request(self, method: str, path: str, **kwargs: Any) -> Response:
        headers = dict(kwargs.pop("headers", {}))
        headers["Authorization"] = f"Bearer {self._admin_token}"
        headers.setdefault("Accept", "application/json")
        return self._session.request(
            method,
            f"{self.base_url}{path}",
            headers=headers,
            timeout=self._timeout,
            **kwargs,
        )


__all__ = [
    "DEFAULT_EXECUTION_TIMEOUT",
    "ExecutionClient",
    "ExecutionClientError",
    "ExecutionOwnershipLostError",
]
