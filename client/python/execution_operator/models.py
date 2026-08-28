"""Bounded, path-free lifecycle facts and reports."""

from __future__ import annotations

import dataclasses
import datetime as dt
import json
import re
from dataclasses import dataclass, field
from typing import Any, Literal

from server.execution.text_policy import contains_absolute_local_path

_SAFE_REASON = re.compile(r"^[a-z0-9][a-z0-9_.:-]{0,127}$")
_SAFE_ID = re.compile(r"^[A-Za-z0-9_.:@/-]{1,255}$")
_SHA = re.compile(r"^[0-9a-f]{40}$")
_DIGEST = re.compile(r"^[0-9a-f]{64}$")
_MAX_ITEMS = 128
_MAX_STRING = 512
_MAX_DEPTH = 8
_MAX_MAPPING_ITEMS = 64
_MAX_KEY_LENGTH = 64
_MAX_TIMESTAMP_LENGTH = 64


class OperatorLifecycleFailure(RuntimeError):  # noqa: N818 - accepted plan name
    """A bounded public failure reason with no raw exception text."""

    def __init__(self, reason: str) -> None:
        if not _SAFE_REASON.fullmatch(reason):
            reason = "operator_lifecycle_failure"
        super().__init__(reason)
        self.reason = reason


@dataclass(frozen=True, slots=True)
class RuntimeSummary:
    schema_version: Literal[1]
    runtime_id: str
    repository_full_name: str
    target_sha: str
    manifest_name: str
    manifest_version: str
    manifest_digest: str
    mode: str
    command_identity: str
    created_at: str


@dataclass(frozen=True, slots=True)
class StepSummary:
    step_id: str
    status: str
    duration_seconds: float


@dataclass(frozen=True, slots=True)
class ArtifactSummary:
    kind: str
    relative_path: str
    size_bytes: int
    sha256: str


@dataclass(frozen=True, slots=True)
class RunSummary:
    work_order_id: int
    run_id: int
    phase: Literal["fresh", "reuse"]
    worker_id: str
    status: str
    reuse_decision: str
    reused_from_run_id: int | None
    evidence_fingerprint: str | None
    evidence_retention_expires_at: str | None
    step_count: int
    artifact_count: int
    route_verified: bool
    evidence_verified: bool
    local_evidence_verified: bool
    source_checkout_unchanged: bool
    steps: list[StepSummary] = field(default_factory=list)
    artifacts: list[ArtifactSummary] = field(default_factory=list)


