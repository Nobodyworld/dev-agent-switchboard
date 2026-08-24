"""Worker enforcement tests for reviewed factory-only result contracts."""

from __future__ import annotations

from pathlib import Path

import pytest

from client.python.execution_worker.config import WorkerConfig
from client.python.execution_worker.worker import _profile_evidence_policy
from server.execution.evidence import compute_result_contract_hash
from server.execution.registry import get_trusted_manifest

_TOKEN = "worker-profile-contract-test-token"  # noqa: S105 - local test fixture
_MEBIBYTE = 1024 * 1024
_DEFAULT_RETENTION_DAYS = 14
_DEFAULT_ARTIFACT_COUNT = 32
_RESTRICTED_RETENTION_DAYS = 7
_RESTRICTED_ARTIFACT_COUNT = 2
_RESTRICTED_ARTIFACT_BYTES = 1024
_RESTRICTED_TOTAL_BYTES = 2048


def _config(tmp_path: Path, **overrides: object) -> WorkerConfig:
    values: dict[str, object] = {
        "base_url": "http://switchboard.test",
        "worker_id": "profile-contract-worker",
        "display_name": "Profile contract worker",
        "admin_token": _TOKEN,
        "worker_root": tmp_path / "worker-root",
        "repositories": {"Nobodyworld/dev-logger-zscripts": tmp_path / "source"},
        "evidence_root": tmp_path / "evidence",
    }
    values.update(overrides)
    return WorkerConfig(**values)  # type: ignore[arg-type]


def test_factory_profile_contract_caps_retained_evidence_and_binds_reuse_hash(
    tmp_path: Path,
) -> None:
    manifest = get_trusted_manifest("validate-zscripts", "1")
    assert manifest is not None and manifest.result_contract is not None

    retention_days, limits = _profile_evidence_policy(manifest, _config(tmp_path))

    assert retention_days == _DEFAULT_RETENTION_DAYS
    assert limits.maximum_artifact_count == _DEFAULT_ARTIFACT_COUNT
    assert limits.maximum_artifact_bytes == 16 * _MEBIBYTE
    assert limits.maximum_total_bytes == 128 * _MEBIBYTE

    original = compute_result_contract_hash(
        fixed_step_metadata=manifest.fixed_step_metadata,
        artifact_declarations=manifest.artifact_declarations,
        dependency_lock_paths=manifest.dependency_lock_paths,
        result_contract=manifest.result_contract,
    )
    changed_contract = {
        **manifest.result_contract,
        "resource_limits": {
            **manifest.result_contract["resource_limits"],
            "retention_days": 13,
        },
    }
    assert (
        compute_result_contract_hash(
            fixed_step_metadata=manifest.fixed_step_metadata,
            artifact_declarations=manifest.artifact_declarations,
            dependency_lock_paths=manifest.dependency_lock_paths,
            result_contract=changed_contract,
        )
        != original
    )


def test_local_evidence_policy_can_only_be_stricter_than_reviewed_profile(
    tmp_path: Path,
) -> None:
    manifest = get_trusted_manifest("validate-industry-resilience", "1")
    assert manifest is not None
    config = _config(
        tmp_path,
        evidence_retention_days=_RESTRICTED_RETENTION_DAYS,
        maximum_artifact_count=_RESTRICTED_ARTIFACT_COUNT,
        maximum_artifact_bytes=_RESTRICTED_ARTIFACT_BYTES,
        maximum_total_evidence_bytes=_RESTRICTED_TOTAL_BYTES,
    )

    retention_days, limits = _profile_evidence_policy(manifest, config)

    assert retention_days == _RESTRICTED_RETENTION_DAYS
    assert limits.maximum_artifact_count == _RESTRICTED_ARTIFACT_COUNT
    assert limits.maximum_artifact_bytes == _RESTRICTED_ARTIFACT_BYTES
    assert limits.maximum_total_bytes == _RESTRICTED_TOTAL_BYTES


def test_factory_result_contract_fails_closed_when_resource_limits_are_malformed(
    tmp_path: Path,
) -> None:
    manifest = get_trusted_manifest("validate-zscripts", "1")
    assert manifest is not None and manifest.result_contract is not None
    malformed = type(manifest)(
        name=manifest.name,
        version=manifest.version,
        schema_version=manifest.schema_version,
        description=manifest.description,
        registry_source=manifest.registry_source,
        required_capabilities=manifest.required_capabilities,
        fixed_step_metadata=manifest.fixed_step_metadata,
        environment_policy=manifest.environment_policy,
        network_policy=manifest.network_policy,
        repository_write_policy=manifest.repository_write_policy,
        timeout_seconds=manifest.timeout_seconds,
        artifact_declarations=manifest.artifact_declarations,
        allowed_parameters=manifest.allowed_parameters,
        execution_steps=manifest.execution_steps,
        dependency_lock_paths=manifest.dependency_lock_paths,
        result_contract={"resource_limits": {}},
    )

    with pytest.raises(ValueError, match="result contract"):
        _profile_evidence_policy(malformed, _config(tmp_path))
