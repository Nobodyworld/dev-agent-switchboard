"""Explicit lifecycle transition policy for execution records."""

from __future__ import annotations

from .enums import ExecutionRunStatus, WorkOrderStatus

WORK_ORDER_TRANSITIONS: dict[WorkOrderStatus, frozenset[WorkOrderStatus]] = {
    WorkOrderStatus.PENDING_APPROVAL: frozenset(
        {
            WorkOrderStatus.APPROVED,
            WorkOrderStatus.QUEUED,
            WorkOrderStatus.REJECTED,
            WorkOrderStatus.CANCELLED,
        }
    ),
    WorkOrderStatus.APPROVED: frozenset(
        {
            WorkOrderStatus.QUEUED,
            WorkOrderStatus.CANCELLED,
            WorkOrderStatus.EXPIRED,
        }
    ),
    WorkOrderStatus.QUEUED: frozenset(
        {
            WorkOrderStatus.ASSIGNED,
            WorkOrderStatus.CANCELLED,
            WorkOrderStatus.EXPIRED,
        }
    ),
    WorkOrderStatus.ASSIGNED: frozenset(
        {
            WorkOrderStatus.RUNNING,
            WorkOrderStatus.QUEUED,
            WorkOrderStatus.SUCCEEDED,
            WorkOrderStatus.FAILED,
            WorkOrderStatus.TIMED_OUT,
            WorkOrderStatus.CANCELLED,
        }
    ),
    WorkOrderStatus.RUNNING: frozenset(
        {
            WorkOrderStatus.SUCCEEDED,
            WorkOrderStatus.FAILED,
            WorkOrderStatus.TIMED_OUT,
            WorkOrderStatus.CANCELLED,
            WorkOrderStatus.QUEUED,
        }
    ),
    WorkOrderStatus.SUCCEEDED: frozenset(),
    WorkOrderStatus.FAILED: frozenset(),
    WorkOrderStatus.TIMED_OUT: frozenset(),
    WorkOrderStatus.CANCELLED: frozenset(),
    WorkOrderStatus.REJECTED: frozenset(),
    WorkOrderStatus.EXPIRED: frozenset(),
}

RUN_TRANSITIONS: dict[ExecutionRunStatus, frozenset[ExecutionRunStatus]] = {
    ExecutionRunStatus.QUEUED: frozenset({ExecutionRunStatus.ASSIGNED}),
    ExecutionRunStatus.ASSIGNED: frozenset(
        {
            ExecutionRunStatus.RUNNING,
            ExecutionRunStatus.SUCCEEDED,
            ExecutionRunStatus.FAILED,
            ExecutionRunStatus.TIMED_OUT,
            ExecutionRunStatus.CANCELLED,
        }
    ),
    ExecutionRunStatus.RUNNING: frozenset(
        {
            ExecutionRunStatus.SUCCEEDED,
            ExecutionRunStatus.FAILED,
            ExecutionRunStatus.TIMED_OUT,
            ExecutionRunStatus.CANCELLED,
        }
    ),
    ExecutionRunStatus.SUCCEEDED: frozenset(),
    ExecutionRunStatus.FAILED: frozenset(),
    ExecutionRunStatus.TIMED_OUT: frozenset(),
    ExecutionRunStatus.CANCELLED: frozenset(),
}


def allows_work_order_transition(
    current: WorkOrderStatus, target: WorkOrderStatus
) -> bool:
    """Return whether the explicit work-order transition is legal."""

    return target in WORK_ORDER_TRANSITIONS[current]


def allows_run_transition(
    current: ExecutionRunStatus, target: ExecutionRunStatus
) -> bool:
    """Return whether the explicit execution-run transition is legal."""

    return target in RUN_TRANSITIONS[current]
