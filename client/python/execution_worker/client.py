"""Authenticated HTTP client for the execution control-plane API."""

from __future__ import annotations

import json
import re
from collections.abc import Mapping
from dataclasses import dataclass
from types import TracebackType
from typing import Any, cast

from requests import Response, Session

from server.execution.text_policy import contains_absolute_local_path

DEFAULT_EXECUTION_TIMEOUT = 10.0
_OWNERSHIP_LOST_STATUSES = {404, 409}
_HTTP_ERROR_STATUS = 400
_UNPROCESSABLE_ENTITY = 422
_MAX_ERROR_BODY_BYTES = 64 * 1024
_MAX_VALIDATION_ERRORS = 8
_MAX_VALIDATION_LOCATION_PARTS = 8
_MAX_VALIDATION_LOCATION_PART_LENGTH = 64
_MAX_VALIDATION_MESSAGE_LENGTH = 256
_SAFE_ERROR_IDENTIFIER = re.compile(r"^[A-Za-z0-9_.-]+$")
_SENSITIVE_ERROR_TEXT = re.compile(
    r"(?i)(?:authorization|bearer|password|secret|token|api[_-]?key)"
)


class ExecutionClientError(RuntimeError):
    """Base error raised by the execution worker client."""


class ExecutionOwnershipLostError(ExecutionClientError):
    """Raised when the server no longer recognizes this worker as run owner."""

    def __init__(self, status_code: int) -> None:
        super().__init__(f"execution_run_ownership_lost:{status_code}")
        self.status_code = status_code


@dataclass(frozen=True, slots=True)
class ExecutionValidationError:
    """One bounded, sanitized FastAPI validation detail."""

    location: tuple[str | int, ...]
    error_type: str
    message: str


class ExecutionHttpError(ExecutionClientError):
    """Safe structured execution API failure without a raw response body."""

    def __init__(
        self,
        status_code: int,
        reason: str,
        validation_errors: tuple[ExecutionValidationError, ...] = (),
    ) -> None:
        details = ";".join(
            f"{'.'.join(str(part) for part in item.location)}:"
            f"{item.error_type}:{item.message}"
            for item in validation_errors
        )
        suffix = f":{details}" if details else ""
        super().__init__(f"{reason}:{status_code}{suffix}")
        self.status_code = status_code
        self.reason = reason
        self.validation_errors = validation_errors


def _safe_error_text(value: object, *, limit: int) -> str | None:
    if not isinstance(value, str):
        return None
    normalized = " ".join(value.split())
    if not normalized:
        return None
    if contains_absolute_local_path(normalized) or _SENSITIVE_ERROR_TEXT.search(
        normalized
    ):
        return "[REDACTED]"
    return normalized[:limit]


def _safe_validation_location(value: object) -> tuple[str | int, ...] | None:
    if not isinstance(value, list) or not value:
        return None
    location: list[str | int] = []
    for part in value[:_MAX_VALIDATION_LOCATION_PARTS]:
        if isinstance(part, int) and not isinstance(part, bool):
            location.append(part)
            continue
        safe_part = _safe_error_text(part, limit=_MAX_VALIDATION_LOCATION_PART_LENGTH)
        if safe_part is None or not _SAFE_ERROR_IDENTIFIER.fullmatch(safe_part):
            location.append("[REDACTED]")
        else:
            location.append(safe_part)
    return tuple(location)


def _bounded_validation_errors(
    response: Response,
) -> tuple[ExecutionValidationError, ...]:
    raw = getattr(response, "content", b"")
    if not isinstance(raw, bytes) or len(raw) > _MAX_ERROR_BODY_BYTES:
        return ()
    try:
        payload = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError):
        return ()
    if not isinstance(payload, Mapping) or not isinstance(payload.get("detail"), list):
        return ()

    errors: list[ExecutionValidationError] = []
    for item in payload["detail"][:_MAX_VALIDATION_ERRORS]:
        if not isinstance(item, Mapping):
            continue
        location = _safe_validation_location(item.get("loc"))
        error_type = _safe_error_text(item.get("type"), limit=64)
        message = _safe_error_text(
            item.get("msg"), limit=_MAX_VALIDATION_MESSAGE_LENGTH
        )
        if location is None or error_type is None or message is None:
            continue
        if not _SAFE_ERROR_IDENTIFIER.fullmatch(error_type):
            error_type = "validation_error"
        errors.append(ExecutionValidationError(location, error_type, message))
    return tuple(errors)


def _execution_http_error(response: Response) -> ExecutionHttpError:
    errors = (
        _bounded_validation_errors(response)
        if response.status_code == _UNPROCESSABLE_ENTITY
        else ()
    )
    reason = "execution_validation_error" if errors else "execution_http_error"
    return ExecutionHttpError(response.status_code, reason, errors)


class ExecutionClient:
    """Small authenticated client dedicated to execution-plane endpoints."""

    def __init__(  # noqa: PLR0913, RUF100
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

    def resolve_reuse_candidate(
        self,
        run_id: int,
        *,
        reuse_identity: Mapping[str, Any],
        reuse_identity_hash: str,
    ) -> dict[str, Any]:
        """Request one exact server-selected source without retrying the write."""

        result = self._request_json(
            "post",
            f"/api/execution/runs/{run_id}/reuse-candidate",
            json={
                "worker_id": self.worker_id,
                "reuse_identity": dict(reuse_identity),
                "reuse_identity_hash": reuse_identity_hash,
            },
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
        reuse_decision: str | None = None,
        reuse_reason: str | None = None,
        reuse_identity: Mapping[str, Any] | None = None,
        reuse_identity_hash: str | None = None,
        evidence_retention_expires_at: str | None = None,
    ) -> dict[str, Any]:
        """Submit one terminal result without retrying ambiguous writes."""

        payload: dict[str, Any] = {
            "worker_id": self.worker_id,
            "status": status,
            "result_summary": result_summary,
            "terminal_reason": terminal_reason,
            "cleanup_status": cleanup_status,
            "artifact_metadata": artifact_metadata or [],
            "evidence_metadata": (
                dict(evidence_metadata) if evidence_metadata is not None else None
            ),
        }
        optional_reuse = {
            "reuse_decision": reuse_decision,
            "reuse_reason": reuse_reason,
            "reuse_identity": (
                dict(reuse_identity) if reuse_identity is not None else None
            ),
            "reuse_identity_hash": reuse_identity_hash,
            "evidence_retention_expires_at": evidence_retention_expires_at,
        }
        payload.update(
            {key: value for key, value in optional_reuse.items() if value is not None}
        )
        result = self._request_json(
            "post",
            f"/api/execution/runs/{run_id}/complete",
            json=payload,
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
        if response.status_code >= _HTTP_ERROR_STATUS:
            raise _execution_http_error(response)
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
    "ExecutionHttpError",
    "ExecutionOwnershipLostError",
    "ExecutionValidationError",
]
