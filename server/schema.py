
from enum import Enum
from typing import List, Optional

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

class TaskOut(BaseModel):
    id: int
    title: str
    description: str
    status: TaskStatus
    depends_on: List[int] = Field(default_factory=list)

    class Config:
        from_attributes = True


class CheckoutFailureReason(str, Enum):
    NO_AVAILABLE_TASKS = "no_available_tasks"

class CheckoutOut(BaseModel):
    task: Optional[TaskOut] = None
    reason: Optional[CheckoutFailureReason] = None

class PlanOut(BaseModel):
    version: int
    tasks: List[TaskOut]

class CompleteIn(BaseModel):
    notes: str = ""


class OkResponse(BaseModel):
    ok: bool


class AgentRegistrationResponse(OkResponse):
    agent_id: str


class StatusResponse(OkResponse):
    pass


class CompleteResponse(StatusResponse):
    notes: str


class FileUploadResponse(StatusResponse):
    sha256: str
    size: int
    url: str
