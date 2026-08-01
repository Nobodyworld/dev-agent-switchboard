"""Pydantic models for the Switchboard API surface."""

import datetime as dt
from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from .task_status import TaskStatus

__all__ = [
    "ActivityEventOut",
    "ActivityFeedOut",
    "AdminSettingsOut",
    "AgentIn",
    "AgentRegistrationResponse",
    "CheckoutFailureReason",
    "CheckoutOut",
    "CompleteIn",
    "CompleteResponse",
    "ConfigurationResponse",
    "DatabaseSettingsOut",
    "DiagnosticsPackageOut",
    "DiagnosticsReportOut",
    "EnvironmentVariableOut",
    "ExecPlanEntry",
    "ExecPlanLifecycle",
    "ExecPlanOwner",
    "ExecPlanRegistryIndex",
    "ExecPlanRegistrySource",
    "ExecutionRoutingSettingsOut",
    "ExtensionDescriptorOut",
    "ExtensionSettingsOut",
    "FileUploadResponse",
    "HealthEnvelopeOut",
    "HealthObservation",
    "HealthStatus",
    "LeaseSettingsOut",
    "MetricsCatalogOut",
    "ObservabilityHealthOut",
    "OkResponse",
    "PlanOut",
    "RateLimitSettingsOut",
    "RuntimeInfoOut",
    "SettingsResponse",
    "StatusResponse",
    "StorageInfoOut",
    "SystemStateOut",
    "SystemStateUpdateIn",
    "TaskAnalyticsOut",
    "TaskIn",
    "TaskOut",
    "TaskStatus",
    "TaskUpdate",
    "TelemetryReportOut",
    "TelemetrySubsystemOut",
]


class AgentIn(BaseModel):
    agent_name: str = Field(..., description="Human-readable or unique agent ID")


MAX_TITLE_LENGTH = 200
MAX_DESCRIPTION_LENGTH = 5000


class TaskIn(BaseModel):
    title: str = Field(
        ..., max_length=MAX_TITLE_LENGTH, description="Short task summary"
    )
    description: str = Field(
        default="",
        max_length=MAX_DESCRIPTION_LENGTH,
        description="Long-form task details",
    )
    depends_on: list[int] = Field(default_factory=list)
    priority: int = Field(
        default=0,
        description="Higher values are checked out before lower priority tasks",
    )


class TaskUpdate(BaseModel):
    title: str | None = Field(
        default=None,
        max_length=MAX_TITLE_LENGTH,
        description="Updated task title",
    )
    description: str | None = Field(
        default=None,
        max_length=MAX_DESCRIPTION_LENGTH,
        description="Updated task description",
    )
    status: TaskStatus | None = None
    depends_on: list[int] | None = Field(default=None)
    priority: int | None = Field(
        default=None,
        description="Override the task priority used during checkout",
    )


class TaskOut(BaseModel):
    id: int
    title: str
    description: str
    status: TaskStatus
    priority: int
    completed_notes: str | None = None
    depends_on: list[int] = Field(default_factory=list)

    model_config = ConfigDict(from_attributes=True)


class TaskAnalyticsOut(BaseModel):
    total_tasks: int = Field(ge=0)
    pending_tasks: int = Field(ge=0)
    in_progress_tasks: int = Field(ge=0)
    completed_tasks: int = Field(ge=0)
    ready_tasks: int = Field(ge=0)
    blocked_tasks: int = Field(ge=0)
    with_dependencies: int = Field(ge=0)
    without_dependencies: int = Field(ge=0)
    dependency_edges: int = Field(ge=0)
    missing_dependency_tasks: int = Field(ge=0)
    missing_dependency_edges: int = Field(ge=0)
    average_dependencies: float = Field(ge=0)

    model_config = ConfigDict(from_attributes=True)


class CheckoutFailureReason(str, Enum):
    NO_AVAILABLE_TASKS = "no_available_tasks"
    TASK_NOT_FOUND = "task_not_found"
    TASK_NOT_AVAILABLE = "task_not_available"
    MAINTENANCE_MODE = "maintenance_mode"


class CheckoutOut(BaseModel):
    task: TaskOut | None = None
    reason: CheckoutFailureReason | None = None
    message: str | None = None


class RateLimitSettingsOut(BaseModel):
    requests: int
    window_seconds: int
    trusted_bypass: list[str] = Field(default_factory=list)
    trusted_proxies: list[str] = Field(default_factory=list)
    enabled: bool


class LeaseSettingsOut(BaseModel):
    duration_seconds: int


class ExecutionRoutingSettingsOut(BaseModel):
    heartbeat_freshness_seconds: int = Field(ge=1, le=86_400)
    active_poll_freshness_seconds: int = Field(ge=1, le=3_600)


