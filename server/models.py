"""Database models for Switchboard."""

import datetime as dt
from enum import Enum
from typing import Any

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    Enum as SAEnum,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from .db import Base
from .execution.enums import (
    ApprovalPolicy,
    ExecutionRunStatus,
    NetworkPolicy,
    RepositoryWritePolicy,
    ReuseDecision,
    ReusePolicy,
    WorkerStatus,
    WorkOrderStatus,
)
from .task_status import TaskStatus
from .time_utils import utcnow_naive

__all__ = [
    "Agent",
    "CommandManifest",
    "ExecPlan",
    "ExecPlanRegistry",
    "ExecutionLease",
    "ExecutionRun",
    "ExecutionWorkOrder",
    "ExecutionWorker",
    "FileEntry",
    "GitHubValidationRequest",
    "Lease",
    "PlanVersion",
    "SystemState",
    "Task",
    "TaskDependency",
]


def _enum_values(enum_type: type[Enum]) -> list[str]:
    """Persist string-enum values rather than implementation member names."""

    return [str(member.value) for member in enum_type]


class Agent(Base):
    __tablename__ = "agents"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    agent_id: Mapped[str] = mapped_column(String(128), unique=True, index=True)
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime, default=dt.datetime.utcnow
    )


class Task(Base):
    __tablename__ = "tasks"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    title: Mapped[str] = mapped_column(String(255))
    description: Mapped[str] = mapped_column(Text, default="")
    priority: Mapped[int] = mapped_column(
        Integer, default=0, nullable=False, index=True
    )
    status: Mapped[TaskStatus] = mapped_column(
        SAEnum(
            TaskStatus,
            native_enum=False,
            validate_strings=True,
            name="task_status",
        ),
        default=TaskStatus.PENDING,
    )
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime, default=dt.datetime.utcnow
    )
    updated_at: Mapped[dt.datetime] = mapped_column(
        DateTime, default=dt.datetime.utcnow, onupdate=dt.datetime.utcnow
    )
    completed_notes: Mapped[str | None] = mapped_column(Text, nullable=True)


class TaskDependency(Base):
    __tablename__ = "task_dependencies"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    task_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("tasks.id", ondelete="CASCADE")
    )
    depends_on_task_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("tasks.id", ondelete="CASCADE")
    )
    __table_args__ = (
        UniqueConstraint("task_id", "depends_on_task_id", name="uq_task_dep"),
    )


class Lease(Base):
    __tablename__ = "leases"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    task_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("tasks.id", ondelete="CASCADE"), unique=True
    )
    agent_id: Mapped[str] = mapped_column(String(128), index=True)
    expires_at: Mapped[dt.datetime] = mapped_column(DateTime, index=True)
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime, default=dt.datetime.utcnow
    )
    updated_at: Mapped[dt.datetime] = mapped_column(
        DateTime, default=dt.datetime.utcnow, onupdate=dt.datetime.utcnow
    )


class FileEntry(Base):
    __tablename__ = "files"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    path: Mapped[str] = mapped_column(String(1024), unique=True, index=True)
    sha256: Mapped[str] = mapped_column(String(64))
    size: Mapped[int] = mapped_column(Integer, default=0)
    updated_at: Mapped[dt.datetime] = mapped_column(
        DateTime, default=dt.datetime.utcnow, onupdate=dt.datetime.utcnow
    )


class PlanVersion(Base):
    __tablename__ = "plan_versions"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    value: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    updated_at: Mapped[dt.datetime] = mapped_column(
        DateTime,
        default=dt.datetime.utcnow,
        onupdate=dt.datetime.utcnow,
    )


class SystemState(Base):
    """Singleton row storing orchestration maintenance flags."""

    __tablename__ = "system_state"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    maintenance_mode: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False
    )
    message: Mapped[str | None] = mapped_column(Text, nullable=True)
    updated_at: Mapped[dt.datetime] = mapped_column(
        DateTime, default=dt.datetime.utcnow, onupdate=dt.datetime.utcnow
    )
    version: Mapped[int] = mapped_column(Integer, default=0, nullable=False)


