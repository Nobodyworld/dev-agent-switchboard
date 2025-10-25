"""Pydantic models for the Switchboard API surface."""

import datetime as dt
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field

from .task_status import TaskStatus

__all__ = [
    "AgentIn",
    "AgentRegistrationResponse",
    "CheckoutFailureReason",
    "CheckoutOut",
    "CompleteIn",
    "CompleteResponse",
    "ExtensionDescriptorOut",
    "ExtensionSettingsOut",
    "ExecPlanEntry",
    "ExecPlanLifecycle",
    "ExecPlanOwner",
    "ExecPlanRegistryIndex",
    "ExecPlanRegistrySource",
    "FileUploadResponse",
    "HealthStatus",
    "LeaseSettingsOut",
    "OkResponse",
    "PlanOut",
    "RateLimitSettingsOut",
    "SettingsResponse",
    "StatusResponse",
    "SystemStateOut",
    "SystemStateUpdateIn",
    "TaskIn",
    "TaskOut",
    "TaskStatus",
    "TaskUpdate",
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
    title: Optional[str] = Field(
        default=None,
        max_length=MAX_TITLE_LENGTH,
        description="Updated task title",
    )
    description: Optional[str] = Field(
        default=None,
        max_length=MAX_DESCRIPTION_LENGTH,
        description="Updated task description",
    )
    status: Optional[TaskStatus] = None
    depends_on: Optional[list[int]] = Field(default=None)


class TaskOut(BaseModel):
    id: int
    title: str
    description: str
    status: TaskStatus
    completed_notes: Optional[str] = None
    depends_on: list[int] = Field(default_factory=list)

    class Config:
        from_attributes = True


class CheckoutFailureReason(str, Enum):
    NO_AVAILABLE_TASKS = "no_available_tasks"
    TASK_NOT_FOUND = "task_not_found"
    TASK_NOT_AVAILABLE = "task_not_available"
    MAINTENANCE_MODE = "maintenance_mode"


class CheckoutOut(BaseModel):
    task: Optional[TaskOut] = None
    reason: Optional[CheckoutFailureReason] = None
    message: Optional[str] = None


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
    version: Optional[str] = None
    description: Optional[str] = None
    config: Optional[dict[str, Any]] = None


class ExtensionSettingsOut(BaseModel):
    modules: list[str] = Field(default_factory=list)
    builtin_enabled: bool = Field(
        default=True,
        description="Whether builtin extensions are registered automatically.",
    )
    registered: list[ExtensionDescriptorOut] = Field(default_factory=list)


class PlanOut(BaseModel):
    version: int
    updated_at: dt.datetime
    tasks: list[TaskOut]


class CompleteIn(BaseModel):
    notes: Optional[str] = None


class OkResponse(BaseModel):
    ok: bool


class AgentRegistrationResponse(OkResponse):
    agent_id: str


class StatusResponse(OkResponse):
    pass


class CompleteResponse(StatusResponse):
    notes: Optional[str] = None


class FileUploadResponse(StatusResponse):
    sha256: str
    size: int
    url: str


class HealthStatus(StatusResponse):
    """Payload describing aggregated health-check information."""

    checks: dict[str, bool] = Field(default_factory=dict)
    version: Optional[str] = None
    started_at: Optional[dt.datetime] = None
    uptime_seconds: Optional[float] = Field(default=None, ge=0)
    environment: Optional[str] = None
    commit_sha: Optional[str] = None
    pid: Optional[int] = Field(default=None, ge=0)
    metadata: dict[str, Any] = Field(default_factory=dict)


class SettingsResponse(BaseModel):
    rate_limit: RateLimitSettingsOut
    lease: LeaseSettingsOut
    extensions: ExtensionSettingsOut


class SystemStateOut(BaseModel):
    maintenance_mode: bool
    message: Optional[str] = None
    updated_at: dt.datetime
    version: int


class SystemStateUpdateIn(BaseModel):
    maintenance_mode: bool
    message: Optional[str] = None
    expected_version: Optional[int] = Field(
        default=None,
        description="Last observed version used for optimistic concurrency",
    )


class ExecPlanOwner(BaseModel):
    agent_id: str
    role: Optional[str] = None
    contact: Optional[str] = None


class ExecPlanLifecycle(BaseModel):
    created_at: Optional[dt.datetime] = None
    updated_at: Optional[dt.datetime] = None
    target_completion: Optional[dt.datetime] = None


class ExecPlanLink(BaseModel):
    url: str
    format: Optional[str] = None
    rel: Optional[str] = None


class ExecPlanEntry(BaseModel):
    plan_id: str
    title: str
    summary: Optional[str] = None
    status: str
    lifecycle: Optional[ExecPlanLifecycle] = None
    owners: Optional[list[ExecPlanOwner]] = None
    tags: Optional[list[str]] = None
    scope: Optional[dict[str, Any]] = None
    links: dict[str, dict[str, Any]]
    metrics: Optional[dict[str, Any]] = None
    changelog_token: Optional[str] = None
    extensions: Optional[list[dict[str, Any]]] = None


class ExecPlanRegistrySource(BaseModel):
    url: Optional[str] = None
    etag: Optional[str] = None


class ExecPlanRegistryIndex(BaseModel):
    version: int
    registry_id: str
    generated_at: dt.datetime
    source: Optional[ExecPlanRegistrySource] = None
    plans: list[ExecPlanEntry]
    extensions: Optional[list[dict[str, Any]]] = None
