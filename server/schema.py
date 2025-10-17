from enum import Enum
import datetime as dt
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class TaskStatus(str, Enum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"


class AgentIn(BaseModel):
    agent_name: str = Field(..., description="Human-readable or unique agent ID")


class TaskIn(BaseModel):
    title: str
    description: str = ""
    depends_on: List[int] = Field(default_factory=list)


class TaskUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    status: Optional[TaskStatus] = None
    depends_on: Optional[List[int]] = Field(default=None)


class TaskOut(BaseModel):
    id: int
    title: str
    description: str
    status: TaskStatus
    completed_notes: Optional[str] = None
    depends_on: List[int] = Field(default_factory=list)

    class Config:
        from_attributes = True


class CheckoutFailureReason(str, Enum):
    NO_AVAILABLE_TASKS = "no_available_tasks"
    TASK_NOT_FOUND = "task_not_found"
    TASK_NOT_AVAILABLE = "task_not_available"


class CheckoutOut(BaseModel):
    task: Optional[TaskOut] = None
    reason: Optional[CheckoutFailureReason] = None


class PlanOut(BaseModel):
    version: int
    updated_at: dt.datetime
    tasks: List[TaskOut]


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
    owners: Optional[List[ExecPlanOwner]] = None
    tags: Optional[List[str]] = None
    scope: Optional[Dict[str, Any]] = None
    links: Dict[str, Dict[str, Any]]
    metrics: Optional[Dict[str, Any]] = None
    changelog_token: Optional[str] = None
    extensions: Optional[List[Dict[str, Any]]] = None


class ExecPlanRegistrySource(BaseModel):
    url: Optional[str] = None
    etag: Optional[str] = None


class ExecPlanRegistryIndex(BaseModel):
    version: int
    registry_id: str
    generated_at: dt.datetime
    source: Optional[ExecPlanRegistrySource] = None
    plans: List[ExecPlanEntry]
    extensions: Optional[List[Dict[str, Any]]] = None
