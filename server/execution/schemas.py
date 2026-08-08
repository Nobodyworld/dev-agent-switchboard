"""Typed FastAPI contracts for the non-executing execution control plane."""

from __future__ import annotations

import datetime as dt
import re
from collections.abc import Mapping
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from .enums import (
    ApprovalPolicy,
    ExecutionRunStatus,
    NetworkPolicy,
    QuotaReservationState,
    RepositoryWritePolicy,
    ReuseDecision,
    ReusePolicy,
    RoutingPolicy,
    WorkerStatus,
    WorkOrderStatus,
)
from .evidence import (
    ArtifactRecord,
    EvidenceReuseIdentity,
    ExecutionEvidence,
    ReuseCandidate,
)
from .routing import MAX_ROUTING_INTEGER
from .text_policy import (
    validate_no_absolute_local_paths,
    validate_optional_no_absolute_local_path,
)

_FORBIDDEN_EXECUTABLE_KEYS = frozenset(
    {
        "argv",
        "command",
        "command_string",
        "shell",
        "shell_command",
        "script",
        "script_contents",
        "executable",
        "executable_path",
    }
)


def _require_aware_timestamp(value: dt.datetime | None) -> dt.datetime | None:
    if value is not None and (value.tzinfo is None or value.utcoffset() is None):
        raise ValueError("quota_reset_at must be timezone-aware")
    return value


def _reject_executable_keys(value: object, *, field_name: str) -> None:
    """Reject executable-shaped keys at every depth of caller JSON metadata."""

    if isinstance(value, Mapping):
        for key, nested in value.items():
            normalized = re.sub(r"[^a-z0-9]+", "_", str(key).lower()).strip("_")
            if normalized in _FORBIDDEN_EXECUTABLE_KEYS:
                raise ValueError(
                    f"{field_name} must not contain executable field '{normalized}'"
                )
            _reject_executable_keys(nested, field_name=field_name)
    elif isinstance(value, (list, tuple)):
        for nested in value:
            _reject_executable_keys(nested, field_name=field_name)


class ExecutionInput(BaseModel):
    """Strict base for all caller-controlled execution request payloads."""

    model_config = ConfigDict(extra="forbid")

    @model_validator(mode="before")
    @classmethod
    def reject_absolute_local_paths(cls, value: object) -> object:
        """Reject local path disclosure in execution-plane request text."""

        return validate_no_absolute_local_paths(value)


class ManifestReferenceIn(ExecutionInput):
    """Identity-only reference to a server-controlled trusted manifest."""

    name: str = Field(min_length=1, max_length=128, pattern=r"^[a-z0-9][a-z0-9-]*$")
    version: str = Field(min_length=1, max_length=64)
    parameters: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def reject_executable_parameters(self) -> ManifestReferenceIn:
        """Keep caller manifest references identity/parameter-only."""

        _reject_executable_keys(self.parameters, field_name="manifest.parameters")
        return self


class WorkOrderCreateIn(ExecutionInput):
    """Safe creation contract; intentionally contains no executable fields."""

    schema_version: Literal[1] = 1
    repository_full_name: str = Field(
        min_length=3,
        max_length=255,
        pattern=r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$",
    )
    commit_sha: str = Field(pattern=r"^[0-9a-fA-F]{40}$")
    manifest: ManifestReferenceIn
    required_capabilities: dict[str, Any] = Field(default_factory=dict)
    permitted_paths: list[str] = Field(default_factory=list, max_length=128)
    forbidden_scope_notes: str = Field(default="", max_length=4000)
    expected_artifact_kinds: list[str] = Field(default_factory=list, max_length=64)
    approval_policy: ApprovalPolicy = ApprovalPolicy.EXPLICIT
    timeout_seconds: int = Field(default=3600, ge=1, le=86400)
    resource_metadata: dict[str, Any] = Field(default_factory=dict)
    network_policy: NetworkPolicy = NetworkPolicy.WORKER_RESTRICTED
    repository_write: Literal[False] = False
    preferred_executor: str | None = Field(default=None, max_length=128)
    cost_ceiling: float | None = Field(default=None, ge=0)
    reuse_policy: ReusePolicy = ReusePolicy.NEVER
    routing_policy: RoutingPolicy = RoutingPolicy.FIRST_AVAILABLE
    maximum_cost_units: int | None = Field(
        default=None, strict=True, ge=0, le=MAX_ROUTING_INTEGER
    )
    required_quota_units: int = Field(
        default=0, strict=True, ge=0, le=MAX_ROUTING_INTEGER
    )

    @model_validator(mode="after")
    def reject_executable_metadata(self) -> WorkOrderCreateIn:
        """Keep all persisted caller metadata non-executable by construction."""

        _reject_executable_keys(
            self.required_capabilities, field_name="required_capabilities"
        )
        _reject_executable_keys(self.resource_metadata, field_name="resource_metadata")
        return self


