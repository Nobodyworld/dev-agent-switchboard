"""Version-controlled trusted command-manifest identities.

Executable definitions live only in reviewed source. The API and persisted manifest
snapshot expose safe metadata, while the local worker resolves fixed argv from the
same immutable name, version, and digest.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import PurePosixPath
from typing import Any

from .enums import NetworkPolicy, RepositoryWritePolicy
from .evidence import ParserKind, RedactionState, validate_relative_path

TRUSTED_REPOSITORIES = frozenset({"Nobodyworld/dev-agent-switchboard"})
MAX_TRUSTED_STEP_ID_LENGTH = 80
MAX_TRUSTED_STEP_OUTPUT_SUMMARY_BYTES = 64 * 1024
MIN_MEDIA_TYPE_LENGTH = 3
MAX_MEDIA_TYPE_LENGTH = 128


@dataclass(frozen=True, slots=True)
class TrustedArtifact:
    """One reviewed relative artifact produced by a trusted step."""

    kind: str
    relative_path: str
    media_type: str
    redaction_state: RedactionState

    def __post_init__(self) -> None:
        if not re.fullmatch(r"[a-z0-9][a-z0-9-]{0,63}", self.kind):
            raise ValueError("trusted artifact kind is invalid")
        validate_relative_path(self.relative_path)
        if not (
            MIN_MEDIA_TYPE_LENGTH <= len(self.media_type) <= MAX_MEDIA_TYPE_LENGTH
        ) or self.redaction_state not in {
            "none",
            "redacted",
        }:
            raise ValueError("trusted artifact metadata is invalid")

    def safe_metadata(self) -> dict[str, str]:
        return {
            "kind": self.kind,
            "media_type": self.media_type,
            "redaction_state": self.redaction_state,
            "relative_path": self.relative_path,
        }


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
    parser_kind: ParserKind | None = None
    artifacts: tuple[TrustedArtifact, ...] = ()

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
        if self.parser_kind not in {
            None,
            "pytest",
            "coverage",
            "pytest-coverage",
            "security-audit",
            "dependency-audit",
        }:
            raise ValueError("trusted step parser kind is unsupported")
        if len({item.relative_path for item in self.artifacts}) != len(self.artifacts):
            raise ValueError("trusted step artifact paths must be unique")
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

        payload: dict[str, Any] = {
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
        if self.parser_kind:
            payload["parser_kind"] = self.parser_kind
        if self.artifacts:
            payload["artifacts"] = [item.safe_metadata() for item in self.artifacts]
        return payload

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
        if self.parser_kind:
            metadata["parser_kind"] = self.parser_kind
        if self.artifacts:
            metadata["artifacts"] = [item.safe_metadata() for item in self.artifacts]
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
    dependency_lock_paths: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if self.execution_steps:
            expected_metadata = [step.safe_metadata() for step in self.execution_steps]
            if self.fixed_step_metadata != expected_metadata:
                raise ValueError(
                    "fixed_step_metadata must match safe executable-step metadata"
                )
        for path in self.dependency_lock_paths:
            validate_relative_path(path)

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
        if self.dependency_lock_paths:
            payload["dependency_lock_paths"] = list(self.dependency_lock_paths)
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


def _log_artifacts(step_id: str) -> tuple[TrustedArtifact, TrustedArtifact]:
    return (
        TrustedArtifact(
            kind="command-log",
            relative_path=f"logs/{step_id}.stdout.log",
            media_type="text/plain",
            redaction_state="none",
        ),
        TrustedArtifact(
            kind="command-log",
            relative_path=f"logs/{step_id}.stderr.log",
            media_type="text/plain",
            redaction_state="none",
        ),
    )


_FIXED_VALIDATION_ENVIRONMENT = (
    ("PYTHONDONTWRITEBYTECODE", "1"),
    ("PYTHONUTF8", "1"),
)


_VALIDATE_SWITCHBOARD_STEPS = (
    TrustedStep(
        id="python-version",
        title="Record Python version",
        argv=("python", "--version"),
        required=True,
        timeout_seconds=60,
        environment=_FIXED_VALIDATION_ENVIRONMENT,
        artifacts=_log_artifacts("python-version"),
    ),
    TrustedStep(
        id="dependency-health",
        title="Validate installed dependency consistency",
        argv=("python", "-m", "pip", "check"),
        required=False,
        timeout_seconds=300,
        environment=_FIXED_VALIDATION_ENVIRONMENT,
        diagnostic_only=True,
        parser_kind="dependency-audit",
        artifacts=_log_artifacts("dependency-health"),
    ),
    TrustedStep(
        id="lint",
        title="Run Ruff without fixes",
        argv=(
            "python",
            "-m",
            "ruff",
            "check",
            "--no-fix",
            "server",
            "client",
            "scripts",
            "tests",
            "web",
            "switchboard_cli.py",
            "switchboard_client.py",
        ),
        required=True,
        timeout_seconds=600,
        environment=_FIXED_VALIDATION_ENVIRONMENT,
        artifacts=_log_artifacts("lint"),
    ),
    TrustedStep(
        id="format",
        title="Check Black formatting",
        argv=(
            "python",
            "-m",
            "black",
            "--check",
            "server",
            "client",
            "scripts",
            "tests",
            "web",
            "switchboard_cli.py",
            "switchboard_client.py",
        ),
        required=True,
        timeout_seconds=600,
        environment=_FIXED_VALIDATION_ENVIRONMENT,
        artifacts=_log_artifacts("format"),
    ),
    TrustedStep(
        id="typecheck",
        title="Run the configured Mypy checks",
        argv=(
            "python",
            "-m",
            "mypy",
            "--config-file",
            "mypy.ini",
            "server",
            "client",
            "scripts",
        ),
        required=True,
        timeout_seconds=900,
        environment=_FIXED_VALIDATION_ENVIRONMENT,
        artifacts=_log_artifacts("typecheck"),
    ),
    TrustedStep(
        id="tests-with-coverage",
        title="Run tests with measured server coverage",
        argv=(
            "python",
            "-m",
            "pytest",
            "-q",
            "-p",
            "no:cacheprovider",
            "--cov=server",
            "--cov-report=term",
        ),
        required=True,
        timeout_seconds=1800,
        environment=_FIXED_VALIDATION_ENVIRONMENT,
        parser_kind="pytest-coverage",
        artifacts=_log_artifacts("tests-with-coverage"),
    ),
    TrustedStep(
        id="security-audit",
        title="Run the Bandit server audit",
        argv=("python", "-m", "bandit", "-q", "-r", "server", "-x", "server/tests"),
        required=True,
        timeout_seconds=600,
        environment=_FIXED_VALIDATION_ENVIRONMENT,
        parser_kind="security-audit",
        artifacts=_log_artifacts("security-audit"),
    ),
)


_VALIDATE_SWITCHBOARD_ARTIFACTS = [
    artifact.safe_metadata()
    for step in _VALIDATE_SWITCHBOARD_STEPS
    for artifact in step.artifacts
]


_TRUSTED_MANIFESTS = (
    TrustedManifest(
        name="validate-switchboard",
        version="1",
        schema_version=1,
        description=(
            "Read-only fixed-argv validation of one exact Switchboard commit with "
            "bounded retained local evidence."
        ),
        registry_source="server/execution/registry.py",
        required_capabilities={
            "operating_system": ["linux", "windows"],
            "python": {"minimum": "3.11"},
            "repository_write": False,
        },
        fixed_step_metadata=[
            step.safe_metadata() for step in _VALIDATE_SWITCHBOARD_STEPS
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
        artifact_declarations=_VALIDATE_SWITCHBOARD_ARTIFACTS,
        execution_steps=_VALIDATE_SWITCHBOARD_STEPS,
        dependency_lock_paths=(
            "server/requirements.txt",
            "server/requirements-dev.txt",
        ),
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
    "TrustedArtifact",
    "TrustedManifest",
    "TrustedStep",
    "get_trusted_manifest",
    "iter_trusted_manifests",
]
