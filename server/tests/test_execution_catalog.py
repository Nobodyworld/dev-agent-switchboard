"""Trusted repository catalog, pairing, and bounded API regressions."""

from __future__ import annotations

import json
from http import HTTPStatus

import pytest
from httpx import ASGITransport, AsyncClient
from pydantic import ValidationError
from sqlalchemy import func, select

from server.app import app
from server.application import build_execution_service
from server.db import AsyncSessionLocal
from server.execution.catalog import (
    TrustedRepository,
    get_trusted_repository,
    iter_trusted_repositories,
    repository_allows_manifest,
    trusted_catalog_digest,
    validate_catalog,
    validate_repository_full_name,
)
from server.execution.entities import WorkOrderDraft
from server.execution.enums import ApprovalPolicy, NetworkPolicy
from server.execution.exceptions import UnknownManifestError
from server.execution.registry import get_trusted_manifest
from server.execution.schemas import WorkerRegistrationIn, WorkOrderCreateIn
from server.github_adapter.schemas import GitHubValidationCreateIn
from server.models import (
    ExecutionLease,
    ExecutionRun,
    ExecutionWorkOrder,
    GitHubValidationRequest,
)

_SWITCHBOARD = "Nobodyworld/dev-agent-switchboard"
_ACCOUNTING = "Nobodyworld/app-accounting-modular"
_SHA256_LENGTH = 64
_EXPECTED_MANIFEST_STEPS = 11
_EXPECTED_REPOSITORIES = 2
_ACCOUNTING_MANIFEST_DIGEST = (
    # pragma: allowlist nextline secret
    "892f1269cdf2a6f4e0df4d86879e5dae980374d598faeadee77c2c32f33aa612"
)
# pragma: allowlist nextline secret
_CATALOG_DIGEST = "3e8fe68e917d1afa5615e158f3ef69ac78193f356502c8e6fb071799edad5436"

_ACCOUNTING_COMMANDS = (
    ("python", "-m", "ruff", "check", "."),
    ("python", "-m", "ruff", "format", "--check", "."),
    (
        "python",
        "-m",
        "mypy",
        "src/apps/modular_accounting/application",
        "src/apps/api",
        "src/apps/extensions",
        "src/cli",
    ),
    (
        "python",
        "-m",
        "pytest",
        "-o",
        "cache_dir=.pytest_cache_runtime",
        "--cov=src/apps",
        "--cov=src/plugins",
        "--cov=src/cli",
        "--cov-branch",
        "--cov-report=term-missing",
        "--cov-report=xml:coverage.xml",
        "--cov-report=json:coverage.json",
    ),
    (
        "python",
        "-m",
        "src.tools.coverage_gate",
        "coverage.json",
        "--minimum-line",
        "85",
    ),
    (
        "python",
        "-m",
        "src.tools.critical_coverage",
        "coverage.json",
        "--config",
        "config/critical-coverage.toml",
    ),
    (
        "python",
        "-m",
        "pytest",
        "-o",
        "cache_dir=.pytest_cache_runtime",
        "-q",
        "tests/test_ledger_service.py",
        "tests/test_data_snapshot_service.py",
        "tests/test_modular_accounting_snapshot.py",
        "tests/test_modular_accounting_controls.py",
    ),
    ("python", "-m", "pip", "check"),
    (
        "python",
        "-m",
        "pip_audit",
        "--timeout",
        "60",
        "--require-hashes",
        "--disable-pip",
        "-r",
        "requirements-container.lock",
    ),
    (
        "python",
        "-m",
        "pip_audit",
        "--timeout",
        "60",
        "-r",
        "requirements-dev.txt",
    ),
    ("python", "-m", "src.tools.secret_scan"),
)


def _cross_repository_draft() -> WorkOrderDraft:
    return WorkOrderDraft(
        schema_version=1,
        repository_full_name=_ACCOUNTING,
        commit_sha="a" * 40,
        manifest_name="validate-switchboard",
        manifest_version="1",
        manifest_parameters={},
        required_capabilities={},
        permitted_paths=(),
        forbidden_scope_notes="read-only exact commit validation",
        expected_artifact_kinds=(),
        approval_policy=ApprovalPolicy.EXPLICIT,
        timeout_seconds=3600,
        resource_metadata={},
        network_policy=NetworkPolicy.WORKER_RESTRICTED,
        repository_write_allowed=False,
        preferred_executor=None,
        cost_ceiling=None,
    )


