"""Typed commands and outcomes used by the execution lifecycle service."""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field
from typing import Any

from .enums import (
    ApprovalPolicy,
    ExecutionRunStatus,
    NetworkPolicy,
    ReuseDecision,
    ReusePolicy,
    WorkerStatus,
    WorkOrderStatus,
)
from .evidence import (
    ArtifactRecord,
    EvidenceReuseIdentity,
    ExecutionEvidence,
    ReuseCandidate,
)


@dataclass(frozen=True, slots=True)
class WorkOrderDraft:
    """Caller-controlled, non-executable data for a new work order."""

    schema_version: int
    repository_full_name: str
    commit_sha: str
    manifest_name: str
    manifest_version: str
    manifest_parameters: dict[str, Any]
    required_capabilities: dict[str, Any]
    permitted_paths: tuple[str, ...]
    forbidden_scope_notes: str
    expected_artifact_kinds: tuple[str, ...]
    approval_policy: ApprovalPolicy
    timeout_seconds: int
    resource_metadata: dict[str, Any]
    network_policy: NetworkPolicy
    repository_write_allowed: bool
    preferred_executor: str | None
    cost_ceiling: float | None
    reuse_policy: ReusePolicy = ReusePolicy.NEVER


@dataclass(frozen=True, slots=True)
class WorkerRegistration:
    """Worker-controlled capability declaration for Phase 1 registration."""

    worker_id: str
    display_name: str
    operating_system: str
    architecture: str
    python_version: str | None
    node_version: str | None
    docker_available: bool
    browsers: tuple[str, ...]
    gpu_available: bool
    unity_available: bool
    desktop_available: bool
    capabilities: dict[str, Any]
    max_concurrency: int
    network_policy_capability: NetworkPolicy
    repository_write_capability: bool
    status: WorkerStatus


@dataclass(frozen=True, slots=True)
class ExecutionCompletion:
    """Bounded terminal metadata submitted by the lease-owning worker."""

    status: ExecutionRunStatus
    result_summary: str | None = None
    terminal_reason: str | None = None
    cleanup_status: str | None = None
    artifact_metadata: tuple[ArtifactRecord, ...] = field(default_factory=tuple)
    evidence_metadata: ExecutionEvidence | None = None
    reuse_decision: ReuseDecision | None = None
    reuse_reason: str | None = None
    reuse_identity: EvidenceReuseIdentity | None = None
    reuse_identity_hash: str | None = None
    evidence_retention_expires_at: dt.datetime | None = None


@dataclass(frozen=True, slots=True)
class CheckoutResult:
    """A successful run assignment or an explainable non-assignment."""

    run_id: int | None
    work_order_id: int | None
    reason: str | None
    mismatch_reasons: tuple[str, ...] = field(default_factory=tuple)

    @property
    def assigned(self) -> bool:
        """Return whether the worker successfully acquired a run."""

        return self.run_id is not None


@dataclass(frozen=True, slots=True)
class ExpiryResult:
    """Summary of stale active runs terminalized and safely requeued."""

    requeued_work_order_ids: tuple[int, ...]
    timed_out_run_ids: tuple[int, ...]


@dataclass(frozen=True, slots=True)
class WorkOrderTransition:
    """Explicit transition detail used by tests and the API layer."""

    previous: WorkOrderStatus
    current: WorkOrderStatus


@dataclass(frozen=True, slots=True)
class ReuseCandidateResult:
    """Exact server lookup disposition for one lease-owning worker."""

    decision: ReuseDecision
    reason: str
    candidate: ReuseCandidate | None = None
