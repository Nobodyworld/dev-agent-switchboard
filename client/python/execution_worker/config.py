"""Validated operator-controlled configuration for the local execution worker."""

from __future__ import annotations

import os
import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from types import MappingProxyType
from typing import Any

_REPOSITORY_NAME = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
MAX_WORKER_CONCURRENCY = 64
MAX_OUTPUT_BYTES = 64 * 1024 * 1024
MAX_OUTPUT_SUMMARY_BYTES = 64 * 1024


@dataclass(frozen=True, slots=True)
class WorkerConfig:
    """Immutable local configuration that never comes from a work order."""

    base_url: str
    worker_id: str
    display_name: str
    admin_token: str = field(repr=False)
    worker_root: Path
    repositories: Mapping[str, Path]
    max_concurrency: int = 1
    network_policy_capability: str = "worker_restricted"
    execution_timeout_seconds: float = 120.0
    default_step_timeout_seconds: float = 60.0
    maximum_step_timeout_seconds: float = 3600.0
    output_summary_limit: int = 4096
    total_output_limit: int = MAX_OUTPUT_BYTES
    disk_limit_bytes: int = 512 * 1024 * 1024
    inherited_environment_keys: tuple[str, ...] = (
        "PATH",
        "HOME",
        "USERPROFILE",
        "SYSTEMROOT",
        "TEMP",
        "TMP",
    )
    redacted_key_patterns: tuple[str, ...] = ("TOKEN", "SECRET", "PASSWORD", "KEY")
    redacted_value_patterns: tuple[str, ...] = ()
    poll_interval_seconds: float = 5.0
    heartbeat_interval_seconds: float = 15.0

    def __post_init__(  # noqa: PLR0912 - validation enumerates security invariants
        self,
    ) -> None:
        if not self.base_url.strip():
            raise ValueError("base_url must not be empty")
        if not self.worker_id.strip():
            raise ValueError("worker_id must not be empty")
        if not self.display_name.strip():
            raise ValueError("display_name must not be empty")
        if not self.admin_token.strip():
            raise ValueError("admin_token must not be empty")
        if not 1 <= self.max_concurrency <= MAX_WORKER_CONCURRENCY:
            raise ValueError(
                f"max_concurrency must be between 1 and {MAX_WORKER_CONCURRENCY}"
            )
        if self.poll_interval_seconds <= 0:
            raise ValueError("poll_interval_seconds must be positive")
        if self.heartbeat_interval_seconds <= 0:
            raise ValueError("heartbeat_interval_seconds must be positive")
        if self.network_policy_capability not in {"disabled", "worker_restricted"}:
            raise ValueError("unsupported network policy capability")
        if (
            not 0
            < self.default_step_timeout_seconds
            <= self.maximum_step_timeout_seconds
        ):
            raise ValueError("invalid step timeout controls")
        if self.execution_timeout_seconds <= 0:
            raise ValueError("execution_timeout_seconds must be positive")
        if not 1 <= self.output_summary_limit <= MAX_OUTPUT_SUMMARY_BYTES:
            raise ValueError("output_summary_limit is out of bounds")
        if not 1 <= self.total_output_limit <= MAX_OUTPUT_BYTES:
            raise ValueError("total_output_limit is out of bounds")
        if self.disk_limit_bytes < self.total_output_limit:
            raise ValueError("disk_limit_bytes must cover total output")
        if not all(
            re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", key)
            for key in self.inherited_environment_keys
        ):
            raise ValueError("invalid inherited environment key")

        worker_root = self.worker_root.expanduser()
        if not worker_root.is_absolute():
            raise ValueError("worker_root must be an absolute path")

        normalized: dict[str, Path] = {}
        for repository_name, repository_path in self.repositories.items():
            if not _is_valid_repository_name(repository_name):
                raise ValueError(
                    f"invalid repository full name in registry: {repository_name}"
                )
            path = Path(repository_path).expanduser()
            if not path.is_absolute():
                raise ValueError(f"repository path must be absolute: {repository_name}")
            if path == worker_root:
                raise ValueError("canonical repository path must not equal worker_root")
            normalized[repository_name] = path

        if not normalized:
            raise ValueError("at least one repository must be configured")

        object.__setattr__(self, "worker_root", worker_root)
        object.__setattr__(self, "repositories", MappingProxyType(normalized))

    @classmethod
    def from_mapping(cls, payload: Mapping[str, Any]) -> WorkerConfig:
        """Build configuration from an operator-owned decoded JSON document."""

        repositories = payload.get("repositories")
        if not isinstance(repositories, Mapping):
            raise ValueError("repositories must be a mapping")

        return cls(
            base_url=str(payload.get("base_url", "")),
            worker_id=str(payload.get("worker_id", "")),
            display_name=str(payload.get("display_name", "")),
            admin_token=os.environ.get("SWITCHBOARD_ADMIN_TOKEN", ""),
            worker_root=Path(str(payload.get("worker_root", ""))),
            repositories={
                str(name): Path(str(path)) for name, path in repositories.items()
            },
            max_concurrency=int(payload.get("max_concurrency", 1)),
            network_policy_capability=str(
                payload.get("network_policy_capability", "worker_restricted")
            ),
            execution_timeout_seconds=float(
                payload.get("execution_timeout_seconds", 120.0)
            ),
            default_step_timeout_seconds=float(
                payload.get("default_step_timeout_seconds", 60.0)
            ),
            maximum_step_timeout_seconds=float(
                payload.get("maximum_step_timeout_seconds", 3600.0)
            ),
            output_summary_limit=int(payload.get("output_summary_limit", 4096)),
            total_output_limit=int(payload.get("total_output_limit", MAX_OUTPUT_BYTES)),
            disk_limit_bytes=int(payload.get("disk_limit_bytes", 512 * 1024 * 1024)),
            inherited_environment_keys=tuple(
                payload.get(
                    "inherited_environment_keys",
                    ("PATH", "HOME", "USERPROFILE", "SYSTEMROOT", "TEMP", "TMP"),
                )
            ),
            redacted_key_patterns=tuple(
                payload.get(
                    "redacted_key_patterns", ("TOKEN", "SECRET", "PASSWORD", "KEY")
                )
            ),
            redacted_value_patterns=tuple(payload.get("redacted_value_patterns", ())),
            poll_interval_seconds=float(payload.get("poll_interval_seconds", 5.0)),
            heartbeat_interval_seconds=float(
                payload.get("heartbeat_interval_seconds", 15.0)
            ),
        )

    def repository_path(self, repository_full_name: str) -> Path:
        """Resolve only an operator-registered logical repository identity."""

        try:
            return self.repositories[repository_full_name]
        except KeyError as error:
            raise KeyError(
                f"repository is not registered: {repository_full_name}"
            ) from error


def _is_valid_repository_name(repository_name: str) -> bool:
    if not _REPOSITORY_NAME.fullmatch(repository_name):
        return False
    owner, name = repository_name.split("/", maxsplit=1)
    return owner not in {".", ".."} and name not in {".", ".."}


__all__ = [
    "MAX_OUTPUT_BYTES",
    "MAX_OUTPUT_SUMMARY_BYTES",
    "MAX_WORKER_CONCURRENCY",
    "WorkerConfig",
]