class ApproveWorkOrderIn(ExecutionInput):
    """Approval request that may immediately make the order worker-visible."""

    queue: bool = True


class ReasonIn(ExecutionInput):
    """Optional bounded reason supplied for an operator lifecycle action."""

    reason: str | None = Field(default=None, max_length=4000)


class WorkerRegistrationIn(ExecutionInput):
    """Read-only worker declaration used for registration or refresh."""

    worker_id: str = Field(min_length=1, max_length=128)
    display_name: str = Field(min_length=1, max_length=255)
    operating_system: str = Field(min_length=1, max_length=64)
    architecture: str = Field(min_length=1, max_length=64)
    python_version: str | None = Field(default=None, max_length=64)
    node_version: str | None = Field(default=None, max_length=64)
    docker_available: bool = False
    browsers: list[str] = Field(default_factory=list, max_length=32)
    gpu_available: bool = False
    unity_available: bool = False
    desktop_available: bool = False
    capabilities: dict[str, Any] = Field(default_factory=dict)
    max_concurrency: int = Field(default=1, ge=1, le=64)
    network_policy_capability: NetworkPolicy = NetworkPolicy.WORKER_RESTRICTED
    repository_write_capability: Literal[False] = False
    status: WorkerStatus = WorkerStatus.ONLINE

    @model_validator(mode="after")
    def reject_executable_capabilities(self) -> WorkerRegistrationIn:
        """Worker declarations carry capabilities, never execution instructions."""

        _reject_executable_keys(self.capabilities, field_name="capabilities")
        return self


class WorkerHeartbeatIn(ExecutionInput):
    """Worker liveness update with an optional availability state change."""

    status: WorkerStatus | None = None


class WorkerRoutingProfileCreateIn(ExecutionInput):
    """Privileged creation contract for server-owned routing state."""

    schema_version: Literal[1] = 1
    worker_id: str = Field(min_length=1, max_length=128)
    enabled: bool = Field(default=True, strict=True)
    estimated_cost_units_per_run: int = Field(strict=True, ge=0, le=MAX_ROUTING_INTEGER)
    quota_capacity_units: int = Field(strict=True, ge=0, le=MAX_ROUTING_INTEGER)
    quota_remaining_units: int = Field(strict=True, ge=0, le=MAX_ROUTING_INTEGER)
    quota_reset_at: dt.datetime | None = None
    routing_priority: int = Field(default=0, strict=True, ge=0, le=MAX_ROUTING_INTEGER)

    @field_validator("quota_reset_at")
    @classmethod
    def validate_reset_timestamp(cls, value: dt.datetime | None) -> dt.datetime | None:
        return _require_aware_timestamp(value)

    @model_validator(mode="after")
    def validate_quota_bounds(self) -> WorkerRoutingProfileCreateIn:
        if self.quota_remaining_units > self.quota_capacity_units:
            raise ValueError("quota_remaining_units must not exceed capacity")
        return self


