"""Service orchestrating reads and writes of global system state."""

from __future__ import annotations

from dataclasses import dataclass

from server.application.exceptions import SystemStateConflictError
from server.domain import SystemState
from server.domain.repositories import SystemStateRepository


@dataclass(slots=True)
class SystemStateUpdate:
    """User-supplied values when mutating system state."""

    maintenance_mode: bool
    message: str | None
    expected_version: int | None


class SystemStateService:
    """Coordinate persistence and validation for global system state."""

    def __init__(self, *, repository: SystemStateRepository) -> None:
        self._repository = repository

    async def get_state(self) -> SystemState:
        """Return the current persisted system state."""

        return await self._repository.get_state()

    async def update_state(self, update: SystemStateUpdate) -> SystemState:
        """Persist the provided state, enforcing optimistic concurrency."""

        normalized_message = self._normalize_message(update.message)
        try:
            return await self._repository.update_state(
                maintenance_mode=update.maintenance_mode,
                message=normalized_message,
                expected_version=update.expected_version,
            )
        except Exception as exc:  # pragma: no cover - defensive catch refined below
            from server.infrastructure.repositories import (
                SystemStateConcurrencyError,
            )

            if isinstance(exc, SystemStateConcurrencyError):
                raise SystemStateConflictError(
                    expected_version=update.expected_version,
                    actual_version=exc.actual,
                ) from exc
            raise

    def _normalize_message(self, message: str | None) -> str | None:
        if message is None:
            return None
        normalized = message.strip()
        return normalized or None
