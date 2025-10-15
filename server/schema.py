
from pydantic import BaseModel, Field
from typing import List, Optional

class AgentIn(BaseModel):
    agent_name: str = Field(..., description="Human-readable or unique agent ID")

class TaskIn(BaseModel):
    title: str
    description: str = ""
    depends_on: List[int] = []

class TaskOut(BaseModel):
    id: int
    title: str
    description: str
    status: str
    depends_on: List[int] = []
    class Config:
        from_attributes = True

class CheckoutOut(BaseModel):
    task: Optional[TaskOut] = None
    reason: Optional[str] = None

class PlanOut(BaseModel):
    version: int
    tasks: List[TaskOut]

class CompleteIn(BaseModel):
    notes: str = ""