class WorkerRoutingProfileReplaceIn(ExecutionInput):
    """Revision-protected full replacement for one routing profile."""

    expected_revision: int = Field(strict=True, ge=1, le=MAX_ROUTING_INTEGER)
    enabled: bool = Field(strict=True)
    estimated_cost_units_per_run: int = Field(strict=True, ge=0, le=MAX_ROUTING_INTEGER)
    quota_capacity_units: int = Field(strict=True, ge=0, le=MAX_ROUTING_INTEGER)
    quota_remaining_units: int = Field(strict=True, ge=0, le=MAX_ROUTING_INTEGER)
    quota_reset_at: dt.datetime | None = None
    routing_priority: int = Field(strict=True, ge=0, le=MAX_ROUTING_INTEGER)

    @field_validator("quota_reset_at")
    @classmethod
    def validate_reset_timestamp(cls, value: dt.datetime | None) -> dt.datetime | None:
        return _require_aware_timestamp(value)

    @model_validator(mode="after")
    def validate_quota_bounds(self) -> WorkerRoutingProfileReplaceIn:
        if self.quota_remaining_units > self.quota_capacity_units:
            raise ValueError("quota_remaining_units must not exceed capacity")
        return self


class RoutingQuotaResetIn(ExecutionInput):
    """Revision-safe explicit quota replacement with idempotency timestamp."""

    expected_revision: int = Field(strict=True, ge=1, le=MAX_ROUTING_INTEGER)
    quota_remaining_units: int = Field(strict=True, ge=0, le=MAX_ROUTING_INTEGER)
    quota_reset_at: dt.datetime

    @field_validator("quota_reset_at")
    @classmethod
    def validate_reset_timestamp(cls, value: dt.datetime) -> dt.datetime:
        validated = _require_aware_timestamp(value)
        if validated is None:  # pragma: no cover - field itself is required
            raise ValueError("quota_reset_at is required")
        return validated


class CheckoutIn(ExecutionInput):
    """Pull-based checkout request from a previously registered worker."""

    worker_id: str = Field(min_length=1, max_length=128)


class RunHeartbeatIn(ExecutionInput):
    """Ownership proof for an execution lease heartbeat."""

    worker_id: str = Field(min_length=1, max_length=128)


class ExecutionCompletionIn(ExecutionInput):
    """Bounded terminal control-plane outcome; never command output execution."""

    worker_id: str = Field(min_length=1, max_length=128)
    status: Literal["succeeded", "failed", "timed_out", "cancelled"]
    result_summary: str | None = Field(default=None, max_length=32768)
    terminal_reason: str | None = Field(default=None, max_length=4000)
    cleanup_status: str | None = Field(default=None, max_length=64)
    artifact_metadata: list[ArtifactRecord] = Field(
        default_factory=list, max_length=128
    )
    evidence_metadata: ExecutionEvidence | None = None
    reuse_decision: ReuseDecision | None = None
    reuse_reason: str | None = Field(
        default=None,
        min_length=1,
        max_length=64,
        pattern=r"^[a-z0-9][a-z0-9_.:-]*$",
    )
    reuse_identity: EvidenceReuseIdentity | None = None
    reuse_identity_hash: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    evidence_retention_expires_at: dt.datetime | None = None

    @field_validator("evidence_metadata", mode="before")
    @classmethod
    def normalize_legacy_empty_evidence(cls, value: object) -> object:
        """Accept the Phase 1A empty-object sentinel as absent evidence."""

        return None if value == {} else value

    @model_validator(mode="after")
    def reject_executable_result_metadata(self) -> ExecutionCompletionIn:
        """Completion reports remain metadata-only placeholders in Phase 1A."""

        artifact_payload = [
            item.model_dump(mode="json") for item in self.artifact_metadata
        ]
        _reject_executable_keys(artifact_payload, field_name="artifact_metadata")
        if self.evidence_metadata is not None:
            evidence_payload = self.evidence_metadata.model_dump(mode="json")
            _reject_executable_keys(evidence_payload, field_name="evidence_metadata")
            if self.evidence_metadata.artifacts != self.artifact_metadata:
                raise ValueError("artifact metadata must match complete evidence")
            if self.evidence_metadata.worker_id != self.worker_id:
                raise ValueError("evidence worker identity must match completion")
            if self.evidence_metadata.terminal_status != self.status:
                raise ValueError("evidence terminal status must match completion")
        return self


