"""Shared complete control-plane fixtures for execution-worker tests."""

from __future__ import annotations

from typing import Any

from server.execution.evidence import compute_execution_policy_hash
from server.execution.registry import TrustedManifest

_TIMESTAMP = "2026-07-16T00:00:00+00:00"


def work_order_payload(
    sha: str,
    manifest: TrustedManifest,
    **overrides: object,
) -> dict[str, Any]:
    """Return the complete current ``WorkOrderOut`` JSON contract."""

    execution_policy_hash = compute_execution_policy_hash(
        expected_artifact_kinds=(),
        manifest_parameters={},
        permitted_paths=(),
        required_capabilities={"repository_write": False},
        timeout_seconds=manifest.timeout_seconds,
        network_policy=manifest.network_policy.value,
        repository_write_allowed=False,
    )
    payload: dict[str, Any] = {
        "id": 3,
        "schema_version": 1,
        "repository_full_name": "Nobodyworld/dev-agent-switchboard",
        "commit_sha": sha,
        "manifest_name": manifest.name,
        "manifest_version": manifest.version,
        "manifest_digest": manifest.digest,
        "manifest_parameters": {},
        "required_capabilities": {"repository_write": False},
        "permitted_paths": [],
        "forbidden_scope_notes": "",
        "expected_artifact_kinds": [],
        "approval_policy": "explicit",
        "status": "assigned",
        "timeout_seconds": manifest.timeout_seconds,
        "resource_metadata": {},
        "network_policy": manifest.network_policy.value,
        "repository_write_allowed": False,
        "preferred_executor": None,
        "cost_ceiling": None,
        "attempt_count": 1,
        "created_at": _TIMESTAMP,
        "updated_at": _TIMESTAMP,
        "approved_at": _TIMESTAMP,
        "queued_at": _TIMESTAMP,
        "assigned_at": _TIMESTAMP,
        "started_at": None,
        "finished_at": None,
        "terminal_reason": None,
        "reuse_policy": "never",
        "execution_policy_hash": execution_policy_hash,
    }
    payload.update(overrides)
    return payload


def remote_manifest_payload(manifest: TrustedManifest) -> dict[str, Any]:
    """Return the complete safe manifest response for a trusted definition."""

    return {
        "name": manifest.name,
        "version": manifest.version,
        "digest": manifest.digest,
        "timeout_seconds": manifest.timeout_seconds,
        "network_policy": manifest.network_policy.value,
        "repository_write_policy": manifest.repository_write_policy.value,
        "schema_version": manifest.schema_version,
        "required_capabilities": manifest.required_capabilities,
        "fixed_step_metadata": manifest.fixed_step_metadata,
        "environment_policy": manifest.environment_policy,
        "artifact_declarations": manifest.artifact_declarations,
        "description": manifest.description,
        "trusted_registry_source": manifest.registry_source,
    }
