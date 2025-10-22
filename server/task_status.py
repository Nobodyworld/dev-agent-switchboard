"""Enumerations and helpers describing Switchboard task lifecycle states."""

from __future__ import annotations

from enum import Enum

__all__ = [
    "TASK_STATUS_VALUES",
    "TaskStatus",
    "is_valid_task_status",
    "normalize_task_status",
]


class TaskStatus(str, Enum):
    """Canonical lifecycle states for tracked Switchboard tasks."""

    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"


TASK_STATUS_VALUES: set[str] = {status.value for status in TaskStatus}


def is_valid_task_status(value: str | TaskStatus | None) -> bool:
    """Return ``True`` if ``value`` is a recognised :class:`TaskStatus`."""

    if value is None:
        return False
    if isinstance(value, TaskStatus):
        return True
    return value in TASK_STATUS_VALUES


def normalize_task_status(value: str | TaskStatus | None) -> TaskStatus | None:
    """Coerce ``value`` into a :class:`TaskStatus` when possible.

    Raises:
        ValueError: if the provided value does not map to a known status.
    """

    if value is None:
        return None
    if isinstance(value, TaskStatus):
        return value
    try:
        return TaskStatus(value)
    except ValueError as exc:  # pragma: no cover - defensive conversion guard
        raise ValueError(f"Unknown task status: {value!r}") from exc
