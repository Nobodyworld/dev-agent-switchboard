"""Pydantic models for the Switchboard API surface."""

import datetime as dt
from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from .task_status import TaskStatus

__all__ = [
    "AgentIn",
    "AgentRegistrationResponse",
    "CheckoutFailureReason",
    "CheckoutOut",
    "CompleteIn",
    "CompleteResponse",
    "DiagnosticsPackageOut",
    "DiagnosticsReportOut",
    "ExecPlanEntry",
    "ExecPlanLifecycle",
    "ExecPlanOwner",
    "ExecPlanRegistryIndex",
    "ExecPlanRegistrySource",
    "ExtensionDescriptorOut",
    "ExtensionSettingsOut",
    "FileUploadResponse",
    "HealthStatus",
    "LeaseSettingsOut",
    "OkResponse",
    "PlanOut",
    "RateLimitSettingsOut",
    "RuntimeInfoOut",
    "SettingsResponse",
    "StatusResponse",
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


class TaskOut(BaseModel):
    id: int
    title: str
    description: str
    status: TaskStatus
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


class RuntimeInfoOut(BaseModel):
    """Serialized runtime metadata describing the running process."""

    started_at: dt.datetime
    uptime_seconds: float = Field(ge=0)
    pid: int = Field(ge=0)
    version: str | None = None
    environment: str | None = None
    commit_sha: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


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
    extensions: ExtensionSettingsOut


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
