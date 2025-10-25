"""Observability helpers exposing runtime metadata for Switchboard."""

from .runtime import (
    RuntimeSnapshot,
    get_runtime_snapshot,
    register_runtime_metadata,
)

__all__ = [
    "RuntimeSnapshot",
    "get_runtime_snapshot",
    "register_runtime_metadata",
]
