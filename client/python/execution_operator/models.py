"""Bounded, path-free lifecycle facts and reports."""

from __future__ import annotations

import dataclasses
import datetime as dt
import json
import math
import re
from dataclasses import dataclass, field
from typing import Any, Literal

from server.execution.evidence import validate_relative_path
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
    schema_version: Literal[1]
    work_order_id: int
    run_id: int
    source_run_id: int
    phase: Literal["fresh", "reuse"]
    worker_id: str
    status: str
    reuse_decision: str
    reused_from_run_id: int | None
    reuse_identity_hash: str
    evidence_fingerprint: str
    evidence_retention_expires_at: str
    routing_policy: Literal["first_available"]
    route_reason: str
    required_quota_units: Literal[0]
    reserved_quota_units: Literal[0]
    quota_reservation_state: Literal["not_required"]
    eligible_candidate_count: int
    step_count: int
    artifact_count: int
    artifact_total_bytes: int
    route_verified: bool
    evidence_verified: bool
    local_evidence_verified: bool
    source_checkout_unchanged: bool
    steps: list[StepSummary] = field(default_factory=list)
    artifacts: list[ArtifactSummary] = field(default_factory=list)


@dataclass(slots=True)
class OperatorLifecycleReport:
    schema_version: Literal[2] = 2
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
        for run in self.runs:
            _validate_run_summary(run)
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
        _ = self.as_dict()
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
                f"source_run={run.source_run_id} "
                f"status={run.status} reuse={run.reuse_decision} "
                f"identity_hash={run.reuse_identity_hash} "
                f"route={run.routing_policy}:{run.route_reason} "
                f"worker={run.worker_id} eligible={run.eligible_candidate_count} "
                f"quota={run.required_quota_units}/{run.reserved_quota_units}:"
                f"{run.quota_reservation_state} steps={run.step_count} "
                f"artifacts={run.artifact_count} "
                f"artifact_bytes={run.artifact_total_bytes} "
                f"fingerprint={run.evidence_fingerprint} "
                f"expires={run.evidence_retention_expires_at}"
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
    if value is None or isinstance(value, (bool, int)):
        return
    if isinstance(value, float):
        _validate_public_number(value)
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


def _validate_public_number(value: float) -> None:
    if not math.isfinite(value):
        raise OperatorLifecycleFailure("report_number_invalid")


def _safe_relative_path(value: str) -> bool:
    if not value or len(value) > _MAX_STRING:
        return False
    try:
        return validate_relative_path(value) == value
    except ValueError:
        return False


def _validate_run_summary(run: RunSummary) -> None:
    artifact_bytes = sum(item.size_bytes for item in run.artifacts)
    try:
        expiry = dt.datetime.fromisoformat(
            run.evidence_retention_expires_at.replace("Z", "+00:00")
        )
    except ValueError as error:
        raise OperatorLifecycleFailure("report_run_invalid") from error
    phase_link_valid = (
        run.phase == "fresh"
        and run.source_run_id == run.run_id
        and run.reused_from_run_id is None
        and run.reuse_decision == "fresh"
    ) or (
        run.phase == "reuse"
        and run.reused_from_run_id == run.source_run_id
        and run.reuse_decision == "reused"
    )
    if (
        run.schema_version != 1
        or run.work_order_id < 1
        or run.run_id < 1
        or run.source_run_id < 1
        or not _SAFE_ID.fullmatch(run.worker_id)
        or not _DIGEST.fullmatch(run.reuse_identity_hash)
        or not _DIGEST.fullmatch(run.evidence_fingerprint)
        or len(run.evidence_retention_expires_at) > _MAX_TIMESTAMP_LENGTH
        or not run.evidence_retention_expires_at.endswith("Z")
        or expiry.tzinfo is None
        or expiry.utcoffset() is None
        or not phase_link_valid
        or run.status != "succeeded"
        or run.routing_policy != "first_available"
        or not _SAFE_REASON.fullmatch(run.route_reason)
        or run.required_quota_units != 0
        or run.reserved_quota_units != 0
        or run.quota_reservation_state != "not_required"
        or run.eligible_candidate_count < 1
        or run.step_count != len(run.steps)
        or run.artifact_count != len(run.artifacts)
        or run.artifact_total_bytes != artifact_bytes
        or artifact_bytes < 0
        or not run.route_verified
        or not run.evidence_verified
        or not run.local_evidence_verified
        or not run.source_checkout_unchanged
    ):
        raise OperatorLifecycleFailure("report_run_invalid")
    for step in run.steps:
        if (
            not _SAFE_ID.fullmatch(step.step_id)
            or not _SAFE_REASON.fullmatch(step.status)
            or step.duration_seconds < 0
        ):
            raise OperatorLifecycleFailure("report_run_invalid")
    for artifact in run.artifacts:
        if (
            not _SAFE_REASON.fullmatch(artifact.kind)
            or not _safe_relative_path(artifact.relative_path)
            or artifact.size_bytes < 0
            or not _DIGEST.fullmatch(artifact.sha256)
        ):
            raise OperatorLifecycleFailure("report_run_invalid")


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
