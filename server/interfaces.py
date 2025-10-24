"""Core data interfaces for the Switchboard orchestration router."""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from typing import Mapping

from .task_status import TaskStatus

__all__ = [
    "AgentDescriptor",
    "CheckoutOutcome",
    "CompletionOutcome",
    "HeartbeatOutcome",
    "QueueDescriptor",
    "TaskEnvelope",
    "TaskLease",
    "TaskPayload",
]


@dataclass(frozen=True, slots=True)
class AgentDescriptor:
    """Immutable description of an agent registered with Switchboard.

    Parameters
    ----------
    agent_id:
        Globally unique identifier assigned to the agent.
    label:
        Optional human-friendly label displayed in operator tooling.
    capabilities:
        Ordered sequence of declared skills used by routing heuristics.
    metadata:
        Optional metadata bag for downstream extensions.
    """

    agent_id: str
    label: str | None = None
    capabilities: tuple[str, ...] = ()
    metadata: Mapping[str, str] | None = None

    def __post_init__(self) -> None:
        """Normalize tuple-backed fields for hashable storage."""

        object.__setattr__(self, "capabilities", tuple(self.capabilities))


@dataclass(frozen=True, slots=True)
class QueueDescriptor:
    """Description of a logical work queue managed by the router.

    Parameters
    ----------
    name:
        Canonical identifier for the queue.
    kind:
        High-level category (for example, ``"task"`` or ``"workflow"``).
    metadata:
        Optional metadata bag with versioning or domain-specific hints.
    """

    name: str
    kind: str
    metadata: Mapping[str, str] | None = None

    def to_dict(self) -> dict[str, str | Mapping[str, str]]:
        """Serialize the descriptor into a JSON-friendly dictionary."""

        payload: dict[str, str | Mapping[str, str]] = {"name": self.name, "kind": self.kind}
        if self.metadata:
            payload["metadata"] = dict(self.metadata)
        return payload


@dataclass(frozen=True, slots=True)
class TaskPayload:
    """Immutable view over a task pulled from the router.

    Parameters
    ----------
    id:
        Database identifier for the task.
    title:
        Short headline describing the work item.
    description:
        Long-form description for the agent to follow.
    status:
        Current lifecycle state of the task.
    depends_on:
        Ordered collection of prerequisite task identifiers.
    metadata:
        Optional structured metadata (notes, timestamps, routing hints).
    """

    id: int
    title: str
    description: str
    status: TaskStatus
    depends_on: tuple[int, ...] = ()
    metadata: Mapping[str, object] | None = None

    def __post_init__(self) -> None:
        """Ensure tuple-backed fields retain deterministic ordering."""

        object.__setattr__(self, "depends_on", tuple(self.depends_on))

    def to_dict(self) -> dict[str, object]:
        """Convert the payload to a primitive mapping for API responses."""

        payload: dict[str, object] = {
            "id": self.id,
            "title": self.title,
            "description": self.description,
            "status": self.status,
            "depends_on": list(self.depends_on),
        }
        if self.metadata:
            payload["metadata"] = dict(self.metadata)
        return payload


@dataclass(frozen=True, slots=True)
class TaskLease:
    """Lease information representing the current lock on a task.

    Parameters
    ----------
    task_id:
        Identifier of the leased task.
    agent_id:
        Agent currently holding the lease.
    issued_at:
        Timestamp when the lease was issued.
    expires_at:
        Timestamp when the lease will expire without a heartbeat.
    """

    task_id: int
    agent_id: str
    issued_at: dt.datetime
    expires_at: dt.datetime

    def to_dict(self) -> dict[str, object]:
        """Serialize the lease into primitives suitable for JSON."""

        return {
            "task_id": self.task_id,
            "agent_id": self.agent_id,
            "issued_at": self.issued_at.isoformat(),
            "expires_at": self.expires_at.isoformat(),
        }


@dataclass(frozen=True, slots=True)
class TaskEnvelope:
    """Composite container describing a queue item and associated lease.

    Parameters
    ----------
    task:
        Task payload available to the agent.
    queue:
        Queue descriptor indicating the routing origin.
    lease:
        Active lease protecting the task, when one exists.
    """

    task: TaskPayload
    queue: QueueDescriptor
    lease: TaskLease | None = None

    def to_dict(self) -> dict[str, object]:
        """Return a JSON-ready dictionary describing the envelope."""

        payload: dict[str, object] = {
            "task": self.task.to_dict(),
            "queue": self.queue.to_dict(),
        }
        if self.lease is not None:
            payload["lease"] = self.lease.to_dict()
        return payload


@dataclass(frozen=True, slots=True)
class CheckoutOutcome:
    """Structured response describing the result of a checkout attempt.

    Parameters
    ----------
    envelope:
        Populated task envelope when checkout succeeds.
    reason:
        Machine-readable reason explaining why checkout failed.
    """

    envelope: TaskEnvelope | None
    reason: str | None = None

    def to_dict(self) -> dict[str, object | None]:
        """Serialize the outcome into a JSON-friendly shape."""

        payload: dict[str, object | None] = {"envelope": None, "reason": self.reason}
        if self.envelope is not None:
            payload["envelope"] = self.envelope.to_dict()
        return payload


@dataclass(frozen=True, slots=True)
class CompletionOutcome:
    """Result wrapper emitted when completing a task.

    Parameters
    ----------
    ok:
        Indicates whether completion succeeded.
    notes:
        Normalized completion notes stored on the task.
    envelope:
        Refreshed task envelope when completion succeeds.
    """

    ok: bool
    notes: str | None
    envelope: TaskEnvelope | None

    def to_dict(self) -> dict[str, object | None]:
        """Serialize the completion outcome for transport."""

        payload: dict[str, object | None] = {"ok": self.ok, "notes": self.notes}
        if self.envelope is not None:
            payload["envelope"] = self.envelope.to_dict()
        return payload


@dataclass(frozen=True, slots=True)
class HeartbeatOutcome:
    """Outcome describing lease extension attempts.

    Parameters
    ----------
    ok:
        Indicates whether the heartbeat was applied.
    task_id:
        Identifier of the task targeted by the heartbeat.
    """

    ok: bool
    task_id: int

    def to_dict(self) -> dict[str, object]:
        """Return primitive representation for logging or APIs."""

        return {"ok": self.ok, "task_id": self.task_id}
