from __future__ import annotations

from dataclasses import dataclass


class ApplicationError(RuntimeError):
    """Base class for application-layer exceptions."""


@dataclass(slots=True)
class MissingDependenciesError(ApplicationError):
    """Raised when requested dependencies are missing."""

    missing_ids: tuple[int, ...]


class TaskNotFoundError(ApplicationError):
    """Raised when a task cannot be located for the requested operation."""


class SelfDependencyError(ApplicationError):
    """Raised when a task attempts to depend on itself."""


@dataclass(slots=True)
class SystemStateConflictError(ApplicationError):
    """Raised when attempting to update system state with a stale version."""

    expected_version: int | None
    actual_version: int | None
