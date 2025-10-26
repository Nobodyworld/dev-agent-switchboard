"""Helpers that expose runtime metadata for observability surfaces."""

from __future__ import annotations

import os
import time
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

_STARTED_AT = datetime.now(timezone.utc)
_STARTED_MONOTONIC = time.monotonic()
_EXTRA_METADATA: dict[str, Any] = {}


def _normalized_env(name: str) -> str | None:
    value = os.getenv(name)
    if value:
        value = value.strip()
    return value or None


@dataclass(frozen=True)
class RuntimeSnapshot:
    """Capture runtime metadata describing the current process."""

    started_at: datetime
    uptime_seconds: float
    pid: int
    version: str | None = None
    environment: str | None = None
    commit_sha: str | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def model_dump(self) -> dict[str, Any]:
        """Return a JSON-serialisable representation of the snapshot."""

        payload = {
            "started_at": self.started_at.isoformat(),
            "uptime_seconds": self.uptime_seconds,
            "pid": self.pid,
        }
        if self.version is not None:
            payload["version"] = self.version
        if self.environment is not None:
            payload["environment"] = self.environment
        if self.commit_sha is not None:
            payload["commit_sha"] = self.commit_sha
        if self.metadata:
            payload["metadata"] = dict(self.metadata)
        return payload


def register_runtime_metadata(**metadata: Any) -> None:
    """Register supplemental metadata to be returned in snapshots."""

    # agent-entrypoint: automation can safely attach rollout metadata surfaced via
    # the health endpoints and observability dashboards.
    _EXTRA_METADATA.update(metadata)


def get_runtime_snapshot(*, version: str | None = None) -> RuntimeSnapshot:
    """Return runtime metadata for the current process."""

    uptime_seconds = max(0.0, time.monotonic() - _STARTED_MONOTONIC)
    environment = _normalized_env("SWITCHBOARD_ENVIRONMENT")
    commit_sha = (
        _normalized_env("SWITCHBOARD_COMMIT_SHA")
        or _normalized_env("GITHUB_SHA")
        or _normalized_env("COMMIT_SHA")
    )
    return RuntimeSnapshot(
        started_at=_STARTED_AT,
        uptime_seconds=uptime_seconds,
        pid=os.getpid(),
        version=version,
        environment=environment,
        commit_sha=commit_sha,
        metadata=dict(_EXTRA_METADATA),
    )
