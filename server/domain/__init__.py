"""Domain layer primitives for Switchboard."""

from .entities import Agent, LeaseRecord, PlanVersionSnapshot, TaskRecord
from .outcomes import CheckoutResult, CompletionResult, HeartbeatResult
from .policies import LeasePolicy, TaskAvailabilityPolicy

__all__ = [
    "Agent",
    "LeaseRecord",
    "PlanVersionSnapshot",
    "TaskRecord",
    "CheckoutResult",
    "CompletionResult",
    "HeartbeatResult",
    "LeasePolicy",
    "TaskAvailabilityPolicy",
]