class ExecPlanRegistry(Base):
    """Metadata describing the published ExecPlan registry index."""

    __tablename__ = "exec_plan_registry"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    registry_id: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    schema_version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    generated_at: Mapped[dt.datetime] = mapped_column(
        DateTime, default=dt.datetime.utcnow
    )
    source_url: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    source_etag: Mapped[str | None] = mapped_column(String(128), nullable=True)
    extensions: Mapped[list[dict[str, Any]] | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime, default=dt.datetime.utcnow, nullable=False
    )
    updated_at: Mapped[dt.datetime] = mapped_column(
        DateTime,
        default=dt.datetime.utcnow,
        onupdate=dt.datetime.utcnow,
        nullable=False,
    )


class ExecPlan(Base):
    """Persisted ExecPlan metadata for registry publication."""

    __tablename__ = "exec_plans"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    plan_id: Mapped[str] = mapped_column(
        String(255), unique=True, nullable=False, index=True
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    lifecycle_created_at: Mapped[dt.datetime | None] = mapped_column(
        DateTime, nullable=True
    )
    lifecycle_updated_at: Mapped[dt.datetime | None] = mapped_column(
        DateTime, nullable=True
    )
    lifecycle_target_completion: Mapped[dt.datetime | None] = mapped_column(
        DateTime, nullable=True
    )
    owners: Mapped[list[dict[str, Any]] | None] = mapped_column(JSON, nullable=True)
    tags: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)
    scope: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    links: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    metrics: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    changelog_token: Mapped[str | None] = mapped_column(String(128), nullable=True)
    extensions: Mapped[list[dict[str, Any]] | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime, default=dt.datetime.utcnow, nullable=False
    )
    updated_at: Mapped[dt.datetime] = mapped_column(
        DateTime,
        default=dt.datetime.utcnow,
        onupdate=dt.datetime.utcnow,
        nullable=False,
    )