def test_catalog_is_canonical_strict_and_preserves_existing_manifest_identities() -> (
    None
):
    repositories = iter_trusted_repositories()
    assert [item.full_name for item in repositories] == sorted(
        [_ACCOUNTING, _SWITCHBOARD]
    )
    assert len(trusted_catalog_digest()) == _SHA256_LENGTH
    assert trusted_catalog_digest() == _CATALOG_DIGEST
    assert get_trusted_manifest("worker-smoke", "1").digest == (
        # pragma: allowlist nextline secret
        "63e645f19d8c60ae442e1800aaecc1a18a719d53f22ba8e85ec62bf745ed55d1"
    )
    assert get_trusted_manifest("validate-switchboard", "1").digest == (
        # pragma: allowlist nextline secret
        "10e99418e4e6f0e9f4a6e95fb5b9a267dab4eeac4671cf58533c8b9afe1fed98"
    )
    accounting = get_trusted_manifest("validate-accounting-modular", "1")
    assert accounting is not None
    assert accounting.digest == _ACCOUNTING_MANIFEST_DIGEST
    assert len(accounting.execution_steps) == _EXPECTED_MANIFEST_STEPS
    assert (
        tuple(step.argv for step in accounting.execution_steps) == _ACCOUNTING_COMMANDS
    )
    assert tuple(step.parser_kind for step in accounting.execution_steps) == (
        None,
        None,
        None,
        "pytest-coverage",
        "coverage",
        "critical-coverage",
        "pytest",
        "dependency-health",
        "dependency-audit",
        "dependency-audit",
        "secret-scan",
    )
    assert {
        artifact.relative_path
        for step in accounting.execution_steps
        for artifact in step.artifacts
    } >= {"coverage.xml", "coverage.json"}
    assert accounting.dependency_lock_paths == (
        "requirements.txt",
        "requirements-dev.txt",
        "requirements-container.lock",
    )
    assert repository_allows_manifest(_ACCOUNTING, accounting.name, accounting.version)
    assert not repository_allows_manifest(_ACCOUNTING, "validate-switchboard", "1")

    with pytest.raises(ValueError, match="fields are invalid"):
        repository = get_trusted_repository(_ACCOUNTING)
        assert repository is not None
        TrustedRepository.from_mapping(
            {
                **repository.safe_metadata(),
                "unexpected": "fail closed",
            }
        )


def test_catalog_definitions_fail_closed_for_duplicates_and_invalid_references() -> (
    None
):
    accounting = get_trusted_repository(_ACCOUNTING)
    assert accounting is not None
    base = accounting.safe_metadata()
    for changes in (
        {"full_name": "missing-slash"},
        {"manifests": [base["manifests"][0], base["manifests"][0]]},
        {"default_manifest": {"name": "worker-smoke", "version": "1"}},
    ):
        with pytest.raises(ValueError):
            TrustedRepository.from_mapping({**base, **changes})
    with pytest.raises(ValueError, match="identities must be unique"):
        validate_catalog(
            {("validate-accounting-modular", "1")},
            (accounting, accounting),
        )
    unknown_reference = TrustedRepository.from_mapping(
        {
            **base,
            "manifests": [{"name": "missing-manifest", "version": "1"}],
            "default_manifest": {"name": "missing-manifest", "version": "1"},
        }
    )
    with pytest.raises(ValueError, match="unknown manifest"):
        validate_catalog(set(), (unknown_reference,))


