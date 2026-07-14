"""Enumerated state and policy values for the execution control plane."""

from __future__ import annotations

from enum import Enum


class WorkOrderStatus(str, Enum):
    """Lifecycle states for a persisted execution work order."""

    PENDING_APPROVAL = "pending_approval"
    APPROVED = "approved"
    QUEUED = "queued"
    ASSIGNED = "assigned"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    TIMED_OUT = "timed_out"
    CANCELLED = "cancelled"
    REJECTED = "rejected"
    EXPIRED = "expired"


class ExecutionRunStatus(str, Enum):
    """Lifecycle states for one execution attempt."""

    QUEUED = "queued"
    ASSIGNED = "assigned"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    TIMED_OUT = "timed_out"
    CANCELLED = "cancelled"


class WorkerStatus(str, Enum):
    """Availability state declared for a pull-based worker."""

    ONLINE = "online"
    BUSY = "busy"
    DRAINING = "draining"
    OFFLINE = "offline"


class ApprovalPolicy(str, Enum):
    """Approval policies accepted in Phase 1."""

    EXPLICIT = "explicit"


class NetworkPolicy(str, Enum):
    """Network levels a Phase 1 worker may advertise."""

    DISABLED = "disabled"
    WORKER_RESTRICTED = "worker_restricted"


class RepositoryWritePolicy(str, Enum):
    """Repository-write posture for an execution request."""

    READ_ONLY = "read_only"


WORK_ORDER_TERMINAL_STATUSES = frozenset(
    {
        WorkOrderStatus.SUCCEEDED,
        WorkOrderStatus.FAILED,
        WorkOrderStatus.TIMED_OUT,
        WorkOrderStatus.CANCELLED,
        WorkOrderStatus.REJECTED,
        WorkOrderStatus.EXPIRED,
    }
)

RUN_TERMINAL_STATUSES = frozenset(
    {
        ExecutionRunStatus.SUCCEEDED,
        ExecutionRunStatus.FAILED,
        ExecutionRunStatus.TIMED_OUT,
        ExecutionRunStatus.CANCELLED,
    }
)


def is_terminal_work_order(status: WorkOrderStatus) -> bool:
    """Return whether a work-order state is immutable."""

    return status in WORK_ORDER_TERMINAL_STATUSES


def is_terminal_run(status: ExecutionRunStatus) -> bool:
    """Return whether an execution-run state is immutable."""

    return status in RUN_TERMINAL_STATUSES