class CommandManifest(Base):
    """Persisted snapshot of a trusted, immutable manifest identity."""

    __tablename__ = "execution_command_manifests"
    __table_args__ = (
        UniqueConstraint("name", "version", name="uq_execution_manifest_identity"),
        CheckConstraint(
            "repository_write_policy = 'read_only'",
            name="ck_execution_manifest_read_only",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    version: Mapped[str] = mapped_column(String(64), nullable=False)
    schema_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    digest: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    trusted_registry_source: Mapped[str] = mapped_column(String(512), nullable=False)
    required_capabilities: Mapped[dict[str, Any]] = mapped_column(
        JSON, nullable=False, default=dict
    )
    fixed_step_metadata: Mapped[list[dict[str, Any]]] = mapped_column(
        JSON, nullable=False, default=list
    )
    environment_policy: Mapped[dict[str, Any]] = mapped_column(
        JSON, nullable=False, default=dict
    )
    network_policy: Mapped[NetworkPolicy] = mapped_column(
        SAEnum(
            NetworkPolicy,
            native_enum=False,
            validate_strings=True,
            values_callable=_enum_values,
            name="execution_manifest_network_policy",
        ),
        nullable=False,
    )
    repository_write_policy: Mapped[RepositoryWritePolicy] = mapped_column(
        SAEnum(
            RepositoryWritePolicy,
            native_enum=False,
            validate_strings=True,
            values_callable=_enum_values,
            name="execution_manifest_repository_write_policy",
        ),
        nullable=False,
        default=RepositoryWritePolicy.READ_ONLY,
    )
    timeout_seconds: Mapped[int] = mapped_column(Integer, nullable=False)
    artifact_declarations: Mapped[list[dict[str, Any]]] = mapped_column(
        JSON, nullable=False, default=list
    )
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime, default=utcnow_naive, nullable=False
    )


class ExecutionWorkOrder(Base):
    """Separate persisted request for one approved deterministic validation."""

    __tablename__ = "execution_work_orders"
    __table_args__ = (
        CheckConstraint(
            "repository_write_allowed = 0",
            name="ck_execution_work_order_read_only",
        ),
        CheckConstraint("attempt_count >= 0", name="ck_execution_attempt_count"),
        CheckConstraint(
            "reuse_policy IN ('never', 'allow_exact', 'require_exact')",
            name="ck_execution_work_order_reuse_policy",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    schema_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    repository_full_name: Mapped[str] = mapped_column(
        String(255), nullable=False, index=True
    )
    commit_sha: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    manifest_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("execution_command_manifests.id", ondelete="RESTRICT"),
        nullable=False,
    )
    manifest_name: Mapped[str] = mapped_column(String(128), nullable=False)
    manifest_version: Mapped[str] = mapped_column(String(64), nullable=False)
    manifest_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    manifest_parameters: Mapped[dict[str, Any]] = mapped_column(
        JSON, nullable=False, default=dict
    )
    required_capabilities: Mapped[dict[str, Any]] = mapped_column(
        JSON, nullable=False, default=dict
    )
    permitted_paths: Mapped[list[str]] = mapped_column(
        JSON, nullable=False, default=list
    )
    forbidden_scope_notes: Mapped[str] = mapped_column(Text, nullable=False, default="")
    expected_artifact_kinds: Mapped[list[str]] = mapped_column(
        JSON, nullable=False, default=list
    )
    approval_policy: Mapped[ApprovalPolicy] = mapped_column(
        SAEnum(
            ApprovalPolicy,
            native_enum=False,
            validate_strings=True,
            values_callable=_enum_values,
            name="execution_approval_policy",
        ),
        nullable=False,
        default=ApprovalPolicy.EXPLICIT,
    )
    status: Mapped[WorkOrderStatus] = mapped_column(
        SAEnum(
            WorkOrderStatus,
            native_enum=False,
            validate_strings=True,
            values_callable=_enum_values,
            name="execution_work_order_status",
        ),
        nullable=False,
        default=WorkOrderStatus.PENDING_APPROVAL,
        index=True,
    )
    timeout_seconds: Mapped[int] = mapped_column(Integer, nullable=False)
    resource_metadata: Mapped[dict[str, Any]] = mapped_column(
        JSON, nullable=False, default=dict
    )
    network_policy: Mapped[NetworkPolicy] = mapped_column(
        SAEnum(
            NetworkPolicy,
            native_enum=False,
            validate_strings=True,
            values_callable=_enum_values,
            name="execution_work_order_network_policy",
        ),
        nullable=False,
    )
    repository_write_allowed: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )
    preferred_executor: Mapped[str | None] = mapped_column(String(128), nullable=True)
    cost_ceiling: Mapped[float | None] = mapped_column(Float, nullable=True)
    reuse_policy: Mapped[ReusePolicy] = mapped_column(
        SAEnum(
            ReusePolicy,
            native_enum=False,
            validate_strings=True,
            values_callable=_enum_values,
            name="execution_reuse_policy",
        ),
        nullable=False,
        default=ReusePolicy.NEVER,
    )
    execution_policy_hash: Mapped[str] = mapped_column(
        String(64), nullable=False, index=True
    )
    attempt_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime, default=utcnow_naive, nullable=False
    )
    updated_at: Mapped[dt.datetime] = mapped_column(
        DateTime,
        default=utcnow_naive,
        onupdate=utcnow_naive,
        nullable=False,
    )
    approved_at: Mapped[dt.datetime | None] = mapped_column(DateTime, nullable=True)
    queued_at: Mapped[dt.datetime | None] = mapped_column(DateTime, nullable=True)
    assigned_at: Mapped[dt.datetime | None] = mapped_column(DateTime, nullable=True)
    started_at: Mapped[dt.datetime | None] = mapped_column(DateTime, nullable=True)
    finished_at: Mapped[dt.datetime | None] = mapped_column(DateTime, nullable=True)
    terminal_reason: Mapped[str | None] = mapped_column(Text, nullable=True)


