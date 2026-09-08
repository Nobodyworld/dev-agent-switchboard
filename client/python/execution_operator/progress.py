"""Bounded optional presentation of facts observed by the existing lifecycle."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Literal, get_args

from server.execution.enums import ExecutionRunStatus

ProgressKind = Literal[
    "preflight_started",
    "preflight_passed",
    "runtime_created",
    "server_started",
    "server_ready",
    "worker_started",
    "worker_ready",
    "approval_requested",
    "approval_accepted",
    "approval_denied",
    "work_order_created",
    "work_order_approved",
    "work_order_queued",
    "run_observed",
    "evidence_verification_started",
    "evidence_verified",
    "shutdown_started",
    "cleanup_verified",
    "completed",
    "failed",
]
ProgressPhase = Literal["fresh", "reuse"]
MAX_PROGRESS_EVENTS = 64
_KINDS = frozenset(get_args(ProgressKind))
_PHASE_KINDS = frozenset(
    {
        "approval_requested",
        "approval_accepted",
        "approval_denied",
        "work_order_created",
        "work_order_approved",
        "work_order_queued",
        "run_observed",
        "evidence_verification_started",
        "evidence_verified",
    }
)


@dataclass(frozen=True, slots=True)
class ProgressEvent:
    """A closed, fixed-size observation, never execution evidence or approval."""

    sequence: int
    event: ProgressKind
    phase: ProgressPhase | None = None
    run_status: ExecutionRunStatus | None = None

    def __post_init__(self) -> None:
        if (
            type(self.sequence) is not int
            or not 1 <= self.sequence <= MAX_PROGRESS_EVENTS
            or self.event not in _KINDS
            or self.phase not in {None, "fresh", "reuse"}
            or (self.event in _PHASE_KINDS) != (self.phase is not None)
            or (self.event == "run_observed") != (self.run_status is not None)
            or (
                self.run_status is not None
                and not isinstance(self.run_status, ExecutionRunStatus)
            )
        ):
            raise ValueError("progress_event_invalid")

    def as_dict(self) -> dict[str, object]:
        """Return only the fixed versioned shape; no caller or API text."""

        return {
            "schema_version": 1,
            "sequence": self.sequence,
            "event": self.event,
            "phase": self.phase,
            "run_status": (
                self.run_status.value if self.run_status is not None else None
            ),
        }


ProgressObserver = Callable[[ProgressEvent], None]


class ProgressPublisher:
    """Deduplicate and cap best-effort observation without granting authority."""

    def __init__(self, observer: ProgressObserver | None = None) -> None:
        self._observer = observer
        self._seen: set[
            tuple[ProgressKind, ProgressPhase | None, ExecutionRunStatus | None]
        ] = set()

    def emit(
        self,
        event: ProgressKind,
        *,
        phase: ProgressPhase | None = None,
        run_status: ExecutionRunStatus | None = None,
    ) -> None:
        key = event, phase, run_status
        if (
            self._observer is None
            or key in self._seen
            or len(self._seen) >= MAX_PROGRESS_EVENTS
        ):
            return
        observation = ProgressEvent(len(self._seen) + 1, event, phase, run_status)
        self._seen.add(key)
        try:
            self._observer(observation)
        except (Exception, KeyboardInterrupt, SystemExit):
            # Presentation cannot interrupt owned cleanup or the approval path.
            # Disable a broken observer once; do not retry it or expose its error.
            self._observer = None


__all__ = ["MAX_PROGRESS_EVENTS", "ProgressEvent", "ProgressObserver"]
