"""Helpers for extension-provided observability instrumentation."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from fastapi import FastAPI

try:  # pragma: no cover - type-only import for linting clarity
    from server.observability.telemetry import TelemetryState
except Exception:  # pragma: no cover - circular import guard for runtime
    TelemetryState = Any  # type: ignore[assignment]


ObservabilityHook = Callable[
    [FastAPI, "TelemetryState"], "ObservabilityRegistration | None"
]


@dataclass(frozen=True)
class ObservabilityRegistration:
    """Metadata describing instrumentation emitted by an extension."""

    details: Mapping[str, Any] = field(default_factory=dict)
    metrics: tuple[Mapping[str, Any], ...] = ()
    traces: tuple[Mapping[str, Any], ...] = ()
    logs: tuple[Mapping[str, Any], ...] = ()
    notes: tuple[str, ...] = ()

    def as_payload(self) -> dict[str, Any]:
        """Return a serialisable payload for API responses."""

        return {
            "details": dict(self.details),
            "metrics": [dict(entry) for entry in self.metrics],
            "traces": [dict(entry) for entry in self.traces],
            "logs": [dict(entry) for entry in self.logs],
            "notes": list(self.notes),
        }


@dataclass(frozen=True)
class ObservabilitySnapshot:
    """Container describing the latest extension observability registrations."""

    generated_at: datetime
    registrations: Mapping[str, ObservabilityRegistration]

    def as_payload(self) -> dict[str, Any]:
        """Return a serialisable view of the stored registrations."""

        return {
            "generated_at": self.generated_at,
            "registrations": {
                name: registration.as_payload()
                for name, registration in self.registrations.items()
            },
        }


class _RegistrationStore:
    """In-memory store capturing per-extension observability metadata."""

    __slots__ = ("_generated_at", "_registrations")

    def __init__(self) -> None:
        self._registrations: dict[str, ObservabilityRegistration] = {}
        self._generated_at: datetime | None = None

    def reset(self) -> None:
        """Clear previously recorded registrations."""

        self._registrations.clear()
        self._generated_at = None

    def record(self, extension: str, registration: ObservabilityRegistration) -> None:
        """Record instrumentation metadata for ``extension``."""

        self._registrations[extension] = registration
        self._generated_at = datetime.now(timezone.utc)

    def snapshot(self) -> ObservabilitySnapshot:
        """Return a snapshot of the latest registrations."""

        generated_at = self._generated_at or datetime.now(timezone.utc)
        return ObservabilitySnapshot(
            generated_at=generated_at,
            registrations=dict(self._registrations),
        )


_STORE = _RegistrationStore()


def reset_observability_registrations() -> None:
    """Clear stored observability registrations."""

    _STORE.reset()


def record_observability_registration(
    extension: str, registration: ObservabilityRegistration
) -> None:
    """Persist observability metadata for ``extension``."""

    _STORE.record(extension, registration)


def get_observability_registrations() -> ObservabilitySnapshot:
    """Return a snapshot of all recorded observability registrations."""

    return _STORE.snapshot()


__all__ = [
    "ObservabilityHook",
    "ObservabilityRegistration",
    "ObservabilitySnapshot",
    "get_observability_registrations",
    "record_observability_registration",
    "reset_observability_registrations",
]