@pytest.mark.parametrize(
    "repository_full_name",
    ("./repository", "../repository", "owner/.", "owner/.."),
)
def test_repository_identity_rejects_exact_dot_segments_everywhere(
    repository_full_name: str,
) -> None:
    accounting = get_trusted_repository(_ACCOUNTING)
    assert accounting is not None
    with pytest.raises(ValueError, match="dot segment"):
        validate_repository_full_name(repository_full_name)
    with pytest.raises(ValueError, match="dot segment"):
        TrustedRepository.from_mapping(
            {**accounting.safe_metadata(), "full_name": repository_full_name}
        )
    with pytest.raises(ValidationError):
        WorkOrderCreateIn.model_validate(
            {
                "repository_full_name": repository_full_name,
                "commit_sha": "a" * 40,
                "manifest": {"name": "validate-switchboard", "version": "1"},
            }
        )
    with pytest.raises(ValidationError):
        GitHubValidationCreateIn.model_validate(
            {
                "repository_full_name": repository_full_name,
                "pull_request_number": 1,
                "manifest": {"name": "validate-switchboard", "version": "1"},
            }
        )
    with pytest.raises(ValidationError):
        WorkerRegistrationIn.model_validate(
            {
                "worker_id": "dot-segment-worker",
                "display_name": "Dot segment worker",
                "operating_system": "linux",
                "architecture": "x86_64",
                "repository_full_names": [repository_full_name],
            }
        )


def test_repository_identity_allows_periods_inside_real_segments() -> None:
    value = "owner.with.period/repository.with.period"
    assert validate_repository_full_name(value) == value
    accounting = get_trusted_repository(_ACCOUNTING)
    assert accounting is not None
    repository = TrustedRepository.from_mapping(
        {**accounting.safe_metadata(), "full_name": value}
    )
    assert repository.full_name == value


def test_worker_repository_names_are_sorted_known_bounded_and_path_free() -> None:
    base = {
        "worker_id": "catalog-worker",
        "display_name": "Catalog worker",
        "operating_system": "linux",
        "architecture": "x86_64",
    }
    legacy = WorkerRegistrationIn.model_validate(base)
    assert legacy.repository_full_names == [_SWITCHBOARD]
    accepted = WorkerRegistrationIn.model_validate(
        {
            **base,
            "repository_full_names": [_ACCOUNTING, _SWITCHBOARD],
        }
    )
    assert json.dumps(accepted.model_dump()).find("C:\\") == -1
    for values in (
        [_SWITCHBOARD, _ACCOUNTING],
        [_SWITCHBOARD, _SWITCHBOARD],
        ["Nobodyworld/unknown"],
        [_SWITCHBOARD] * 33,
    ):
        with pytest.raises(ValidationError):
            WorkerRegistrationIn.model_validate(
                {**base, "repository_full_names": values}
            )


@pytest.mark.asyncio
async def test_cross_repository_manifest_pair_is_rejected_before_persistence() -> None:
    async with AsyncSessionLocal() as session:
        before = int(
            await session.scalar(select(func.count(ExecutionWorkOrder.id))) or 0
        )
        before_related = []
        for model in (GitHubValidationRequest, ExecutionRun, ExecutionLease):
            before_related.append(
                int(await session.scalar(select(func.count(model.id))) or 0)
            )
        service = build_execution_service(session)
        with pytest.raises(
            UnknownManifestError, match="repository_manifest_not_allowed"
        ):
            await service.create_work_order(_cross_repository_draft())
        await session.rollback()
        after = int(
            await session.scalar(select(func.count(ExecutionWorkOrder.id))) or 0
        )
        assert after == before
        after_related = []
        for model in (GitHubValidationRequest, ExecutionRun, ExecutionLease):
            after_related.append(
                int(await session.scalar(select(func.count(model.id))) or 0)
            )
        assert after_related == before_related


@pytest.mark.asyncio
async def test_catalog_api_is_bounded_and_executable_data_free() -> None:
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.get("/api/execution/trusted-repositories")
    assert response.status_code == HTTPStatus.OK
    payload = response.json()
    assert payload["schema_version"] == 1
    assert payload["digest"] == trusted_catalog_digest()
    assert len(payload["repositories"]) == _EXPECTED_REPOSITORIES
    serialized = json.dumps(payload, sort_keys=True)
    for prohibited in (
        '"argv":',
        '"environment":',
        '"working_directory":',
        ":\\",
        "file://",
    ):
        assert prohibited not in serialized
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        detail = await client.get(
            "/api/execution/trusted-repositories/Nobodyworld/app-accounting-modular"
        )
    assert detail.status_code == HTTPStatus.OK
    assert detail.json()["support_status"] == "developer_preview"
    assert detail.json()["documentation_reference"].startswith("docs/")
