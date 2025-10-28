"""Shared utilities for Switchboard FastAPI routers."""
from __future__ import annotations

import json
from collections.abc import Sequence
from typing import Any

from server.domain import SystemState, TaskRecord
from server.schema import SystemStateOut, TaskOut


def serialize_model(model: Any) -> dict[str, Any]:
    """Return a dictionary representation for both Pydantic v1 and v2 models."""

    if hasattr(model, "model_dump"):
        return model.model_dump(mode="json")  # type: ignore[no-any-return]
    if hasattr(model, "json"):
        return json.loads(model.json())  # type: ignore[no-any-return]
    return model.dict()  # type: ignore[no-any-return]


def task_record_to_out(task: TaskRecord) -> TaskOut:
    """Convert a domain task record into the public schema."""

    return TaskOut(
        id=task.id,
        title=task.title,
        description=task.description,
        status=task.status,
        completed_notes=task.completed_notes,
        depends_on=list(task.depends_on),
    )


def records_to_out(tasks: Sequence[TaskRecord]) -> list[TaskOut]:
    """Serialize a sequence of task records."""

    return [task_record_to_out(task) for task in tasks]


def system_state_to_out(state: SystemState) -> SystemStateOut:
    """Serialize a system state domain object."""

    return SystemStateOut(
        maintenance_mode=state.maintenance_mode,
        message=state.message,
        updated_at=state.updated_at,
        version=state.version,
    )