class ExecutionWorker(Base):
    """Registered pull worker and its immutable Phase 1 capability posture."""

    __tablename__ = "execution_workers"
    __table_args__ = (
        CheckConstraint("max_concurrency >= 1", name="ck_execution_worker_capacity"),
        CheckConstraint(
            "active_run_count >= 0", name="ck_execution_worker_active_runs"
        ),
        CheckConstraint(
            "repository_write_capability = 0",
            name="ck_execution_worker_read_only",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    worker_id: Mapped[str] = mapped_column(
        String(128), unique=True, nullable=False, index=True
    )
    display_name: Mapped[str] = mapped_column(String(255), nullable=False)
    operating_system: Mapped[str] = mapped_column(String(64), nullable=False)
    architecture: Mapped[str] = mapped_column(String(64), nullable=False)
    python_version: Mapped[str | None] = mapped_column(String(64), nullable=True)
    node_version: Mapped[str | None] = mapped_column(String(64), nullable=True)
    docker_available: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )
    browsers: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    gpu_available: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    unity_available: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )
    desktop_available: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )
    capabilities: Mapped[dict[str, Any]] = mapped_column(
        JSON, nullable=False, default=dict
    )
    max_concurrency: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    active_run_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    network_policy_capability: Mapped[NetworkPolicy] = mapped_column(
        SAEnum(
            NetworkPolicy,
            native_enum=False,
            validate_strings=True,
            values_callable=_enum_values,
            name="execution_worker_network_policy",
        ),
        nullable=False,
        default=NetworkPolicy.WORKER_RESTRICTED,
    )
    repository_write_capability: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )
    status: Mapped[WorkerStatus] = mapped_column(
        SAEnum(
            WorkerStatus,
            native_enum=False,
            validate_strings=True,
            values_callable=_enum_values,
            name="execution_worker_status",
        ),
        nullable=False,
        default=WorkerStatus.ONLINE,
        index=True,
    )
    last_heartbeat_at: Mapped[dt.datetime] = mapped_column(DateTime, nullable=False)
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime, default=utcnow_naive, nullable=False
    )
    updated_at: Mapped[dt.datetime] = mapped_column(
        DateTime,
        default=utcnow_naive,
        onupdate=utcnow_naive,
        nullable=False,
    )


class ExecutionRun(Base):
    """Historical record of one attempt to execute a work order."""

    __tablename__ = "execution_runs"
    __table_args__ = (
        UniqueConstraint(
            "work_order_id", "attempt_number", name="uq_execution_run_attempt"
        ),
        Index(
            "ix_execution_run_exact_reuse_candidate",
            "reuse_identity_hash",
            "worker_id",
            "status",
        ),
        CheckConstraint(
            "reuse_decision IN ('not_requested', 'pending', "
            "'candidate_available', 'fresh', 'reused', 'unavailable')",
            name="ck_execution_run_reuse_decision",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    work_order_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("execution_work_orders.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    worker_id: Mapped[str] = mapped_column(
        String(128),
        ForeignKey("execution_workers.worker_id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    attempt_number: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[ExecutionRunStatus] = mapped_column(
        SAEnum(
            ExecutionRunStatus,
            native_enum=False,
            validate_strings=True,
            values_callable=_enum_values,
            name="execution_run_status",
        ),
        nullable=False,
        default=ExecutionRunStatus.ASSIGNED,
        index=True,
    )
    queued_at: Mapped[dt.datetime] = mapped_column(DateTime, nullable=False)
    assigned_at: Mapped[dt.datetime] = mapped_column(DateTime, nullable=False)
    started_at: Mapped[dt.datetime | None] = mapped_column(DateTime, nullable=True)
    finished_at: Mapped[dt.datetime | None] = mapped_column(DateTime, nullable=True)
    lease_expires_at: Mapped[dt.datetime] = mapped_column(DateTime, nullable=False)
    last_heartbeat_at: Mapped[dt.datetime] = mapped_column(DateTime, nullable=False)
    result_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    terminal_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    cleanup_status: Mapped[str | None] = mapped_column(String(64), nullable=True)
    artifact_metadata: Mapped[list[dict[str, Any]]] = mapped_column(
        JSON, nullable=False, default=list
    )
    evidence_metadata: Mapped[dict[str, Any]] = mapped_column(
        JSON, nullable=False, default=dict
    )
    reuse_identity: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    reuse_identity_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    reused_from_run_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("execution_runs.id", ondelete="RESTRICT"),
        nullable=True,
        index=True,
    )
    source_evidence_fingerprint: Mapped[str | None] = mapped_column(
        String(64), nullable=True
    )
    reuse_decision: Mapped[ReuseDecision] = mapped_column(
        SAEnum(
            ReuseDecision,
            native_enum=False,
            validate_strings=True,
            values_callable=_enum_values,
            name="execution_reuse_decision",
        ),
        nullable=False,
        default=ReuseDecision.NOT_REQUESTED,
    )
    reuse_reason: Mapped[str | None] = mapped_column(String(64), nullable=True)
    reuse_candidate_metadata: Mapped[dict[str, Any] | None] = mapped_column(
        JSON, nullable=True
    )
    evidence_retention_expires_at: Mapped[dt.datetime | None] = mapped_column(
        DateTime, nullable=True, index=True
    )
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime, default=utcnow_naive, nullable=False
    )
    updated_at: Mapped[dt.datetime] = mapped_column(
        DateTime,
        default=utcnow_naive,
        onupdate=utcnow_naive,
        nullable=False,
    )


class ExecutionLease(Base):
    """The single active ownership claim for an execution work order."""

    __tablename__ = "execution_leases"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    work_order_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("execution_work_orders.id", ondelete="RESTRICT"),
        nullable=False,
        unique=True,
        index=True,
    )
    execution_run_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("execution_runs.id", ondelete="RESTRICT"),
        nullable=False,
        unique=True,
        index=True,
    )
    worker_id: Mapped[str] = mapped_column(
        String(128),
        ForeignKey("execution_workers.worker_id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    expires_at: Mapped[dt.datetime] = mapped_column(
        DateTime, nullable=False, index=True
    )
    last_heartbeat_at: Mapped[dt.datetime] = mapped_column(DateTime, nullable=False)
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime, default=utcnow_naive, nullable=False
    )
    updated_at: Mapped[dt.datetime] = mapped_column(
        DateTime,
        default=utcnow_naive,
        onupdate=utcnow_naive,
        nullable=False,
    )


