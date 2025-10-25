"""Domain layer primitives for Switchboard."""

from .entities import Agent, LeaseRecord, PlanVersionSnapshot, SystemState, TaskRecord
from .outcomes import CheckoutResult, CompletionResult, HeartbeatResult
from .policies import LeasePolicy, TaskAvailabilityPolicy

__all__ = [
    "Agent",
    "CheckoutResult",
    "CompletionResult",
    "HeartbeatResult",
    "LeasePolicy",
    "LeaseRecord",
    "PlanVersionSnapshot",
    "SystemState",
    "TaskAvailabilityPolicy",
    "TaskRecord",
]
