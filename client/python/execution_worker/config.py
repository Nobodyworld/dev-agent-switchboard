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
MAX_WORKER_CONCURRENCY = 1
MAX_OUTPUT_BYTES = 64 * 1024 * 1024
MAX_OUTPUT_SUMMARY_BYTES = 64 * 1024
MAX_EVIDENCE_RETENTION_DAYS = 3650
MAX_ARTIFACT_COUNT = 128
MAX_EVIDENCE_BYTES = 1024**4


@dataclass(frozen=True, slots=True)
class WorkerConfig:
    """Immutable local configuration that never comes from a work order."""

    base_url: str
    worker_id: str
    display_name: str
    admin_token: str = field(repr=False)
    worker_root: Path
    repositories: Mapping[str, Path]
    evidence_root: Path
    max_concurrency: int = 1
    network_policy_capability: str = "worker_restricted"
    execution_timeout_seconds: float = 120.0
    default_step_timeout_seconds: float = 60.0
    maximum_step_timeout_seconds: float = 3600.0
    output_summary_limit: int = 4096
    total_output_limit: int = MAX_OUTPUT_BYTES
    disk_limit_bytes: int = 512 * 1024 * 1024
    evidence_retention_days: int = 14
    maximum_artifact_count: int = 128
    maximum_artifact_bytes: int = 64 * 1024 * 1024
    maximum_total_evidence_bytes: int = 512 * 1024 * 1024
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

    def __post_init__(  # noqa: PLR0912, PLR0915 - security invariants are explicit
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
        if self.max_concurrency != MAX_WORKER_CONCURRENCY:
            raise ValueError("Phase 1 worker supports max_concurrency == 1 only")
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
        if not 1 <= self.evidence_retention_days <= MAX_EVIDENCE_RETENTION_DAYS:
            raise ValueError("evidence_retention_days is out of bounds")
        if not 1 <= self.maximum_artifact_count <= MAX_ARTIFACT_COUNT:
            raise ValueError("maximum_artifact_count is out of bounds")
        if not 1 <= self.maximum_artifact_bytes <= MAX_EVIDENCE_BYTES:
            raise ValueError("maximum_artifact_bytes is out of bounds")
        if not (
            self.maximum_artifact_bytes
            <= self.maximum_total_evidence_bytes
            <= MAX_EVIDENCE_BYTES
        ):
            raise ValueError("maximum_total_evidence_bytes is out of bounds")
        if not all(
            isinstance(key, str) and re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", key)
            for key in self.inherited_environment_keys
        ):
            raise ValueError("invalid inherited environment key")
        if not all(
            isinstance(pattern, str) and pattern
            for pattern in (*self.redacted_key_patterns, *self.redacted_value_patterns)
        ):
            raise ValueError("invalid redaction pattern")

        worker_root = self.worker_root.expanduser()
        if not worker_root.is_absolute():
            raise ValueError("worker_root must be an absolute path")
        evidence_root = self.evidence_root.expanduser()
        if not evidence_root.is_absolute():
            raise ValueError("evidence_root must be an absolute path")
        if evidence_root == worker_root:
            raise ValueError("evidence_root must be separate from worker_root")

        normalized: dict[str, Path] = {}
        for repository_name, repository_path in self.repositories.items():
            if not isinstance(repository_name, str) or not _is_valid_repository_name(
                repository_name
            ):
                raise ValueError(
                    f"invalid repository full name in registry: {repository_name}"
                )
            if not isinstance(repository_path, Path):
                raise ValueError(f"repository path must be a path: {repository_name}")
            path = repository_path.expanduser()
            if not path.is_absolute():
                raise ValueError(f"repository path must be absolute: {repository_name}")
            if path == worker_root:
                raise ValueError("canonical repository path must not equal worker_root")
            if path == evidence_root:
                raise ValueError(
                    "canonical repository path must not equal evidence_root"
                )
            normalized[repository_name] = path

        if not normalized:
            raise ValueError("at least one repository must be configured")

        object.__setattr__(self, "worker_root", worker_root)
        object.__setattr__(self, "evidence_root", evidence_root)
        object.__setattr__(self, "repositories", MappingProxyType(normalized))

    @classmethod
    def from_mapping(cls, payload: Mapping[str, Any]) -> WorkerConfig:
        """Build configuration from an operator-owned decoded JSON document."""

        if not isinstance(payload, Mapping):
            raise ValueError("worker configuration must be a mapping")
        repositories = payload.get("repositories")
        if not isinstance(repositories, Mapping) or not repositories:
            raise ValueError("repositories must be a mapping")

        def required_text(name: str) -> str:
            value = payload.get(name)
            if not isinstance(value, str):
                raise ValueError(f"{name} must be a string")
            return value

        def optional_text(name: str, default: str) -> str:
            value = payload.get(name, default)
            if not isinstance(value, str):
                raise ValueError(f"{name} must be a string")
            return value

        def positive_number(name: str, default: float) -> float:
            value = payload.get(name, default)
            if not isinstance(value, (int, float)) or isinstance(value, bool):
                raise ValueError(f"{name} must be numeric")
            return float(value)

        def positive_integer(name: str, default: int) -> int:
            value = payload.get(name, default)
            if not isinstance(value, int) or isinstance(value, bool):
                raise ValueError(f"{name} must be an integer")
            return value

        def string_array(name: str, default: tuple[str, ...]) -> tuple[str, ...]:
            if name not in payload:
                return default
            value = payload[name]
            if not isinstance(value, list) or not all(
                isinstance(item, str) for item in value
            ):
                raise ValueError(f"{name} must be an array of strings")
            return tuple(value)

        worker_root = payload.get("worker_root")
        if not isinstance(worker_root, str):
            raise ValueError("worker_root must be a string")
        evidence_root = payload.get("evidence_root")
        if not isinstance(evidence_root, str):
            raise ValueError("evidence_root must be a string")
        normalized_repositories: dict[str, Path] = {}
        for name, path in repositories.items():
            if not isinstance(name, str) or not isinstance(path, str):
                raise ValueError("repositories must map strings to strings")
            normalized_repositories[name] = Path(path)

        return cls(
            base_url=required_text("base_url"),
            worker_id=required_text("worker_id"),
            display_name=required_text("display_name"),
            admin_token=os.environ.get("SWITCHBOARD_ADMIN_TOKEN", ""),
            worker_root=Path(worker_root),
            repositories=normalized_repositories,
            evidence_root=Path(evidence_root),
            max_concurrency=positive_integer("max_concurrency", 1),
            network_policy_capability=optional_text(
                "network_policy_capability", "worker_restricted"
            ),
            execution_timeout_seconds=positive_number(
                "execution_timeout_seconds", 120.0
            ),
            default_step_timeout_seconds=positive_number(
                "default_step_timeout_seconds", 60.0
            ),
            maximum_step_timeout_seconds=positive_number(
                "maximum_step_timeout_seconds", 3600.0
            ),
            output_summary_limit=positive_integer("output_summary_limit", 4096),
            total_output_limit=positive_integer("total_output_limit", MAX_OUTPUT_BYTES),
            disk_limit_bytes=positive_integer("disk_limit_bytes", 512 * 1024 * 1024),
            evidence_retention_days=positive_integer("evidence_retention_days", 14),
            maximum_artifact_count=positive_integer("maximum_artifact_count", 128),
            maximum_artifact_bytes=positive_integer(
                "maximum_artifact_bytes", 64 * 1024 * 1024
            ),
            maximum_total_evidence_bytes=positive_integer(
                "maximum_total_evidence_bytes", 512 * 1024 * 1024
            ),
            inherited_environment_keys=string_array(
                "inherited_environment_keys",
                ("PATH", "HOME", "USERPROFILE", "SYSTEMROOT", "TEMP", "TMP"),
            ),
            redacted_key_patterns=string_array(
                "redacted_key_patterns", ("TOKEN", "SECRET", "PASSWORD", "KEY")
            ),
            redacted_value_patterns=string_array("redacted_value_patterns", ()),
            poll_interval_seconds=positive_number("poll_interval_seconds", 5.0),
            heartbeat_interval_seconds=positive_number(
                "heartbeat_interval_seconds", 15.0
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