class ExtensionDescriptorOut(BaseModel):
    name: str
    capabilities: list[str] = Field(default_factory=list)
    version: str | None = None
    description: str | None = None
    config: dict[str, Any] | None = None


class ExtensionSettingsOut(BaseModel):
    modules: list[str] = Field(default_factory=list)
    builtin_enabled: bool = Field(
        default=True,
        description="Whether builtin extensions are registered automatically.",
    )
    registered: list[ExtensionDescriptorOut] = Field(default_factory=list)
    contract_version: str = Field(
        default="2025.2",
        description="Version of the extension API contract exposed by the runtime.",
    )
    contract_notes: list[str] = Field(
        default_factory=list,
        description="Additional compatibility notes surfaced by the runtime.",
    )


class PlanOut(BaseModel):
    version: int
    updated_at: dt.datetime
    tasks: list[TaskOut]


class CompleteIn(BaseModel):
    notes: str | None = None


class OkResponse(BaseModel):
    ok: bool


class AgentRegistrationResponse(OkResponse):
    agent_id: str


class StatusResponse(OkResponse):
    pass


class CompleteResponse(StatusResponse):
    notes: str | None = None


class FileUploadResponse(StatusResponse):
    sha256: str
    size: int
    url: str


class HealthObservation(BaseModel):
    """Structured representation of an individual probe result."""

    name: str
    ok: bool
    critical: bool
    observed_at: dt.datetime
    duration_ms: float = Field(ge=0)
    detail: str | None = None


class HealthStatus(StatusResponse):
    """Payload describing aggregated health-check information."""

    checks: dict[str, bool] = Field(default_factory=dict)
    version: str | None = None
    started_at: dt.datetime | None = None
    uptime_seconds: float | None = Field(default=None, ge=0)
    environment: str | None = None
    commit_sha: str | None = None
    pid: int | None = Field(default=None, ge=0)
    metadata: dict[str, Any] = Field(default_factory=dict)
    observations: list[HealthObservation] = Field(default_factory=list)


class HealthEnvelopeOut(BaseModel):
    """JSON response combining liveness and readiness payloads."""

    ok: bool
    liveness: HealthStatus
    readiness: HealthStatus


class RuntimeInfoOut(BaseModel):
    """Serialized runtime metadata describing the running process."""

    started_at: dt.datetime
    uptime_seconds: float = Field(ge=0)
    pid: int = Field(ge=0)
    version: str | None = None
    environment: str | None = None
    commit_sha: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class AdminSettingsOut(BaseModel):
    """Indicator describing whether privileged endpoints are locked down."""

    configured: bool = Field(
        default=False,
        description="True when an administrative token has been configured.",
    )


class StorageInfoOut(BaseModel):
    """Information about the live file storage root."""

    root: str
    exists: bool
    writable: bool
    total_bytes: int | None = Field(default=None, ge=0)
    free_bytes: int | None = Field(default=None, ge=0)


class DatabaseSettingsOut(BaseModel):
    """Sanitised database connection details."""

    url: str
    driver: str | None = None
    configured_via_env: bool = Field(
        default=False,
        description="True when DATABASE_URL is supplied via the environment.",
    )
    engine_options: dict[str, Any] = Field(default_factory=dict)


class EnvironmentVariableOut(BaseModel):
    """Safe environment variable presented to operators."""

    name: str
    value: str
    source: Literal["environment", "derived"] = "environment"


class DiagnosticsPackageOut(BaseModel):
    """Package version and status metadata included in diagnostics payloads."""

    name: str
    installed: str | None = None
    required: str | None = None
    status: Literal["ok", "mismatch", "missing"]
    homepage: str | None = None
    summary: str | None = None


class SettingsResponse(BaseModel):
    rate_limit: RateLimitSettingsOut
    lease: LeaseSettingsOut
    execution_routing: ExecutionRoutingSettingsOut
    extensions: ExtensionSettingsOut


class ConfigurationResponse(BaseModel):
    """Composite configuration payload returned by `/api/configuration`."""

    settings: SettingsResponse
    admin: AdminSettingsOut
    storage: StorageInfoOut
    database: DatabaseSettingsOut
    runtime: RuntimeInfoOut
    environment: list[EnvironmentVariableOut] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class SystemStateOut(BaseModel):
    maintenance_mode: bool
    message: str | None = None
    updated_at: dt.datetime
    version: int


class SystemStateUpdateIn(BaseModel):
    maintenance_mode: bool
    message: str | None = None
    expected_version: int | None = Field(
        default=None,
        description="Last observed version used for optimistic concurrency",
    )