@dataclass(slots=True)
class OperatorLifecycleReport:
    schema_version: Literal[1] = 1
    outcome: Literal["succeeded", "failed", "inspected"] = "failed"
    reason: str = "not_started"
    runtime: RuntimeSummary | None = None
    phases: list[str] = field(default_factory=list)
    preflight_checks: list[str] = field(default_factory=list)
    preflight_passed: bool = False
    server_ready: bool = False
    worker_ready: bool = False
    fresh_approved: bool = False
    reuse_approved: bool = False
    runs: list[RunSummary] = field(default_factory=list)
    active_lease_count: int | None = None
    worker_active_run_count: int | None = None
    owned_processes_stopped: bool = False
    port_released: bool = False
    canonical_checkout_unchanged: bool = False
    failed_runtime_preserved: bool = False
    operator_action_count: int = 0
    avoided_deterministic_step_count: int = 0
    completed_at: str | None = None

    def as_dict(self) -> dict[str, Any]:
        payload = dataclasses.asdict(self)
        _validate_public_value(payload)
        return payload

    def as_json_bytes(self, *, maximum_bytes: int) -> bytes:
        encoded = json.dumps(
            self.as_dict(), sort_keys=True, separators=(",", ":"), ensure_ascii=True
        ).encode("utf-8")
        if len(encoded) > maximum_bytes:
            raise OperatorLifecycleFailure("report_size_limit_exceeded")
        return encoded

    def as_text(self, *, maximum_bytes: int) -> bytes:
        lines = [
            "Switchboard operator validation lifecycle",
            f"outcome: {self.outcome}",
            f"reason: {self.reason}",
            f"preflight: {self.preflight_passed}",
            f"server_ready: {self.server_ready}",
            f"worker_ready: {self.worker_ready}",
            f"fresh_approved: {self.fresh_approved}",
            f"reuse_approved: {self.reuse_approved}",
            f"runs: {len(self.runs)}",
            f"active_lease_count: {self.active_lease_count}",
            f"owned_processes_stopped: {self.owned_processes_stopped}",
            f"port_released: {self.port_released}",
            f"canonical_checkout_unchanged: {self.canonical_checkout_unchanged}",
            f"failed_runtime_preserved: {self.failed_runtime_preserved}",
            f"operator_action_count: {self.operator_action_count}",
            (
                "avoided_deterministic_step_count: "
                f"{self.avoided_deterministic_step_count}"
            ),
            f"phases: {','.join(self.phases)}",
        ]
        for run in self.runs:
            lines.append(
                f"{run.phase}: work_order={run.work_order_id} run={run.run_id} "
                f"status={run.status} reuse={run.reuse_decision} "
                f"steps={run.step_count} artifacts={run.artifact_count}"
            )
        encoded = ("\n".join(lines) + "\n").encode("utf-8")
        if len(encoded) > maximum_bytes:
            raise OperatorLifecycleFailure("report_size_limit_exceeded")
        return encoded


def _validate_public_value(value: object, *, depth: int = 0) -> None:
    if depth > _MAX_DEPTH:
        raise OperatorLifecycleFailure("report_depth_limit_exceeded")
    if isinstance(value, str):
        if len(value) > _MAX_STRING or contains_absolute_local_path(value):
            raise OperatorLifecycleFailure("report_text_policy_rejected")
        return
    if value is None or isinstance(value, (bool, int, float)):
        return
    if isinstance(value, list):
        if len(value) > _MAX_ITEMS:
            raise OperatorLifecycleFailure("report_collection_limit_exceeded")
        for item in value:
            _validate_public_value(item, depth=depth + 1)
        return
    if isinstance(value, dict):
        if len(value) > _MAX_MAPPING_ITEMS:
            raise OperatorLifecycleFailure("report_collection_limit_exceeded")
        for key, item in value.items():
            if not isinstance(key, str) or len(key) > _MAX_KEY_LENGTH:
                raise OperatorLifecycleFailure("report_key_policy_rejected")
            _validate_public_value(item, depth=depth + 1)
        return
    raise OperatorLifecycleFailure("report_type_rejected")


def utc_now_text() -> str:
    return dt.datetime.now(dt.UTC).isoformat().replace("+00:00", "Z")


def validate_runtime_summary(summary: RuntimeSummary) -> None:
    if (
        summary.schema_version != 1
        or not _SAFE_ID.fullmatch(summary.runtime_id)
        or not _SAFE_ID.fullmatch(summary.repository_full_name)
        or not _SHA.fullmatch(summary.target_sha)
        or not _SAFE_ID.fullmatch(summary.manifest_name)
        or not _SAFE_ID.fullmatch(summary.manifest_version)
        or not _DIGEST.fullmatch(summary.manifest_digest)
        or summary.mode not in {"fresh-only", "fresh-then-exact-reuse"}
        or summary.command_identity != "validation-lifecycle@1"
        or len(summary.created_at) > _MAX_TIMESTAMP_LENGTH
    ):
        raise OperatorLifecycleFailure("runtime_marker_invalid")


__all__ = [
    "ArtifactSummary",
    "OperatorLifecycleFailure",
    "OperatorLifecycleReport",
    "RunSummary",
    "RuntimeSummary",
    "StepSummary",
    "utc_now_text",
    "validate_runtime_summary",
]