class GitHubValidationRequest(Base):
    """Server-owned GitHub request identity and publication lifecycle."""

    __tablename__ = "github_validation_requests"
    __table_args__ = (
        UniqueConstraint(
            "idempotency_key", name="uq_github_validation_idempotency_key"
        ),
        UniqueConstraint("work_order_id", name="uq_github_validation_work_order"),
        CheckConstraint(
            "schema_version = 1", name="ck_github_validation_schema_version"
        ),
        CheckConstraint(
            "length(idempotency_key) = 64",
            name="ck_github_validation_idempotency_length",
        ),
        CheckConstraint(
            "length(head_sha) = 40", name="ck_github_validation_head_sha_length"
        ),
        CheckConstraint(
            "length(base_sha) = 40", name="ck_github_validation_base_sha_length"
        ),
        CheckConstraint(
            "length(manifest_digest) = 64",
            name="ck_github_validation_manifest_digest_length",
        ),
        CheckConstraint(
            "pull_request_number >= 1",
            name="ck_github_validation_pull_request_number",
        ),
        CheckConstraint(
            "repository_id >= 1 AND pull_request_id >= 1 "
            "AND head_repository_id >= 1",
            name="ck_github_validation_stable_numeric_ids",
        ),
        CheckConstraint(
            "length(github_api_url) BETWEEN 1 AND 512 "
            "AND length(github_host) BETWEEN 1 AND 255",
            name="ck_github_validation_configured_origin_bounds",
        ),
        CheckConstraint(
            "length(repository_full_name) BETWEEN 3 AND 255 "
            "AND length(head_repository_full_name) BETWEEN 3 AND 255",
            name="ck_github_validation_repository_identity_bounds",
        ),
        CheckConstraint(
            "length(repository_node_id) BETWEEN 1 AND 128 "
            "AND length(pull_request_node_id) BETWEEN 1 AND 128",
            name="ck_github_validation_node_identity_bounds",
        ),
        CheckConstraint(
            "(github_actor_id IS NULL AND github_actor_node_id IS NULL) OR "
            "(github_actor_id >= 1 AND "
            "length(github_actor_node_id) BETWEEN 1 AND 128)",
            name="ck_github_validation_actor_identity",
        ),
        CheckConstraint(
            "pull_request_state IN ('open', 'closed')",
            name="ck_github_validation_pull_request_state",
        ),
        CheckConstraint(
            "length(base_ref) BETWEEN 1 AND 255 "
            "AND length(head_ref) BETWEEN 1 AND 255",
            name="ck_github_validation_ref_bounds",
        ),
        CheckConstraint(
            "length(manifest_name) BETWEEN 1 AND 128 "
            "AND length(manifest_version) BETWEEN 1 AND 64 "
            "AND length(operator_id) BETWEEN 1 AND 128",
            name="ck_github_validation_server_identity_bounds",
        ),
        CheckConstraint(
            "managed_comment_id IS NULL OR managed_comment_id >= 1",
            name="ck_github_validation_managed_comment_id",
        ),
        CheckConstraint(
            "publication_head_sha IS NULL OR length(publication_head_sha) = 40",
            name="ck_github_validation_publication_head_sha_length",
        ),
        CheckConstraint(
            "last_transport_reason IS NULL "
            "OR length(last_transport_reason) BETWEEN 1 AND 64",
            name="ck_github_validation_transport_reason_bounds",
        ),
        CheckConstraint(
            "publication_reason IS NULL "
            "OR length(publication_reason) BETWEEN 1 AND 64",
            name="ck_github_validation_publication_reason_bounds",
        ),
        CheckConstraint(
            (
                "publication_state IN "
                "('not_published', 'published_current', 'published_stale', "
                "'retryable_failure', 'failed')"
            ),
            name="ck_github_validation_publication_state",
        ),
        CheckConstraint(
            "publication_decision IN ('not_evaluated', 'current', 'stale')",
            name="ck_github_validation_publication_decision",
        ),
        CheckConstraint(
            "(publication_claim_token IS NULL "
            "AND publication_claimed_at IS NULL "
            "AND publication_claim_expires_at IS NULL) OR "
            "(length(publication_claim_token) = 64 "
            "AND publication_claimed_at IS NOT NULL "
            "AND publication_claim_expires_at IS NOT NULL "
            "AND publication_claim_expires_at > publication_claimed_at)",
            name="ck_github_validation_publication_claim",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    schema_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    idempotency_key: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    github_api_url: Mapped[str] = mapped_column(String(512), nullable=False)
    github_host: Mapped[str] = mapped_column(String(255), nullable=False)
    repository_full_name: Mapped[str] = mapped_column(String(255), nullable=False)
    repository_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    repository_node_id: Mapped[str] = mapped_column(String(128), nullable=False)
    github_actor_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    github_actor_node_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    pull_request_number: Mapped[int] = mapped_column(Integer, nullable=False)
    pull_request_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    pull_request_node_id: Mapped[str] = mapped_column(String(128), nullable=False)
    pull_request_state: Mapped[str] = mapped_column(String(16), nullable=False)
    pull_request_draft: Mapped[bool] = mapped_column(Boolean, nullable=False)
    pull_request_merged: Mapped[bool] = mapped_column(Boolean, nullable=False)
    base_ref: Mapped[str] = mapped_column(String(255), nullable=False)
    base_sha: Mapped[str] = mapped_column(String(40), nullable=False)
    head_ref: Mapped[str] = mapped_column(String(255), nullable=False)
    head_sha: Mapped[str] = mapped_column(String(40), nullable=False)
    head_repository_full_name: Mapped[str] = mapped_column(String(255), nullable=False)
    head_repository_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    manifest_name: Mapped[str] = mapped_column(String(128), nullable=False)
    manifest_version: Mapped[str] = mapped_column(String(64), nullable=False)
    manifest_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    operator_id: Mapped[str] = mapped_column(String(128), nullable=False)
    work_order_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("execution_work_orders.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    terminal_run_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("execution_runs.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    managed_comment_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    publication_state: Mapped[str] = mapped_column(
        String(32), nullable=False, default="not_published"
    )
    publication_decision: Mapped[str] = mapped_column(
        String(16), nullable=False, default="not_evaluated"
    )
    publication_head_sha: Mapped[str | None] = mapped_column(String(40), nullable=True)
    last_transport_reason: Mapped[str | None] = mapped_column(String(64), nullable=True)
    publication_reason: Mapped[str | None] = mapped_column(String(64), nullable=True)
    publication_claim_token: Mapped[str | None] = mapped_column(
        String(64), nullable=True
    )
    publication_claimed_at: Mapped[dt.datetime | None] = mapped_column(
        DateTime, nullable=True
    )
    publication_claim_expires_at: Mapped[dt.datetime | None] = mapped_column(
        DateTime, nullable=True, index=True
    )
    last_resolved_at: Mapped[dt.datetime] = mapped_column(DateTime, nullable=False)
    last_publication_attempt_at: Mapped[dt.datetime | None] = mapped_column(
        DateTime, nullable=True
    )
    published_at: Mapped[dt.datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime, default=utcnow_naive, nullable=False
    )
    updated_at: Mapped[dt.datetime] = mapped_column(
        DateTime,
        default=utcnow_naive,
        onupdate=utcnow_naive,
        nullable=False,
    )