class DiagnosticsReportOut(BaseModel):
    """Aggregated diagnostics payload returned by `/api/diagnostics`."""

    python_version: str
    implementation: str
    platform: str
    executable: str
    runtime: RuntimeInfoOut
    packages: list[DiagnosticsPackageOut] = Field(default_factory=list)
    settings: SettingsResponse
    system_state: SystemStateOut | None = None
    features: dict[str, Any] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)
    generated_at: dt.datetime


class TelemetrySubsystemOut(BaseModel):
    """Runtime status for an individual observability subsystem."""

    enabled: bool
    configured: bool
    details: dict[str, Any] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)


class TelemetryReportOut(BaseModel):
    """Shape returned by `/api/observability/telemetry`."""

    generated_at: dt.datetime
    logging: TelemetrySubsystemOut
    metrics: TelemetrySubsystemOut
    tracing: TelemetrySubsystemOut
    request_id_header: str
    health_endpoints: list[str] = Field(default_factory=list)
    runtime: RuntimeInfoOut
    diagnostics: DiagnosticsReportOut | None = None


class ActivityEventOut(BaseModel):
    """Serialized activity event captured by the builtin audit feed."""

    kind: str
    occurred_at: dt.datetime
    agent_id: str | None = None
    task_id: int | str | None = None
    payload: dict[str, Any] = Field(default_factory=dict)
    request_id: str | None = None
    trace_id: str | None = None


class ActivityFeedOut(BaseModel):
    """Container for the activity feed endpoint."""

    generated_at: dt.datetime
    events: list[ActivityEventOut] = Field(default_factory=list)


class ObservabilityHealthOut(BaseModel):
    """Aggregate observability payload combining health and telemetry."""

    generated_at: dt.datetime
    liveness: HealthStatus
    readiness: HealthStatus
    telemetry: dict[str, Any]
    probes: list[HealthObservation] = Field(default_factory=list)


class ObservabilityHookOut(BaseModel):
    """Serialized observability hook registration."""

    extension: str
    description: str | None = None
    capabilities: list[str] = Field(default_factory=list)
    outputs: list[str] = Field(default_factory=list)
    active: bool
    registration: dict[str, Any] | None = None


class ObservabilityOverviewOut(BaseModel):
    """Shape returned by `/api/observability/overview`."""

    generated_at: dt.datetime
    runtime: RuntimeInfoOut
    liveness: HealthStatus
    readiness: HealthStatus
    telemetry: dict[str, Any]
    diagnostics: dict[str, Any]
    metrics_catalog: dict[str, Any]
    extensions: list[ExtensionDescriptorOut]
    observability_hooks: list[ObservabilityHookOut] = Field(default_factory=list)
    contract: dict[str, Any]
    correlation_hints: dict[str, Any] = Field(default_factory=dict)


class MetricsCatalogOut(BaseModel):
    """Shape returned by `/api/observability/metrics`."""

    generated_at: dt.datetime
    enabled: bool
    last_updated_at: dt.datetime | None = None
    status: dict[str, float] = Field(default_factory=dict)
    readiness: dict[str, float] = Field(default_factory=dict)
    dependency: dict[str, float] = Field(default_factory=dict)
    missing: dict[str, float] = Field(default_factory=dict)
    dependency_edges: float = 0.0
    average_dependencies: float = 0.0
    updated_timestamp: float = 0.0


class ExecPlanOwner(BaseModel):
    agent_id: str
    role: str | None = None
    contact: str | None = None


class ExecPlanLifecycle(BaseModel):
    created_at: dt.datetime | None = None
    updated_at: dt.datetime | None = None
    target_completion: dt.datetime | None = None


class ExecPlanLink(BaseModel):
    url: str
    format: str | None = None
    rel: str | None = None


class ExecPlanEntry(BaseModel):
    plan_id: str
    title: str
    summary: str | None = None
    status: str
    lifecycle: ExecPlanLifecycle | None = None
    owners: list[ExecPlanOwner] | None = None
    tags: list[str] | None = None
    scope: dict[str, Any] | None = None
    links: dict[str, dict[str, Any]]
    metrics: dict[str, Any] | None = None
    changelog_token: str | None = None
    extensions: list[dict[str, Any]] | None = None


class ExecPlanRegistrySource(BaseModel):
    url: str | None = None
    etag: str | None = None


class ExecPlanRegistryIndex(BaseModel):
    version: int
    registry_id: str
    generated_at: dt.datetime
    source: ExecPlanRegistrySource | None = None
    plans: list[ExecPlanEntry]
    extensions: list[dict[str, Any]] | None = None
