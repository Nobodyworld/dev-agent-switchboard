"""Version-controlled trusted command-manifest identities.

Executable definitions live only in reviewed source. The API and persisted manifest
snapshot expose safe metadata, while the local worker resolves fixed argv from the
same immutable name, version, and digest.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import PurePosixPath
from typing import Any

from .enums import NetworkPolicy, RepositoryWritePolicy

TRUSTED_REPOSITORIES = frozenset({"Nobodyworld/dev-agent-switchboard"})
MAX_TRUSTED_STEP_ID_LENGTH = 80
MAX_TRUSTED_STEP_OUTPUT_SUMMARY_BYTES = 64 * 1024


@dataclass(frozen=True, slots=True)
class TrustedStep:
    """One reviewed fixed-argv step that cannot be authored through the API."""

    id: str
    title: str
    argv: tuple[str, ...]
    required: bool
    timeout_seconds: int
    output_summary_limit: int = 4096
    working_directory: str = "."
    environment: tuple[tuple[str, str], ...] = ()
    capability_condition: dict[str, Any] | None = None
    diagnostic_only: bool = False

    def __post_init__(self) -> None:
        if not self.id or not self.title or len(self.id) > MAX_TRUSTED_STEP_ID_LENGTH:
            raise ValueError("trusted step identity must not be empty")
        if not self.argv or any(not item for item in self.argv):
            raise ValueError("trusted step argv must contain fixed non-empty items")
        if self.timeout_seconds <= 0:
            raise ValueError("trusted step timeout must be positive")
        if not (
            1 <= self.output_summary_limit <= MAX_TRUSTED_STEP_OUTPUT_SUMMARY_BYTES
        ):
            raise ValueError("trusted step output summary limit is out of bounds")
        working_directory = PurePosixPath(self.working_directory)
        if working_directory.is_absolute() or ".." in working_directory.parts:
            raise ValueError("trusted step working directory must remain relative")
        if self.required and self.diagnostic_only:
            raise ValueError("a required step cannot be diagnostic-only")
        keys = [key for key, _ in self.environment]
        if len(keys) != len(set(keys)) or any(
            not key or not key.replace("_", "a").isalnum() or not value
            for key, value in self.environment
        ):
            raise ValueError(
                "trusted step environment must contain unique valid values"
            )

    def digest_payload(self) -> dict[str, Any]:
        """Return every execution-relevant field for immutable digesting."""

        return {
            "argv": list(self.argv),
            "capability_condition": self.capability_condition,
            "diagnostic_only": self.diagnostic_only,
            "environment": [list(item) for item in self.environment],
            "id": self.id,
            "output_summary_limit": self.output_summary_limit,
            "required": self.required,
            "timeout_seconds": self.timeout_seconds,
            "title": self.title,
            "working_directory": self.working_directory,
        }

    def safe_metadata(self) -> dict[str, Any]:
        """Return API-safe metadata without argv, executable paths, or values."""

        metadata: dict[str, Any] = {
            "id": self.id,
            "required": self.required,
            "timeout_seconds": self.timeout_seconds,
            "output_summary_limit": self.output_summary_limit,
        }
        if self.capability_condition:
            metadata["capability_condition"] = self.capability_condition
        if self.diagnostic_only:
            metadata["diagnostic_only"] = True
        if self.environment:
            metadata["environment_keys"] = sorted(key for key, _ in self.environment)
        return metadata


@dataclass(frozen=True, slots=True)
class TrustedManifest:
    """An immutable, server-controlled manifest identity and metadata snapshot."""

    name: str
    version: str
    schema_version: int
    description: str
    registry_source: str
    required_capabilities: dict[str, Any]
    fixed_step_metadata: list[dict[str, Any]]
    environment_policy: dict[str, Any]
    network_policy: NetworkPolicy
    repository_write_policy: RepositoryWritePolicy
    timeout_seconds: int
    artifact_declarations: list[dict[str, Any]]
    allowed_parameters: frozenset[str] = frozenset()
    execution_steps: tuple[TrustedStep, ...] = ()

    def __post_init__(self) -> None:
        if self.execution_steps:
            expected_metadata = [step.safe_metadata() for step in self.execution_steps]
            if self.fixed_step_metadata != expected_metadata:
                raise ValueError(
                    "fixed_step_metadata must match safe executable-step metadata"
                )

    @property
    def digest(self) -> str:
        """Return the stable SHA-256 digest of this reviewed contract."""

        payload: dict[str, Any] = {
            "allowed_parameters": sorted(self.allowed_parameters),
            "artifact_declarations": self.artifact_declarations,
            "description": self.description,
            "environment_policy": self.environment_policy,
            "fixed_step_metadata": self.fixed_step_metadata,
            "name": self.name,
            "network_policy": self.network_policy.value,
            "registry_source": self.registry_source,
            "repository_write_policy": self.repository_write_policy.value,
            "required_capabilities": self.required_capabilities,
            "schema_version": self.schema_version,
            "timeout_seconds": self.timeout_seconds,
            "version": self.version,
        }
        # Preserve the existing Phase 1A digest for metadata-only manifests while
        # binding every executable field for worker-enabled manifest identities.
        if self.execution_steps:
            payload["execution_steps"] = [
                step.digest_payload() for step in self.execution_steps
            ]
        encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


_WORKER_SMOKE_STEPS = (
    TrustedStep(
        id="python-version",
        title="Record Python version",
        argv=("python", "--version"),
        required=True,
        timeout_seconds=60,
        output_summary_limit=4096,
    ),
    TrustedStep(
        id="git-head",
        title="Verify detached checkout commit identity",
        argv=("git", "rev-parse", "HEAD"),
        required=True,
        timeout_seconds=60,
        output_summary_limit=4096,
    ),
)


_TRUSTED_MANIFESTS = (
    TrustedManifest(
        name="validate-switchboard",
        version="1",
        schema_version=1,
        description=(
            "Read-only validation contract identity for one exact Switchboard commit. "
            "Phase 1A persists control-plane metadata only."
        ),
        registry_source="server/execution/registry.py",
        required_capabilities={
            "operating_system": ["linux", "windows"],
            "python": {"minimum": "3.11"},
            "repository_write": False,
        },
        fixed_step_metadata=[
            {"id": "python-version", "required": True, "timeout_seconds": 60},
            {
                "id": "dependency-health",
                "required": True,
                "timeout_seconds": 300,
            },
            {
                "id": "repository-verification",
                "required": True,
                "timeout_seconds": 1200,
            },
            {"id": "tests", "required": True, "timeout_seconds": 1800},
            {
                "id": "strict-browser",
                "required": True,
                "timeout_seconds": 1200,
            },
            {
                "id": "docker-build",
                "required": False,
                "timeout_seconds": 1800,
                "capability_condition": {"docker": True},
            },
        ],
        environment_policy={
            "allowed_inherited_keys": [
                "PATH",
                "HOME",
                "USERPROFILE",
                "SYSTEMROOT",
                "TEMP",
                "TMP",
            ],
            "redact_keys": [
                "SWITCHBOARD_ADMIN_TOKEN",
                "GITHUB_TOKEN",
                "GH_TOKEN",
                "OPENAI_API_KEY",
                "ANTHROPIC_API_KEY",
                "XAI_API_KEY",
            ],
        },
        network_policy=NetworkPolicy.WORKER_RESTRICTED,
        repository_write_policy=RepositoryWritePolicy.READ_ONLY,
        timeout_seconds=3600,
        artifact_declarations=[
            {"kind": "command-log", "retention_days": 14},
            {"kind": "test-report", "retention_days": 14},
            {"kind": "coverage", "retention_days": 14},
            {"kind": "browser-trace", "retention_days": 14},
        ],
    ),
    TrustedManifest(
        name="worker-smoke",
        version="1",
        schema_version=1,
        description=(
            "Harmless read-only worker smoke contract for one exact local Git commit."
        ),
        registry_source="server/execution/registry.py",
        required_capabilities={
            "operating_system": ["linux", "windows"],
            "python": {"minimum": "3.11"},
            "git_available": True,
            "repository_write": False,
        },
        fixed_step_metadata=[step.safe_metadata() for step in _WORKER_SMOKE_STEPS],
        environment_policy={
            "allowed_inherited_keys": [
                "PATH",
                "HOME",
                "USERPROFILE",
                "SYSTEMROOT",
                "TEMP",
                "TMP",
            ],
            "redact_keys": [
                "SWITCHBOARD_ADMIN_TOKEN",
                "GITHUB_TOKEN",
                "GH_TOKEN",
                "OPENAI_API_KEY",
                "ANTHROPIC_API_KEY",
                "XAI_API_KEY",
            ],
        },
        network_policy=NetworkPolicy.WORKER_RESTRICTED,
        repository_write_policy=RepositoryWritePolicy.READ_ONLY,
        timeout_seconds=120,
        artifact_declarations=[],
        execution_steps=_WORKER_SMOKE_STEPS,
    ),
)


def iter_trusted_manifests() -> tuple[TrustedManifest, ...]:
    """Return all static trusted manifest definitions."""

    return _TRUSTED_MANIFESTS


def get_trusted_manifest(name: str, version: str) -> TrustedManifest | None:
    """Return the trusted manifest matching an immutable name/version identity."""

    return next(
        (
            manifest
            for manifest in _TRUSTED_MANIFESTS
            if manifest.name == name and manifest.version == version
        ),
        None,
    )


__all__ = [
    "TRUSTED_REPOSITORIES",
    "TrustedManifest",
    "TrustedStep",
    "get_trusted_manifest",
    "iter_trusted_manifests",
]
