"""Version-controlled trusted command-manifest identities.

The Phase 1 control plane deliberately exposes only identity and safe contract
metadata. It neither accepts executable steps from callers nor launches them.
The future worker implementation is responsible for consuming a reviewed,
version-controlled execution definition after its own issue-specific review.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any

from .enums import NetworkPolicy, RepositoryWritePolicy

TRUSTED_REPOSITORIES = frozenset({"Nobodyworld/dev-agent-switchboard"})


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

    @property
    def digest(self) -> str:
        """Return the stable SHA-256 digest of this reviewed contract metadata."""

        payload = {
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
        encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


# This is a metadata-only representation of the reviewed v1 contract example.
# In particular, it intentionally does not contain argv, shell text, scripts,
# executable paths, or any process-launching behavior.
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
