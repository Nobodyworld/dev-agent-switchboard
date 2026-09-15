"""Authenticated HTTP client for the execution control-plane API."""

from __future__ import annotations

import json
import re
from collections.abc import Mapping
from dataclasses import dataclass
from types import TracebackType
from typing import Any, Self, cast

from requests import Response, Session

from server.execution.text_policy import (
    contains_absolute_local_path,
    contains_worker_credential,
)

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
    if (
        contains_worker_credential(normalized)
        or contains_absolute_local_path(normalized)
        or _SENSITIVE_ERROR_TEXT.search(normalized)
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


class ExecutionCredentialRejectedError(ExecutionOwnershipLostError):
    """Authentication loss permanently stops this worker client's requests."""


class _ExecutionTransport:
    _worker_scoped = False

    def __init__(  # noqa: PLR0913, RUF100
        self,
        base_url: str,
        worker_id: str,
        token: str,
        *,
        session: Session | None = None,
        timeout: float = DEFAULT_EXECUTION_TIMEOUT,
    ) -> None:
        if not token.strip():
            raise ValueError("token is required for execution endpoints")
        if not worker_id.strip():
            raise ValueError("worker_id must not be empty")

        self.base_url = base_url.rstrip("/")
        self.worker_id = worker_id
        self._token = token
        self._session = session or Session()
        self._timeout = float(timeout)
        self._credential_rejected = False

    def __enter__(self) -> Self:
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

    def _request_json(
        self,
        method: str,
        path: str,
        *,
        ownership_sensitive: bool = False,
        **kwargs: Any,
    ) -> object:
        if self._worker_scoped and self._credential_rejected:
            raise ExecutionCredentialRejectedError(401)
        response = self._request(method, path, **kwargs)
        if self._worker_scoped and response.status_code in {401, 403}:
            self._credential_rejected = True
            raise ExecutionCredentialRejectedError(response.status_code)
        if ownership_sensitive and response.status_code in _OWNERSHIP_LOST_STATUSES:
            raise ExecutionOwnershipLostError(response.status_code)
        if response.status_code >= _HTTP_ERROR_STATUS:
            raise _execution_http_error(response)
        response.raise_for_status()
        return response.json()

    def _request(self, method: str, path: str, **kwargs: Any) -> Response:
        headers = dict(kwargs.pop("headers", {}))
        headers["Authorization"] = f"Bearer {self._token}"
        headers.setdefault("Accept", "application/json")
        return self._session.request(
            method,
            f"{self.base_url}{path}",
            headers=headers,
            timeout=self._timeout,
            **kwargs,
        )


class WorkerExecutionClient(_ExecutionTransport):
    """Only the nine reviewed worker lifecycle operations; no administrator API."""

    _prefix = "/api/execution/worker"
    _worker_scoped = True

    def __init__(
        self,
        base_url: str,
        worker_id: str,
        worker_token: str,
        *,
        session: Session | None = None,
        timeout: float = DEFAULT_EXECUTION_TIMEOUT,
    ) -> None:
        super().__init__(
            base_url, worker_id, worker_token, session=session, timeout=timeout
        )

    def get_manifest(
        self, name: str, version: str, *, run_id: int | None = None
    ) -> dict[str, Any]:
        """Return safe metadata for one immutable manifest identity."""

        payload = self._request_json(
            "get",
            f"{self._prefix}/manifests/{name}/{version}",
            params={"run_id": run_id} if self._worker_scoped else {},
        )
        return cast(dict[str, Any], payload)

    def register_worker(self, registration: Mapping[str, Any]) -> dict[str, Any]:
        """Register or refresh this worker's declared capabilities."""

        payload = dict(registration)
        if payload.get("worker_id") != self.worker_id:
            raise ValueError("registration worker_id must match the client worker_id")
        result = self._request_json("post", f"{self._prefix}/workers", json=payload)
        return cast(dict[str, Any], result)

    def heartbeat_worker(self, *, status: str | None = None) -> dict[str, Any]:
        """Refresh worker liveness and optionally update availability status."""

        result = self._request_json(
            "post",
            f"{self._prefix}/workers/{self.worker_id}/heartbeat",
            json={"status": status},
        )
        return cast(dict[str, Any], result)

    def checkout(self) -> dict[str, Any]:
        """Attempt one non-retried atomic work-order checkout."""

        result = self._request_json(
            "post",
            f"{self._prefix}/checkout",
            json={"worker_id": self.worker_id},
        )
        return cast(dict[str, Any], result)

    def get_work_order(self, work_order_id: int) -> dict[str, Any]:
        """Read repository, exact SHA, manifest, and policy for an assigned run."""

        result = self._request_json(
            "get", f"{self._prefix}/work-orders/{work_order_id}"
        )
        return cast(dict[str, Any], result)

    def get_run(self, run_id: int) -> dict[str, Any]:
        """Read one execution-run snapshot."""

        result = self._request_json("get", f"{self._prefix}/runs/{run_id}")
        return cast(dict[str, Any], result)

    def heartbeat_run(self, run_id: int) -> dict[str, Any]:
        """Renew the active run lease or raise when ownership has been lost."""

        result = self._request_json(
            "post",
            f"{self._prefix}/runs/{run_id}/heartbeat",
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
            f"{self._prefix}/runs/{run_id}/reuse-candidate",
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
            f"{self._prefix}/runs/{run_id}/complete",
            json=payload,
            ownership_sensitive=True,
        )
        return cast(dict[str, Any], result)


class ExecutionClient(WorkerExecutionClient):
    """Existing administrator/operator API, including deliberate provisioning."""

    _prefix = "/api/execution"
    _worker_scoped = False

    def __init__(
        self,
        base_url: str,
        worker_id: str,
        admin_token: str,
        *,
        session: Session | None = None,
        timeout: float = DEFAULT_EXECUTION_TIMEOUT,
    ) -> None:
        super().__init__(
            base_url, worker_id, admin_token, session=session, timeout=timeout
        )

    def issue_worker_credential(self) -> dict[str, Any]:
        return cast(
            dict[str, Any],
            self._request_json(
                "post",
                f"/api/execution/worker-credentials/{self.worker_id}/issue",
                json={},
            ),
        )

    def rotate_worker_credential(self, credential_id: str) -> dict[str, Any]:
        return cast(
            dict[str, Any],
            self._request_json(
                "post",
                f"/api/execution/worker-credentials/{self.worker_id}/rotate",
                json={"credential_id": credential_id},
            ),
        )

    def revoke_worker_credential(self, credential_id: str) -> dict[str, Any]:
        return cast(
            dict[str, Any],
            self._request_json(
                "post",
                f"/api/execution/worker-credentials/{self.worker_id}/revoke",
                json={"credential_id": credential_id},
            ),
        )

    def list_manifests(self) -> list[dict[str, Any]]:
        """Return safe metadata for all trusted manifests."""

        payload = self._request_json("get", "/api/execution/manifests")
        return cast(list[dict[str, Any]], payload)

    def health_ready(self) -> dict[str, Any]:
        """Read the bounded readiness probe for an owned local server."""

        return cast(dict[str, Any], self._request_json("get", "/health/ready"))

    def list_workers(self) -> dict[str, Any]:
        """Read the bounded operator worker projection."""

        return cast(
            dict[str, Any],
            self._request_json("get", "/api/execution/workers?limit=100&offset=0"),
        )

    def repository_readiness(
        self,
        *,
        repository_full_name: str,
        manifest_name: str,
        manifest_version: str,
        preferred_executor: str,
    ) -> dict[str, Any]:
        """Read non-mutating readiness for one trusted repository contract."""

        owner, repository = repository_full_name.split("/", 1)
        result = self._request_json(
            "get",
            f"/api/execution/trusted-repositories/{owner}/{repository}/readiness",
            params={
                "manifest_name": manifest_name,
                "manifest_version": manifest_version,
                "routing_policy": "first_available",
                "required_quota_units": 0,
                "preferred_executor": preferred_executor,
            },
        )
        return cast(dict[str, Any], result)

    def create_work_order(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        """Create one explicit-approval work order without retrying the write."""

        return cast(
            dict[str, Any],
            self._request_json(
                "post", "/api/execution/work-orders", json=dict(payload)
            ),
        )

    def approve_work_order(self, work_order_id: int) -> dict[str, Any]:
        """Approve one order without implicitly queueing it."""

        return cast(
            dict[str, Any],
            self._request_json(
                "post",
                f"/api/execution/work-orders/{work_order_id}/approve",
                json={"queue": False},
            ),
        )

    def queue_work_order(self, work_order_id: int) -> dict[str, Any]:
        """Queue one separately approved work order."""

        return cast(
            dict[str, Any],
            self._request_json(
                "post", f"/api/execution/work-orders/{work_order_id}/queue", json={}
            ),
        )

    def assess_work_order_route(self, work_order_id: int) -> dict[str, Any]:
        """Read current route readiness without reserving state."""

        return cast(
            dict[str, Any],
            self._request_json(
                "get", f"/api/execution/work-orders/{work_order_id}/route-assessment"
            ),
        )

    def get_work_order_route(self, work_order_id: int) -> dict[str, Any]:
        """Read persisted route provenance."""

        return cast(
            dict[str, Any],
            self._request_json(
                "get", f"/api/execution/work-orders/{work_order_id}/route"
            ),
        )

    def list_runs(self, work_order_id: int) -> list[dict[str, Any]]:
        """Read bounded runs for one work order."""

        return cast(
            list[dict[str, Any]],
            self._request_json(
                "get", f"/api/execution/runs?work_order_id={work_order_id}"
            ),
        )

    def get_run_evidence(self, run_id: int) -> dict[str, Any]:
        """Read one compact validated evidence record."""

        return cast(
            dict[str, Any],
            self._request_json("get", f"/api/execution/runs/{run_id}/evidence"),
        )


__all__ = [
    "DEFAULT_EXECUTION_TIMEOUT",
    "ExecutionClient",
    "ExecutionClientError",
    "ExecutionCredentialRejectedError",
    "ExecutionHttpError",
    "ExecutionOwnershipLostError",
    "ExecutionValidationError",
    "WorkerExecutionClient",
]