class CommandManifestOut(BaseModel):
    """Trusted manifest identity and non-executable contract metadata."""

    id: int
    name: str
    version: str
    schema_version: int
    digest: str
    description: str
    trusted_registry_source: str
    required_capabilities: dict[str, Any]
    fixed_step_metadata: list[dict[str, Any]]
    environment_policy: dict[str, Any]
    network_policy: NetworkPolicy
    repository_write_policy: RepositoryWritePolicy
    timeout_seconds: int
    artifact_declarations: list[dict[str, Any]]
    created_at: dt.datetime

    model_config = ConfigDict(from_attributes=True)


class WorkOrderOut(BaseModel):
    """Persisted work-order snapshot including resolved manifest identity."""

    id: int
    schema_version: int
    repository_full_name: str
    commit_sha: str
    manifest_name: str
    manifest_version: str
    manifest_digest: str
    manifest_parameters: dict[str, Any]
    required_capabilities: dict[str, Any]
    permitted_paths: list[str]
    forbidden_scope_notes: str
    expected_artifact_kinds: list[str]
    approval_policy: ApprovalPolicy
    status: WorkOrderStatus
    timeout_seconds: int
    resource_metadata: dict[str, Any]
    network_policy: NetworkPolicy
    repository_write_allowed: bool
    preferred_executor: str | None
    cost_ceiling: float | None
    routing_policy: RoutingPolicy
    maximum_cost_units: int | None
    required_quota_units: int
    attempt_count: int
    created_at: dt.datetime
    updated_at: dt.datetime
    approved_at: dt.datetime | None
    queued_at: dt.datetime | None
    assigned_at: dt.datetime | None
    started_at: dt.datetime | None
    finished_at: dt.datetime | None
    terminal_reason: str | None
    reuse_policy: ReusePolicy
    execution_policy_hash: str
    route_provenance: RouteProvenanceOut | None

    model_config = ConfigDict(from_attributes=True)

    _local_path = field_validator("terminal_reason")(
        validate_optional_no_absolute_local_path
    )


class WorkerOut(BaseModel):
    """Persisted worker capability declaration and capacity state."""

    id: int
    worker_id: str
    display_name: str
    operating_system: str
    architecture: str
    python_version: str | None
    node_version: str | None
    docker_available: bool
    browsers: list[str]
    gpu_available: bool
    unity_available: bool
    desktop_available: bool
    capabilities: dict[str, Any]
    max_concurrency: int
    active_run_count: int
    network_policy_capability: NetworkPolicy
    repository_write_capability: bool
    status: WorkerStatus
    last_heartbeat_at: dt.datetime
    last_checkout_poll_at: dt.datetime | None
    created_at: dt.datetime
    updated_at: dt.datetime

    model_config = ConfigDict(from_attributes=True)


class ExecutionRunOut(BaseModel):
    """Historical execution-attempt record with strict compact metadata."""

    id: int
    work_order_id: int
    worker_id: str
    attempt_number: int
    status: ExecutionRunStatus
    queued_at: dt.datetime
    assigned_at: dt.datetime
    started_at: dt.datetime | None
    finished_at: dt.datetime | None
    lease_expires_at: dt.datetime
    last_heartbeat_at: dt.datetime
    result_summary: str | None
    terminal_reason: str | None
    cleanup_status: str | None
    artifact_metadata: list[ArtifactRecord]
    evidence_metadata: ExecutionEvidence | None
    reuse_identity: EvidenceReuseIdentity | None
    reuse_identity_hash: str | None
    reused_from_run_id: int | None
    source_evidence_fingerprint: str | None
    reuse_decision: ReuseDecision
    reuse_reason: str | None
    evidence_retention_expires_at: dt.datetime | None
    route_provenance: RouteProvenanceOut
    created_at: dt.datetime
    updated_at: dt.datetime

    model_config = ConfigDict(from_attributes=True)

    _local_paths = field_validator(
        "worker_id", "result_summary", "terminal_reason", "cleanup_status"
    )(validate_optional_no_absolute_local_path)

    @field_validator("evidence_metadata", mode="before")
    @classmethod
    def normalize_legacy_empty_evidence(cls, value: object) -> object:
        """Expose the non-null database sentinel as API null."""

        return None if value == {} else value


class CheckoutOut(BaseModel):
    """Checkout result with a run only when the worker wins an atomic claim."""

    run: ExecutionRunOut | None = None
    reason: str | None = None
    mismatch_reasons: list[str] = Field(default_factory=list)


class WorkerRoutingProfileOut(BaseModel):
    """Bounded privileged view of one operator-owned routing profile."""

    schema_version: int
    worker_id: str
    enabled: bool
    estimated_cost_units_per_run: int
    quota_capacity_units: int
    quota_remaining_units: int
    quota_reset_at: dt.datetime | None
    routing_priority: int
    revision: int = Field(ge=1, le=MAX_ROUTING_INTEGER)
    created_at: dt.datetime
    updated_at: dt.datetime

    model_config = ConfigDict(from_attributes=True)

    @field_validator("quota_reset_at", mode="before")
    @classmethod
    def normalize_reset_timestamp(cls, value: dt.datetime | None) -> dt.datetime | None:
        if value is not None and (value.tzinfo is None or value.utcoffset() is None):
            return value.replace(tzinfo=dt.UTC)
        return value.astimezone(dt.UTC) if value is not None else None


class RouteProvenanceOut(BaseModel):
    """Compact route decision safe for normal work-order and run APIs."""

    schema_version: Literal[1]
    routing_policy: RoutingPolicy
    selected_worker_id: str = Field(min_length=1, max_length=128)
    selected_routing_profile_revision: int | None = Field(
        default=None, ge=1, le=MAX_ROUTING_INTEGER
    )
    estimated_cost_units: int | None = Field(default=None, ge=0, le=MAX_ROUTING_INTEGER)
    required_quota_units: int = Field(ge=0, le=MAX_ROUTING_INTEGER)
    reserved_quota_units: int = Field(ge=0, le=MAX_ROUTING_INTEGER)
    quota_reservation_state: QuotaReservationState
    eligible_candidate_count: int = Field(ge=1, le=MAX_ROUTING_INTEGER)
    explicit_pin_applied: bool
    reason: str = Field(min_length=1, max_length=64, pattern=r"^[a-z0-9][a-z0-9_.:-]*$")
    decision_timestamp: dt.datetime


class RouteAssessmentOut(BaseModel):
    """Read-only bounded assessment for one queued work order."""

    schema_version: Literal[1]
    work_order_id: int = Field(ge=1)
    routing_policy: RoutingPolicy
    selected_worker_id: str | None = Field(default=None, max_length=128)
    selected_routing_profile_revision: int | None = Field(
        default=None, ge=1, le=MAX_ROUTING_INTEGER
    )
    estimated_cost_units: int | None = Field(default=None, ge=0, le=MAX_ROUTING_INTEGER)
    required_quota_units: int = Field(ge=0, le=MAX_ROUTING_INTEGER)
    reserved_quota_units: Literal[0] = 0
    quota_reservation_state: QuotaReservationState = QuotaReservationState.NOT_REQUIRED
    eligible_candidate_count: int = Field(ge=0, le=MAX_ROUTING_INTEGER)
    explicit_pin_applied: bool
    reason: str = Field(min_length=1, max_length=64, pattern=r"^[a-z0-9][a-z0-9_.:-]*$")
    decision_timestamp: dt.datetime

    model_config = ConfigDict(from_attributes=True)


class ReuseCandidateRequestIn(ExecutionInput):
    """Worker-derived current identity used for exact server lookup only."""

    worker_id: str = Field(min_length=1, max_length=128)
    reuse_identity: EvidenceReuseIdentity
    reuse_identity_hash: str = Field(pattern=r"^[0-9a-f]{64}$")


class ReuseCandidateOut(BaseModel):
    """Server-owned exact candidate or a bounded unavailable disposition."""

    decision: ReuseDecision
    reason: str = Field(min_length=1, max_length=64, pattern=r"^[a-z0-9][a-z0-9_.:-]*$")
    candidate: ReuseCandidate | None = None


class ExpireLeasesOut(BaseModel):
    """Summary returned after stale execution lease maintenance."""

    requeued_work_order_ids: list[int] = Field(default_factory=list)
    timed_out_run_ids: list[int] = Field(default_factory=list)
