# ruff: noqa: PLR2004
"""Persistence, idempotency, API, and publication tests for issue #122."""

from __future__ import annotations

import asyncio
import datetime as dt
import json
from collections.abc import AsyncGenerator, Callable
from dataclasses import asdict, replace
from http import HTTPStatus
from typing import cast

import pytest
from httpx import ASGITransport, AsyncClient
from pydantic import ValidationError
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from server.api.dependencies import (
    SessionDependency,
    get_github_adapter_service,
    get_session,
)
from server.app import app as server_app
from server.application import build_execution_service
from server.db import AsyncSessionLocal
from server.execution.entities import (
    ExecutionCompletion,
    RoutingProfileDraft,
    WorkerRegistration,
)
from server.execution.enums import (
    ExecutionRunStatus,
    NetworkPolicy,
    ReuseDecision,
    ReusePolicy,
    RoutingPolicy,
    WorkerStatus,
    WorkOrderStatus,
)
from server.execution.evidence import (
    AuditSummary,
    DependencyLockHash,
    EnvironmentIdentity,
    EvidenceReuseIdentity,
    EvidenceReuseProvenance,
    ExecutionEvidenceDraft,
    ParsedCoverage,
    ParsedResult,
    ParsedTestCounts,
    StepEvidence,
    compute_result_contract_hash,
    compute_reuse_identity_hash,
    finalize_evidence,
)
from server.execution.operator_projection import ExecutionOperatorProjection
from server.execution.registry import get_trusted_manifest
from server.github_adapter.errors import (
    GitHubAmbiguousWriteError,
    GitHubManifestError,
    GitHubRateLimitedError,
    GitHubRepositoryNotAllowedError,
    GitHubTerminalEvidenceRequiredError,
    GitHubTransportError,
)
from server.github_adapter.rendering import (
    has_exact_marker,
    managed_comment_marker,
)
from server.github_adapter.repository import GitHubAdapterRepository
from server.github_adapter.schemas import GitHubValidationCreateIn
from server.github_adapter.service import (
    PUBLICATION_CLAIM_TTL,
    GitHubAdapterDependencies,
    GitHubAdapterService,
    _legacy_idempotency_key,
)
from server.github_adapter.transport import (
    GitHubActorIdentity,
    GitHubComment,
    GitHubCommentListing,
    GitHubTransport,
    ResolvedPullRequest,
)
from server.models import ExecutionWorkOrder, GitHubValidationRequest
from server.settings import GitHubSettings, get_github_settings, reload_admin_token
from server.time_utils import utcnow_naive

REPOSITORY = "Nobodyworld/dev-agent-switchboard"
HEAD_SHA = "a" * 40
MOVED_SHA = "c" * 40
BASE_SHA = "b" * 40
ADMIN_TOKEN = "adapter-admin-test-token"  # noqa: S105
GITHUB_TOKEN = "offline-adapter-secret-placeholder"  # noqa: S105
CREDENTIAL_ACTOR = GitHubActorIdentity(actor_id=700, node_id="U_credential")
USER_ACTOR = GitHubActorIdentity(actor_id=701, node_id="U_user")


def _resolved(  # noqa: PLR0913 - stable identity variants are explicit
    *,
    head_sha: str | None = HEAD_SHA,
    repository_id: int = 100,
    repository_node_id: str = "R_repo",
    pull_request_id: int = 200,
    pull_request_node_id: str = "PR_node",
    state: str = "open",
    draft: bool = False,
    merged: bool = False,
    head_repository_full_name: str | None = REPOSITORY,
    head_repository_id: int | None = 100,
) -> ResolvedPullRequest:
    return ResolvedPullRequest(
        repository_full_name=REPOSITORY,
        repository_id=repository_id,
        repository_node_id=repository_node_id,
        pull_request_number=125,
        pull_request_id=pull_request_id,
        pull_request_node_id=pull_request_node_id,
        state=state,
        draft=draft,
        merged=merged,
        base_ref="main",
        base_sha=BASE_SHA,
        head_ref="feature/exact-pr",
        head_sha=head_sha,
        head_repository_full_name=head_repository_full_name,
        head_repository_id=head_repository_id,
    )


def _comment(
    comment_id: int,
    body: str,
    *,
    author: GitHubActorIdentity = CREDENTIAL_ACTOR,
    repository_full_name: str = REPOSITORY,
    pull_request_number: int = 125,
) -> GitHubComment:
    return GitHubComment(
        comment_id=comment_id,
        body=body,
        author=author,
        repository_full_name=repository_full_name,
        pull_request_number=pull_request_number,
    )


class FakeGitHubTransport(GitHubTransport):
    """Stateful, offline transport that exposes comment idempotency effects."""

    def __init__(self, resolved: ResolvedPullRequest | None = None) -> None:
        self.resolved = resolved or _resolved()
        self.credential_actor = CREDENTIAL_ACTOR
        self.actor_calls = 0
        self.resolve_calls = 0
        self.list_calls = 0
        self.comments: list[GitHubComment] = []
        self.created_comment_ids: list[int] = []
        self.updated_comment_ids: list[int] = []
        self.next_comment_id = 500
        self.ambiguous_create = False
        self.rate_limit_publication = False
        self.listing_complete = True
        self.pause_create = False
        self.create_started = asyncio.Event()
        self.allow_create = asyncio.Event()
        self.after_list: Callable[[], None] | None = None

    async def resolve_pull_request(
        self,
        repository_full_name: str,
        pull_request_number: int,
        *,
        require_head: bool = True,
    ) -> ResolvedPullRequest:
        assert repository_full_name == REPOSITORY
        assert pull_request_number == 125
        self.resolve_calls += 1
        if require_head and self.resolved.head_sha is None:
            raise AssertionError("test transport was asked to require an absent head")
        return self.resolved

    async def list_comments(
        self, repository_full_name: str, pull_request_number: int
    ) -> GitHubCommentListing:
        assert repository_full_name == REPOSITORY
        assert pull_request_number == 125
        self.list_calls += 1
        if self.rate_limit_publication:
            raise GitHubRateLimitedError("github_rate_limited")
        if self.after_list is not None:
            self.after_list()
        return GitHubCommentListing(
            comments=tuple(self.comments),
            complete=self.listing_complete,
        )

    async def resolve_authenticated_actor(self) -> GitHubActorIdentity:
        self.actor_calls += 1
        return self.credential_actor

    async def get_comment(
        self, repository_full_name: str, comment_id: int
    ) -> GitHubComment:
        assert repository_full_name == REPOSITORY
        for comment in self.comments:
            if comment.comment_id == comment_id:
                return comment
        raise GitHubTransportError("github_comment_not_found")

    async def create_comment(
        self,
        repository_full_name: str,
        pull_request_number: int,
        body: str,
    ) -> GitHubComment:
        assert repository_full_name == REPOSITORY
        assert pull_request_number == 125
        if self.pause_create:
            self.create_started.set()
            await self.allow_create.wait()
        comment = _comment(
            self.next_comment_id,
            body,
            author=self.credential_actor,
        )
        self.next_comment_id += 1
        self.comments.append(comment)
        self.created_comment_ids.append(comment.comment_id)
        if self.ambiguous_create:
            self.ambiguous_create = False
            raise GitHubAmbiguousWriteError("github_publication_failed")
        return comment

    async def update_comment(
        self,
        repository_full_name: str,
        comment_id: int,
        body: str,
    ) -> GitHubComment:
        assert repository_full_name == REPOSITORY
        self.updated_comment_ids.append(comment_id)
        for index, comment in enumerate(self.comments):
            if comment.comment_id == comment_id:
                updated = replace(comment, body=body)
                self.comments[index] = updated
                return updated
        raise AssertionError("service attempted to update an absent comment")


def _settings() -> GitHubSettings:
    return GitHubSettings(
        api_url="https://api.github.com",
        operator_id="test-operator",
        token=GITHUB_TOKEN,
    )


def _service(
    session: AsyncSession,
    transport: FakeGitHubTransport,
    *,
    clock: Callable[[], dt.datetime] = utcnow_naive,
) -> GitHubAdapterService:
    return GitHubAdapterService(
        dependencies=GitHubAdapterDependencies(
            repository=GitHubAdapterRepository(session),
            execution=build_execution_service(session),
            transport=transport,
        ),
        settings=_settings(),
        clock=clock,
    )


def _worker(worker_id: str = "github-adapter-worker") -> WorkerRegistration:
    return WorkerRegistration(
        worker_id=worker_id,
        display_name="GitHub adapter worker",
        operating_system="windows",
        architecture="amd64",
        python_version="3.11.14",
        node_version=None,
        docker_available=False,
        browsers=(),
        gpu_available=False,
        unity_available=False,
        desktop_available=False,
        capabilities={},
        max_concurrency=1,
        network_policy_capability=NetworkPolicy.WORKER_RESTRICTED,
        repository_write_capability=False,
        status=WorkerStatus.ONLINE,
    )


def _step(
    *,
    step_id: str,
    parsed: ParsedResult,
    now: dt.datetime,
) -> StepEvidence:
    return StepEvidence(
        step_id=step_id,
        title=f"Bounded {step_id}",
        status="succeeded",
        started_at=now,
        finished_at=now + dt.timedelta(seconds=1),
        duration_seconds=1,
        exit_code=0,
        summary="bounded parsed summary",
        parsed_result=parsed,
    )


def _reuse_identity(order: ExecutionWorkOrder) -> EvidenceReuseIdentity:
    manifest = get_trusted_manifest(order.manifest_name, order.manifest_version)
    assert manifest is not None
    return EvidenceReuseIdentity(
        repository_full_name=order.repository_full_name,
        tested_sha=order.commit_sha,
        manifest_name=order.manifest_name,
        manifest_version=order.manifest_version,
        manifest_digest=order.manifest_digest,
        worker_environment_fingerprint="d" * 64,
        dependency_lock_hashes=[
            DependencyLockHash(relative_path=path, sha256="e" * 64)
            for path in sorted(manifest.dependency_lock_paths)
        ],
        execution_policy_hash=order.execution_policy_hash,
        result_contract_hash=compute_result_contract_hash(
            fixed_step_metadata=manifest.fixed_step_metadata,
            artifact_declarations=manifest.artifact_declarations,
            dependency_lock_paths=manifest.dependency_lock_paths,
        ),
    )


def _reuse_evidence(  # noqa: PLR0913
    *,
    order: ExecutionWorkOrder,
    run_id: int,
    worker_id: str,
    identity: EvidenceReuseIdentity,
    decision: str,
    source_run_id: int | None = None,
    source_fingerprint: str | None = None,
):
    now = dt.datetime(2026, 8, 8, 12, tzinfo=dt.UTC)
    return finalize_evidence(
        ExecutionEvidenceDraft(
            work_order_id=order.id,
            run_id=run_id,
            repository_full_name=order.repository_full_name,
            tested_sha=order.commit_sha,
            manifest_name=order.manifest_name,
            manifest_version=order.manifest_version,
            manifest_digest=order.manifest_digest,
            worker_id=worker_id,
            environment=EnvironmentIdentity(
                operating_system="windows",
                architecture="amd64",
                python_version="3.11.14",
                fingerprint=identity.worker_environment_fingerprint,
            ),
            dependency_lock_hashes=identity.dependency_lock_hashes,
            started_at=now,
            finished_at=now + dt.timedelta(seconds=7),
            duration_seconds=7,
            terminal_status="succeeded",
            steps=[],
            artifacts=[],
            dependency_lock_status="succeeded",
            artifact_finalization_status="succeeded",
            source_cleanup_status="succeeded",
            local_record_status="succeeded",
            reuse_provenance=EvidenceReuseProvenance(
                decision=decision,  # type: ignore[arg-type]
                reason=("exact_evidence_verified" if decision == "reused" else "fresh"),
                reuse_identity_hash=compute_reuse_identity_hash(identity),
                source_run_id=source_run_id,
                source_evidence_fingerprint=source_fingerprint,
            ),
        )
    )


async def _complete_with_compact_evidence(
    service: GitHubAdapterService,
    request_id: int,
    *,
    worker_id: str = "github-adapter-worker",
) -> int:
    status = await service.get_status(request_id)
    execution = service._execution
    await execution.approve_work_order(status.work_order_id)
    await execution.register_worker(_worker(worker_id))
    checkout = await execution.checkout(worker_id)
    assert checkout.run_id is not None
    run = await execution.get_run(checkout.run_id)
    work_order = await execution.get_work_order(status.work_order_id)
    now = dt.datetime(2026, 7, 24, 12, tzinfo=dt.UTC)
    evidence = finalize_evidence(
        ExecutionEvidenceDraft(
            work_order_id=work_order.id,
            run_id=run.id,
            repository_full_name=work_order.repository_full_name,
            tested_sha=work_order.commit_sha,
            manifest_name=work_order.manifest_name,
            manifest_version=work_order.manifest_version,
            manifest_digest=work_order.manifest_digest,
            worker_id=worker_id,
            environment=EnvironmentIdentity(
                operating_system="windows",
                architecture="amd64",
                python_version="3.11.14",
                fingerprint="d" * 64,
            ),
            started_at=now,
            finished_at=now + dt.timedelta(seconds=4),
            duration_seconds=4,
            terminal_status="succeeded",
            terminal_reason="validation_completed",
            steps=[
                _step(
                    step_id="tests",
                    parsed=ParsedResult(
                        parser="pytest",
                        status="parsed",
                        tests=ParsedTestCounts(
                            passed=40, failed=0, skipped=2, total=42
                        ),
                    ),
                    now=now,
                ),
                _step(
                    step_id="coverage",
                    parsed=ParsedResult(
                        parser="coverage",
                        status="parsed",
                        coverage=ParsedCoverage(measured_percent=91.25),
                    ),
                    now=now,
                ),
                _step(
                    step_id="security",
                    parsed=ParsedResult(
                        parser="security-audit",
                        status="parsed",
                        audit=AuditSummary(
                            kind="security",
                            status="passed",
                            tool="bandit",
                            findings=0,
                        ),
                    ),
                    now=now,
                ),
                _step(
                    step_id="dependency",
                    parsed=ParsedResult(
                        parser="dependency-audit",
                        status="parsed",
                        audit=AuditSummary(
                            kind="dependency",
                            status="passed",
                            tool="pip-audit",
                            findings=0,
                        ),
                    ),
                    now=now,
                ),
            ],
            artifacts=[],
            dependency_lock_status="succeeded",
            artifact_finalization_status="succeeded",
            source_cleanup_status="succeeded",
            local_record_status="succeeded",
        )
    )
    await execution.complete_run(
        run.id,
        worker_id=worker_id,
        completion=ExecutionCompletion(
            status=ExecutionRunStatus.SUCCEEDED,
            result_summary="bounded validation summary",
            terminal_reason="validation_completed",
            cleanup_status="succeeded",
            evidence_metadata=evidence,
        ),
    )
    return run.id


async def _managed_record(
    service: GitHubAdapterService,
    session: AsyncSession,
) -> tuple[GitHubValidationRequest, str, str]:
    status = await service.request_validation(
        repository_full_name=REPOSITORY,
        pull_request_number=125,
        manifest_name="validate-switchboard",
        manifest_version="1",
    )
    request = await session.get(GitHubValidationRequest, status.request_id)
    assert request is not None
    marker = managed_comment_marker(request.idempotency_key)
    return request, marker, f"{marker}\nbounded managed evidence"


@pytest.mark.asyncio
async def test_allowlist_is_enforced_before_remote_or_work_order_creation() -> None:
    transport = FakeGitHubTransport()
    async with AsyncSessionLocal() as session:
        service = _service(session, transport)
        with pytest.raises(
            GitHubRepositoryNotAllowedError,
            match=r"^github_repository_not_allowed$",
        ):
            await service.request_validation(
                repository_full_name="attacker/not-allowlisted",
                pull_request_number=125,
                manifest_name="validate-switchboard",
                manifest_version="1",
            )
        work_orders = await session.scalar(
            select(func.count()).select_from(ExecutionWorkOrder)
        )

    assert transport.actor_calls == 0
    assert transport.resolve_calls == 0
    assert int(work_orders or 0) == 0


@pytest.mark.asyncio
async def test_repository_manifest_pair_is_enforced_before_remote_or_persistence() -> (
    None
):
    transport = FakeGitHubTransport()
    async with AsyncSessionLocal() as session:
        before_requests = int(
            await session.scalar(select(func.count(GitHubValidationRequest.id))) or 0
        )
        before_orders = int(
            await session.scalar(select(func.count(ExecutionWorkOrder.id))) or 0
        )
        service = _service(session, transport)
        with pytest.raises(
            GitHubManifestError, match=r"^repository_manifest_not_allowed$"
        ):
            await service.request_validation(
                repository_full_name=REPOSITORY,
                pull_request_number=125,
                manifest_name="validate-accounting-modular",
                manifest_version="1",
            )
        await session.rollback()
        assert (
            int(
                await session.scalar(select(func.count(GitHubValidationRequest.id)))
                or 0
            )
            == before_requests
        )
        assert (
            int(await session.scalar(select(func.count(ExecutionWorkOrder.id))) or 0)
            == before_orders
        )

    assert transport.actor_calls == 0
    assert transport.resolve_calls == 0


@pytest.mark.asyncio
async def test_duplicate_request_reuses_work_order_and_new_head_is_distinct() -> None:
    transport = FakeGitHubTransport(_resolved(state="open", draft=True, merged=False))
    async with AsyncSessionLocal() as session:
        service = _service(session, transport)
        first = await service.request_validation(
            repository_full_name=REPOSITORY,
            pull_request_number=125,
            manifest_name="validate-switchboard",
            manifest_version="1",
        )
        duplicate = await service.request_validation(
            repository_full_name=REPOSITORY,
            pull_request_number=125,
            manifest_name="validate-switchboard",
            manifest_version="1",
        )

        assert duplicate.request_id == first.request_id
        assert duplicate.work_order_id == first.work_order_id
        assert first.work_order_status == WorkOrderStatus.PENDING_APPROVAL.value
        assert first.pull_request_draft is True
        work_order = await service._execution.get_work_order(first.work_order_id)
        assert work_order.approval_policy.value == "explicit"
        assert work_order.status == WorkOrderStatus.PENDING_APPROVAL
        assert work_order.commit_sha == HEAD_SHA
        assert work_order.required_capabilities["repository_write"] is False

        transport.resolved = _resolved(head_sha=MOVED_SHA)
        moved = await service.request_validation(
            repository_full_name=REPOSITORY,
            pull_request_number=125,
            manifest_name="validate-switchboard",
            manifest_version="1",
        )
        assert moved.request_id != first.request_id
        assert moved.work_order_id != first.work_order_id
        assert moved.tested_head_sha == MOVED_SHA

        adapter_count = await session.scalar(
            select(func.count()).select_from(GitHubValidationRequest)
        )
        work_order_count = await session.scalar(
            select(func.count()).select_from(ExecutionWorkOrder)
        )

    assert int(adapter_count or 0) == 2
    assert int(work_order_count or 0) == 2


@pytest.mark.asyncio
async def test_every_adapter_policy_dimension_changes_request_identity() -> None:
    transport = FakeGitHubTransport()
    variants = (
        {},
        {"reuse_policy": ReusePolicy.ALLOW_EXACT},
        {"routing_policy": RoutingPolicy.CHEAPEST_CAPABLE},
        {"maximum_cost_units": 17},
        {"required_quota_units": 3},
        {"preferred_executor": "worker-preferred"},
    )
    async with AsyncSessionLocal() as session:
        service = _service(session, transport)
        await service._execution.register_worker(_worker("worker-preferred"))
        statuses = []
        for policy in variants:
            statuses.append(
                await service.request_validation(
                    repository_full_name=REPOSITORY,
                    pull_request_number=125,
                    manifest_name="validate-switchboard",
                    manifest_version="1",
                    **policy,
                )
            )
        records = (
            (
                await session.execute(
                    select(GitHubValidationRequest).order_by(GitHubValidationRequest.id)
                )
            )
            .scalars()
            .all()
        )

    assert len({status.request_id for status in statuses}) == len(variants)
    assert len({status.work_order_id for status in statuses}) == len(variants)
    assert len({record.idempotency_key for record in records}) == len(variants)
    assert statuses[0].reuse_policy == ReusePolicy.NEVER
    assert statuses[0].routing_policy == RoutingPolicy.FIRST_AVAILABLE
    assert statuses[1].reuse_policy == ReusePolicy.ALLOW_EXACT
    assert statuses[2].routing_policy == RoutingPolicy.CHEAPEST_CAPABLE
    assert statuses[3].maximum_cost_units == 17
    assert statuses[4].required_quota_units == 3
    assert statuses[5].preferred_executor == "worker-preferred"


@pytest.mark.asyncio
async def test_default_policy_finds_exact_legacy_key_without_mutating_it() -> None:
    transport = FakeGitHubTransport()
    async with AsyncSessionLocal() as session:
        service = _service(session, transport)
        created = await service.request_validation(
            repository_full_name=REPOSITORY,
            pull_request_number=125,
            manifest_name="validate-switchboard",
            manifest_version="1",
        )
        record = await session.get(GitHubValidationRequest, created.request_id)
        manifest = get_trusted_manifest("validate-switchboard", "1")
        assert record is not None
        assert manifest is not None
        legacy_key = _legacy_idempotency_key(
            settings=_settings(),
            actor=CREDENTIAL_ACTOR,
            resolved=transport.resolved,
            manifest=manifest,
        )
        record.idempotency_key = legacy_key
        await session.flush()

        recovered = await service.request_validation(
            repository_full_name=REPOSITORY,
            pull_request_number=125,
            manifest_name="validate-switchboard",
            manifest_version="1",
        )
        unchanged = await session.get(GitHubValidationRequest, created.request_id)
        non_default = await service.request_validation(
            repository_full_name=REPOSITORY,
            pull_request_number=125,
            manifest_name="validate-switchboard",
            manifest_version="1",
            reuse_policy=ReusePolicy.ALLOW_EXACT,
        )

    assert recovered.request_id == created.request_id
    assert unchanged is not None
    assert unchanged.idempotency_key == legacy_key
    assert non_default.request_id != created.request_id


@pytest.mark.asyncio
async def test_direct_completion_projects_fresh_then_reused_github_lifecycle(  # noqa: PLR0915
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Exercise projection formulas without representing the local-worker trust path."""

    transport = FakeGitHubTransport()
    cheap_worker = "worker-cheap"
    expensive_worker = "worker-expensive"
    async with AsyncSessionLocal() as session:
        adapter = _service(session, transport)
        execution = adapter._execution
        monkeypatch.setattr(
            execution,
            "_clock",
            lambda: dt.datetime(2026, 8, 8, 12, tzinfo=dt.UTC).replace(tzinfo=None),
        )
        await execution.register_worker(_worker(cheap_worker))
        await execution.register_worker(_worker(expensive_worker))
        await execution.create_routing_profile(
            RoutingProfileDraft(
                schema_version=1,
                worker_id=cheap_worker,
                enabled=True,
                estimated_cost_units_per_run=3,
                quota_capacity_units=20,
                quota_remaining_units=20,
                quota_reset_at=None,
                routing_priority=0,
            )
        )
        await execution.create_routing_profile(
            RoutingProfileDraft(
                schema_version=1,
                worker_id=expensive_worker,
                enabled=True,
                estimated_cost_units_per_run=9,
                quota_capacity_units=20,
                quota_remaining_units=20,
                quota_reset_at=None,
                routing_priority=0,
            )
        )

        fresh_request = await adapter.request_validation(
            repository_full_name=REPOSITORY,
            pull_request_number=125,
            manifest_name="validate-switchboard",
            manifest_version="1",
            reuse_policy=ReusePolicy.NEVER,
            routing_policy=RoutingPolicy.CHEAPEST_CAPABLE,
            required_quota_units=1,
        )
        assert not (await execution.checkout(expensive_worker)).assigned
        assert not (await execution.checkout(cheap_worker)).assigned
        await execution.approve_work_order(fresh_request.work_order_id)
        assert not (await execution.checkout(expensive_worker)).assigned
        fresh_assignment = await execution.checkout(cheap_worker)
        assert fresh_assignment.run_id is not None
        await execution.heartbeat_run(fresh_assignment.run_id, worker_id=cheap_worker)
        fresh_order = await execution.get_work_order(fresh_request.work_order_id)
        fresh_identity = _reuse_identity(fresh_order)
        fresh_evidence = _reuse_evidence(
            order=fresh_order,
            run_id=fresh_assignment.run_id,
            worker_id=cheap_worker,
            identity=fresh_identity,
            decision="fresh",
        )
        fresh_run = await execution.complete_run(
            fresh_assignment.run_id,
            worker_id=cheap_worker,
            completion=ExecutionCompletion(
                status=ExecutionRunStatus.SUCCEEDED,
                evidence_metadata=fresh_evidence,
                reuse_decision=ReuseDecision.FRESH,
                reuse_reason="fresh_execution_completed",
                reuse_identity=fresh_identity,
                reuse_identity_hash=compute_reuse_identity_hash(fresh_identity),
                evidence_retention_expires_at=(
                    fresh_evidence.started_at + dt.timedelta(days=14)
                ),
            ),
        )
        fresh_run.started_at = dt.datetime(2026, 8, 8, 12, 0, 0, tzinfo=dt.UTC)
        fresh_run.finished_at = dt.datetime(2026, 8, 8, 12, 0, 7, tzinfo=dt.UTC)
        await session.flush()
        published_current = await adapter.publish(fresh_request.request_id)
        assert published_current.publication_state == "published_current"
        republished_current = await adapter.publish(fresh_request.request_id)
        assert republished_current.managed_comment_id == (
            published_current.managed_comment_id
        )

        reused_request = await adapter.request_validation(
            repository_full_name=REPOSITORY,
            pull_request_number=125,
            manifest_name="validate-switchboard",
            manifest_version="1",
            reuse_policy=ReusePolicy.ALLOW_EXACT,
            routing_policy=RoutingPolicy.CHEAPEST_CAPABLE,
            required_quota_units=1,
        )
        reused_order = await execution.get_work_order(reused_request.work_order_id)
        assert reused_request.request_id != fresh_request.request_id
        assert reused_order.execution_policy_hash == fresh_order.execution_policy_hash
        assert not (await execution.checkout(expensive_worker)).assigned
        assert not (await execution.checkout(cheap_worker)).assigned
        await execution.approve_work_order(reused_request.work_order_id)
        assert not (await execution.checkout(expensive_worker)).assigned
        reused_assignment = await execution.checkout(cheap_worker)
        assert reused_assignment.run_id is not None
        reused_identity = _reuse_identity(reused_order)
        assert reused_identity == fresh_identity
        lookup = await execution.resolve_reuse_candidate(
            reused_assignment.run_id,
            worker_id=cheap_worker,
            reuse_identity=reused_identity,
            reuse_identity_hash=compute_reuse_identity_hash(reused_identity),
        )
        assert lookup.candidate is not None
        assert lookup.candidate.source_run_id == fresh_run.id
        reused_evidence = _reuse_evidence(
            order=reused_order,
            run_id=reused_assignment.run_id,
            worker_id=cheap_worker,
            identity=reused_identity,
            decision="reused",
            source_run_id=fresh_run.id,
            source_fingerprint=fresh_evidence.fingerprint,
        )
        reused_run = await execution.complete_run(
            reused_assignment.run_id,
            worker_id=cheap_worker,
            completion=ExecutionCompletion(
                status=ExecutionRunStatus.SUCCEEDED,
                evidence_metadata=reused_evidence,
                reuse_decision=ReuseDecision.REUSED,
                reuse_reason="exact_evidence_verified",
                reuse_identity=reused_identity,
                reuse_identity_hash=compute_reuse_identity_hash(reused_identity),
                evidence_retention_expires_at=(
                    reused_evidence.started_at + dt.timedelta(days=14)
                ),
            ),
        )
        assert reused_run.worker_id == cheap_worker
        assert reused_run.reused_from_run_id == fresh_run.id
        assert reused_run.evidence_metadata["steps"] == []

        transport.resolved = _resolved(head_sha=MOVED_SHA)
        published_stale = await adapter.publish(reused_request.request_id)
        assert published_stale.publication_state == "published_stale"

        projection = ExecutionOperatorProjection(session)
        overview = await projection.overview(
            window_days=30,
            heartbeat_freshness_seconds=300,
            active_poll_freshness_seconds=60,
        )
        history = await projection.list_history(limit=25, offset=0)
        first_page = await projection.list_history(limit=1, offset=0)
        second_page = await projection.list_history(limit=1, offset=1)
        filter_now = dt.datetime.now(dt.UTC)
        reused_history = await projection.list_history(
            limit=25,
            offset=0,
            repository_full_name=REPOSITORY,
            pull_request_number=125,
            work_order_status=WorkOrderStatus.SUCCEEDED.value,
            run_status=ExecutionRunStatus.SUCCEEDED.value,
            reuse_decision=ReuseDecision.REUSED.value,
            routing_policy=RoutingPolicy.CHEAPEST_CAPABLE.value,
            publication_state="published_stale",
            created_after=filter_now - dt.timedelta(days=1),
            created_before=filter_now + dt.timedelta(days=1),
        )
        workers = await projection.list_workers(
            limit=25,
            offset=0,
            heartbeat_freshness_seconds=300,
            active_poll_freshness_seconds=60,
        )
        fresh_run.started_at = None
        reused_run.route_estimated_cost_units = None
        await session.flush()
        missing_estimates = await projection.overview(
            window_days=30,
            heartbeat_freshness_seconds=300,
            active_poll_freshness_seconds=60,
        )

    assert overview.requests.total == 2
    assert overview.runs.fresh_successful == 1
    assert overview.runs.reused_successful == 1
    assert overview.avoided_work.deterministic_executions_avoided == 1
    assert overview.avoided_work.reference_seconds_avoided == 7
    assert overview.avoided_work.comparison_units_avoided == 3
    assert overview.avoided_work.reuse_rate == 0.5
    assert overview.publications.current == 1
    assert overview.publications.stale == 1
    assert history.total == 2
    assert history.items[0].request_id == reused_request.request_id
    assert history.items[0].reuse_decision == "reused"
    assert history.items[1].reuse_decision == "fresh"
    assert [item.request_id for item in first_page.items] == [reused_request.request_id]
    assert [item.request_id for item in second_page.items] == [fresh_request.request_id]
    assert reused_history.total == 1
    assert reused_history.items[0].request_id == reused_request.request_id
    assert {item.worker_id for item in workers.items} == {
        cheap_worker,
        expensive_worker,
    }
    assert "capabilities" not in workers.items[0].model_dump()
    assert "repository_full_name" not in workers.items[0].model_dump()
    assert missing_estimates.avoided_work.deterministic_executions_avoided == 1
    assert missing_estimates.avoided_work.reference_seconds_avoided == 0
    assert missing_estimates.avoided_work.comparison_units_avoided == 0


@pytest.mark.asyncio
async def test_operator_projection_routes_enforce_hard_query_bounds() -> None:
    transport = ASGITransport(
        app=server_app, client=("operator-projection-test", 12_345)
    )
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        overview = await client.get("/api/execution/operator/overview")
        history = await client.get("/api/execution/operator/history")
        workers = await client.get("/api/execution/workers")
        requests = await client.get("/api/execution/github/requests")
        too_wide = await client.get(
            "/api/execution/operator/overview", params={"window_days": 366}
        )
        too_many = await client.get(
            "/api/execution/operator/history", params={"limit": 101}
        )
        too_far = await client.get(
            "/api/execution/github/requests", params={"offset": 10_001}
        )

    assert overview.status_code == HTTPStatus.OK
    assert overview.json()["window"]["days"] == 30
    assert history.status_code == HTTPStatus.OK
    assert workers.status_code == HTTPStatus.OK
    assert requests.status_code == HTTPStatus.OK
    assert too_wide.status_code == HTTPStatus.UNPROCESSABLE_ENTITY
    assert too_many.status_code == HTTPStatus.UNPROCESSABLE_ENTITY
    assert too_far.status_code == HTTPStatus.UNPROCESSABLE_ENTITY


@pytest.mark.asyncio
async def test_token_rotation_to_another_actor_creates_distinct_request() -> None:
    transport = FakeGitHubTransport()
    async with AsyncSessionLocal() as session:
        service = _service(session, transport)
        first = await service.request_validation(
            repository_full_name=REPOSITORY,
            pull_request_number=125,
            manifest_name="validate-switchboard",
            manifest_version="1",
        )
        first_record = await session.get(GitHubValidationRequest, first.request_id)
        assert first_record is not None
        first_key = first_record.idempotency_key

        transport.credential_actor = USER_ACTOR
        rotated = await service.request_validation(
            repository_full_name=REPOSITORY,
            pull_request_number=125,
            manifest_name="validate-switchboard",
            manifest_version="1",
        )
        rotated_record = await session.get(
            GitHubValidationRequest,
            rotated.request_id,
        )
        assert rotated_record is not None

    assert rotated.request_id != first.request_id
    assert rotated.work_order_id != first.work_order_id
    assert rotated_record.idempotency_key != first_key
    assert rotated_record.github_actor_id == USER_ACTOR.actor_id
    assert rotated_record.github_actor_node_id == USER_ACTOR.node_id


def test_request_schema_rejects_every_server_owned_or_executable_field() -> None:
    valid = {
        "repository_full_name": REPOSITORY,
        "pull_request_number": 125,
        "manifest": {"name": "validate-switchboard", "version": "1"},
    }
    forbidden = {
        "host": "https://attacker.example",
        "repository_id": 100,
        "pull_request_node_id": "PR_node",
        "head_sha": HEAD_SHA,
        "base_sha": BASE_SHA,
        "manifest_digest": "d" * 64,
        "worker_id": "attacker-worker",
        "work_order_status": "succeeded",
        "evidence_fingerprint": "e" * 64,
        "artifact_hashes": ["f" * 64],
        "comment_id": 99,
        "publication_status": "published_current",
        "commands": ["python", "-c", "malicious"],
        "argv": ["malicious"],
        "scripts": ["malicious"],
        "urls": ["https://attacker.example"],
        "local_paths": [r"C:\private\checkout"],
    }

    assert GitHubValidationCreateIn.model_validate(valid)
    for field, value in forbidden.items():
        with pytest.raises(ValidationError):
            GitHubValidationCreateIn.model_validate({**valid, field: value})


def test_adapter_table_has_no_credential_or_remote_body_columns() -> None:
    columns = set(GitHubValidationRequest.__table__.columns.keys())

    assert {
        "token",
        "authorization",
        "authorization_header",
        "response_body",
        "request_body",
        "commands",
        "argv",
        "environment",
        "local_path",
        "artifact_location",
    }.isdisjoint(columns)


@pytest.mark.asyncio
async def test_publication_requires_terminal_compact_evidence() -> None:
    transport = FakeGitHubTransport()
    async with AsyncSessionLocal() as session:
        service = _service(session, transport)
        requested = await service.request_validation(
            repository_full_name=REPOSITORY,
            pull_request_number=125,
            manifest_name="validate-switchboard",
            manifest_version="1",
        )

        with pytest.raises(
            GitHubTerminalEvidenceRequiredError,
            match=r"^github_terminal_evidence_required$",
        ):
            await service.publish(requested.request_id)
        stored = await session.get(GitHubValidationRequest, requested.request_id)
        assert stored is not None
        assert stored.publication_state == "retryable_failure"
        assert stored.publication_reason == "github_terminal_evidence_required"
        assert stored.publication_claim_token is None
        assert stored.publication_claimed_at is None
        assert stored.publication_claim_expires_at is None

    assert transport.comments == []


@pytest.mark.asyncio
async def test_publication_fails_closed_when_credential_actor_changes() -> None:
    transport = FakeGitHubTransport()
    async with AsyncSessionLocal() as session:
        service = _service(session, transport)
        requested = await service.request_validation(
            repository_full_name=REPOSITORY,
            pull_request_number=125,
            manifest_name="validate-switchboard",
            manifest_version="1",
        )
        await _complete_with_compact_evidence(service, requested.request_id)
        transport.credential_actor = USER_ACTOR

        failed = await service.publish(requested.request_id)

    assert failed.publication_state == "failed"
    assert failed.publication_reason == "github_actor_mismatch"
    assert transport.created_comment_ids == []
    assert transport.updated_comment_ids == []
    assert transport.list_calls == 0


@pytest.mark.asyncio
async def test_current_publication_creates_then_updates_only_persisted_comment() -> (
    None
):
    transport = FakeGitHubTransport()
    user_comment = _comment(
        41,
        ("<!-- switchboard-validation:v1:" + "0" * 64 + " -->\nuser-authored text"),
        author=USER_ACTOR,
    )
    transport.comments.append(user_comment)
    async with AsyncSessionLocal() as session:
        service = _service(session, transport)
        requested = await service.request_validation(
            repository_full_name=REPOSITORY,
            pull_request_number=125,
            manifest_name="validate-switchboard",
            manifest_version="1",
        )
        run_id = await _complete_with_compact_evidence(service, requested.request_id)

        published = await service.publish(requested.request_id)
        assert published.publication_state == "published_current"
        assert published.publication_decision == "current"
        assert published.terminal_run_id == run_id
        assert len(transport.created_comment_ids) == 1
        managed_id = cast(int, published.managed_comment_id)
        managed = next(
            comment
            for comment in transport.comments
            if comment.comment_id == managed_id
        )
        marker = managed_comment_marker(
            (
                await session.get(GitHubValidationRequest, requested.request_id)
            ).idempotency_key  # type: ignore[union-attr]
        )
        assert has_exact_marker(managed.body, marker)
        assert "40 passed, 0 failed, 2 skipped, 0 errors" in managed.body
        assert "91.25%" in managed.body
        assert "Security audit: `passed; 0 findings`" in managed.body
        assert "Dependency audit: `passed; 0 findings`" in managed.body
        assert "Execution provenance: `fresh`" in managed.body
        assert HEAD_SHA in managed.body
        assert "Full logs and artifact bytes remain local" in managed.body

        # A copied exact marker must not displace the persisted managed ID.
        copied = _comment(
            42,
            f"{marker}\nuser copied the marker",
            author=USER_ACTOR,
        )
        transport.comments.insert(0, copied)
        repeated = await service.publish(requested.request_id)
        assert repeated.managed_comment_id == managed_id
        assert transport.updated_comment_ids[-1] == managed_id
        assert len(transport.created_comment_ids) == 1
        assert (
            next(
                comment.body
                for comment in transport.comments
                if comment.comment_id == 41
            )
            == user_comment.body
        )
        assert (
            next(
                comment.body
                for comment in transport.comments
                if comment.comment_id == 42
            )
            == copied.body
        )

        serialized = json.dumps(asdict(repeated), default=str)
        rendered = next(
            comment.body
            for comment in transport.comments
            if comment.comment_id == managed_id
        )

    prohibited = (
        GITHUB_TOKEN,
        "Authorization",
        '"argv"',
        "stdout",
        "stderr",
        r"C:\private",
        "/tmp/checkout",  # noqa: S108 - prohibited-output sentinel
        "environment=",
        "artifact location",
    )
    assert all(value not in serialized for value in prohibited)
    assert all(value not in rendered for value in prohibited)


@pytest.mark.asyncio
async def test_user_exact_marker_before_first_publish_is_never_edited() -> None:
    transport = FakeGitHubTransport()
    async with AsyncSessionLocal() as session:
        service = _service(session, transport)
        request, marker, body = await _managed_record(service, session)
        user_comment = _comment(
            41,
            f"{marker}\nuser-authored copied marker",
            author=USER_ACTOR,
        )
        transport.comments.append(user_comment)

        managed = await service._upsert_managed_comment(request, body)

    assert managed.comment_id == 500
    assert transport.created_comment_ids == [500]
    assert transport.updated_comment_ids == []
    assert transport.comments[0] == user_comment


@pytest.mark.asyncio
async def test_copied_marker_with_null_id_never_displaces_owned_comment() -> None:
    transport = FakeGitHubTransport()
    async with AsyncSessionLocal() as session:
        service = _service(session, transport)
        request, marker, body = await _managed_record(service, session)
        copied = _comment(41, f"{marker}\ncopy", author=USER_ACTOR)
        owned = _comment(42, f"{marker}\nprevious managed evidence")
        transport.comments.extend([copied, owned])
        assert request.managed_comment_id is None

        managed = await service._upsert_managed_comment(request, body)

    assert managed.comment_id == owned.comment_id
    assert transport.created_comment_ids == []
    assert transport.updated_comment_ids == [owned.comment_id]
    assert transport.comments[0] == copied


@pytest.mark.asyncio
async def test_persisted_id_pointing_to_user_comment_is_not_edited() -> None:
    transport = FakeGitHubTransport()
    async with AsyncSessionLocal() as session:
        service = _service(session, transport)
        request, marker, body = await _managed_record(service, session)
        user_comment = _comment(41, f"{marker}\nuser text", author=USER_ACTOR)
        transport.comments.append(user_comment)
        request.managed_comment_id = user_comment.comment_id

        managed = await service._upsert_managed_comment(request, body)

    assert managed.comment_id == 500
    assert transport.created_comment_ids == [500]
    assert transport.updated_comment_ids == []
    assert transport.comments[0] == user_comment


@pytest.mark.asyncio
async def test_persisted_id_for_another_pull_request_is_not_edited() -> None:
    transport = FakeGitHubTransport()
    async with AsyncSessionLocal() as session:
        service = _service(session, transport)
        request, marker, body = await _managed_record(service, session)
        other_pr = _comment(
            42,
            f"{marker}\nother PR",
            pull_request_number=126,
        )
        transport.comments.append(other_pr)
        request.managed_comment_id = other_pr.comment_id

        managed = await service._upsert_managed_comment(request, body)

    assert managed.comment_id == 500
    assert transport.created_comment_ids == [500]
    assert transport.updated_comment_ids == []
    assert transport.comments[0] == other_pr


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "persisted",
    [
        _comment(
            43,
            f"<!-- switchboard-validation:v1:{'d' * 64} -->\nwrong marker",
        ),
        _comment(
            44,
            "<!-- switchboard-validation:v1:" + "e" * 64 + " -->\nother repo",
            repository_full_name="Nobodyworld/other-repository",
        ),
        _comment(
            45,
            "<!-- switchboard-validation:v1:" + "f" * 64 + " -->\nother actor",
            author=USER_ACTOR,
        ),
    ],
)
async def test_other_mismatched_persisted_ids_are_never_patched(
    persisted: GitHubComment,
) -> None:
    transport = FakeGitHubTransport()
    async with AsyncSessionLocal() as session:
        service = _service(session, transport)
        request, _marker, body = await _managed_record(service, session)
        transport.comments.append(persisted)
        request.managed_comment_id = persisted.comment_id

        managed = await service._upsert_managed_comment(request, body)

    assert managed.comment_id == 500
    assert transport.created_comment_ids == [500]
    assert transport.updated_comment_ids == []
    assert transport.comments[0] == persisted


@pytest.mark.asyncio
async def test_cross_repository_persisted_id_with_exact_marker_is_not_edited() -> None:
    transport = FakeGitHubTransport()
    async with AsyncSessionLocal() as session:
        service = _service(session, transport)
        request, marker, body = await _managed_record(service, session)
        cross_repository = _comment(
            46,
            f"{marker}\nother repository",
            repository_full_name="Nobodyworld/other-repository",
        )
        transport.comments.append(cross_repository)
        request.managed_comment_id = cross_repository.comment_id

        managed = await service._upsert_managed_comment(request, body)

    assert managed.comment_id == 500
    assert transport.created_comment_ids == [500]
    assert transport.updated_comment_ids == []
    assert transport.comments[0] == cross_repository


@pytest.mark.asyncio
async def test_deleted_persisted_comment_recovers_before_replacement() -> None:
    transport = FakeGitHubTransport()
    async with AsyncSessionLocal() as session:
        service = _service(session, transport)
        request, _marker, body = await _managed_record(service, session)
        first = await service._upsert_managed_comment(request, body)
        request.managed_comment_id = first.comment_id
        transport.comments.clear()

        replacement = await service._upsert_managed_comment(request, body)

    assert first.comment_id == 500
    assert replacement.comment_id == 501
    assert transport.created_comment_ids == [500, 501]
    assert transport.updated_comment_ids == []
    assert transport.comments == [replacement]


@pytest.mark.asyncio
async def test_ambiguous_create_over_100_comments_recovers_without_duplicate() -> None:
    transport = FakeGitHubTransport()
    transport.comments.extend(
        _comment(index, f"ordinary user comment {index}", author=USER_ACTOR)
        for index in range(1, 102)
    )
    transport.ambiguous_create = True
    async with AsyncSessionLocal() as session:
        service = _service(session, transport)
        request, _marker, body = await _managed_record(service, session)

        managed = await service._upsert_managed_comment(request, body)

    assert managed.comment_id == 500
    assert transport.created_comment_ids == [500]
    assert transport.updated_comment_ids == [500]
    assert (
        len(
            [
                comment
                for comment in transport.comments
                if comment.author == CREDENTIAL_ACTOR
            ]
        )
        == 1
    )


@pytest.mark.asyncio
async def test_multiple_owned_exact_marker_candidates_fail_closed_until_unique() -> (
    None
):
    transport = FakeGitHubTransport()
    async with AsyncSessionLocal() as session:
        service = _service(session, transport)
        request, marker, body = await _managed_record(service, session)
        user_copy = _comment(40, f"{marker}\ncopy", author=USER_ACTOR)
        first = _comment(41, f"{marker}\nfirst")
        second = _comment(42, f"{marker}\nsecond")
        transport.comments.extend([user_copy, first, second])

        with pytest.raises(
            GitHubTransportError,
            match=r"^github_comment_recovery_ambiguous$",
        ):
            await service._upsert_managed_comment(request, body)
        transport.comments.remove(second)
        recovered = await service._upsert_managed_comment(request, body)

    assert recovered.comment_id == first.comment_id
    assert transport.created_comment_ids == []
    assert transport.updated_comment_ids == [first.comment_id]
    assert transport.comments[0] == user_copy


@pytest.mark.asyncio
async def test_incomplete_recovery_window_fails_closed_without_write() -> None:
    transport = FakeGitHubTransport()
    transport.listing_complete = False
    async with AsyncSessionLocal() as session:
        service = _service(session, transport)
        request, _marker, body = await _managed_record(service, session)

        with pytest.raises(
            GitHubTransportError,
            match=r"^github_comment_recovery_unverifiable$",
        ):
            await service._upsert_managed_comment(request, body)

    assert transport.created_comment_ids == []
    assert transport.updated_comment_ids == []


@pytest.mark.asyncio
async def test_database_claim_serializes_two_services_and_sessions() -> None:
    transport = FakeGitHubTransport()
    transport.pause_create = True
    async with AsyncSessionLocal() as setup_session:
        setup_service = _service(setup_session, transport)
        requested = await setup_service.request_validation(
            repository_full_name=REPOSITORY,
            pull_request_number=125,
            manifest_name="validate-switchboard",
            manifest_version="1",
        )
        await _complete_with_compact_evidence(setup_service, requested.request_id)
        await setup_session.commit()

    async with (
        AsyncSessionLocal() as first_session,
        AsyncSessionLocal() as second_session,
    ):
        first_service = _service(first_session, transport)
        second_service = _service(second_session, transport)
        first_task = asyncio.create_task(first_service.publish(requested.request_id))
        await transport.create_started.wait()

        concurrent = await second_service.publish(requested.request_id)

        assert concurrent.publication_reason == "github_publication_in_progress"
        assert transport.created_comment_ids == []
        assert transport.updated_comment_ids == []
        transport.allow_create.set()
        published = await first_task

    async with AsyncSessionLocal() as verification_session:
        stored = await verification_session.get(
            GitHubValidationRequest,
            requested.request_id,
        )
        assert stored is not None
        assert stored.managed_comment_id == published.managed_comment_id == 500
        assert stored.publication_claim_token is None
        assert stored.publication_claimed_at is None
        assert stored.publication_claim_expires_at is None
    assert transport.created_comment_ids == [500]
    assert transport.updated_comment_ids == []
    assert len(transport.comments) == 1


@pytest.mark.asyncio
async def test_expired_publication_claim_is_recoverable() -> None:
    transport = FakeGitHubTransport()
    async with AsyncSessionLocal() as setup_session:
        setup_service = _service(setup_session, transport)
        requested = await setup_service.request_validation(
            repository_full_name=REPOSITORY,
            pull_request_number=125,
            manifest_name="validate-switchboard",
            manifest_version="1",
        )
        await _complete_with_compact_evidence(setup_service, requested.request_id)
        await setup_session.commit()

    expired_at = utcnow_naive() - dt.timedelta(minutes=5)
    async with AsyncSessionLocal() as interrupted_session:
        interrupted_repository = GitHubAdapterRepository(interrupted_session)
        acquired = await interrupted_repository.acquire_publication_claim(
            requested.request_id,
            token="1" * 64,
            claimed_at=expired_at - dt.timedelta(minutes=5),
            expires_at=expired_at,
        )
        assert acquired is True

    async with AsyncSessionLocal() as recovery_session:
        recovered = await _service(recovery_session, transport).publish(
            requested.request_id
        )

    assert recovered.managed_comment_id == 500
    assert recovered.publication_state == "published_current"
    assert transport.created_comment_ids == [500]


@pytest.mark.asyncio
async def test_expired_holder_cannot_make_remote_write() -> None:
    now = [utcnow_naive()]
    transport = FakeGitHubTransport()

    def advance_past_expiry() -> None:
        now[0] += PUBLICATION_CLAIM_TTL + dt.timedelta(seconds=1)

    transport.after_list = advance_past_expiry
    async with AsyncSessionLocal() as session:
        service = _service(session, transport, clock=lambda: now[0])
        requested = await service.request_validation(
            repository_full_name=REPOSITORY,
            pull_request_number=125,
            manifest_name="validate-switchboard",
            manifest_version="1",
        )
        await _complete_with_compact_evidence(service, requested.request_id)

        failed = await service.publish(requested.request_id)

    assert failed.publication_state == "retryable_failure"
    assert failed.publication_reason == "github_publication_claim_lost"
    assert transport.created_comment_ids == []
    assert transport.updated_comment_ids == []


@pytest.mark.asyncio
async def test_stale_claim_token_cannot_release_newer_claim() -> None:
    transport = FakeGitHubTransport()
    async with AsyncSessionLocal() as setup_session:
        requested = await _service(
            setup_session,
            transport,
        ).request_validation(
            repository_full_name=REPOSITORY,
            pull_request_number=125,
            manifest_name="validate-switchboard",
            manifest_version="1",
        )
        await setup_session.commit()

    old_claimed_at = utcnow_naive() - dt.timedelta(minutes=10)
    new_claimed_at = utcnow_naive()
    async with (
        AsyncSessionLocal() as stale_session,
        AsyncSessionLocal() as current_session,
    ):
        stale_repository = GitHubAdapterRepository(stale_session)
        current_repository = GitHubAdapterRepository(current_session)
        assert await stale_repository.acquire_publication_claim(
            requested.request_id,
            token="2" * 64,
            claimed_at=old_claimed_at,
            expires_at=old_claimed_at + dt.timedelta(minutes=1),
        )
        assert await current_repository.acquire_publication_claim(
            requested.request_id,
            token="3" * 64,
            claimed_at=new_claimed_at,
            expires_at=new_claimed_at + dt.timedelta(minutes=5),
        )

        assert (
            await stale_repository.finalize_publication_claim(
                requested.request_id,
                token="2" * 64,
                values={
                    "managed_comment_id": 999,
                    "publication_reason": "github_publication_succeeded",
                },
            )
            is False
        )
        current = await current_repository.get(
            requested.request_id,
            refresh=True,
        )
        assert current is not None
        assert current.publication_claim_token == "3" * 64
        assert current.managed_comment_id is None
        assert current.publication_reason == "github_publication_in_progress"
        assert await current_repository.release_publication_claim(
            requested.request_id,
            token="3" * 64,
        )


@pytest.mark.asyncio
async def test_ambiguous_create_under_claim_recovers_exactly_one_comment() -> None:
    transport = FakeGitHubTransport()
    transport.ambiguous_create = True
    async with AsyncSessionLocal() as session:
        service = _service(session, transport)
        requested = await service.request_validation(
            repository_full_name=REPOSITORY,
            pull_request_number=125,
            manifest_name="validate-switchboard",
            manifest_version="1",
        )
        await _complete_with_compact_evidence(service, requested.request_id)

        published = await service.publish(requested.request_id)

    assert published.managed_comment_id == 500
    assert transport.created_comment_ids == [500]
    assert transport.updated_comment_ids == [500]
    assert len(transport.comments) == 1


@pytest.mark.asyncio
async def test_actor_identity_is_immutable_but_not_exposed() -> None:
    response_sentinel = "discarded-actor-response-field"
    transport = FakeGitHubTransport()
    transport.credential_actor = GitHubActorIdentity(
        actor_id=987_654,
        node_id="U_stable_actor",
    )
    async with AsyncSessionLocal() as session:
        service = _service(session, transport)
        request, _marker, body = await _managed_record(service, session)
        await service._upsert_managed_comment(request, body)
        status = await service.get_status(request.id)
        stored = await session.get(GitHubValidationRequest, request.id)
        assert stored is not None
        assert stored.github_actor_id == transport.credential_actor.actor_id
        assert stored.github_actor_node_id == transport.credential_actor.node_id
        serialized_status = json.dumps(asdict(status), default=str)
        rendered = transport.comments[0].body

    prohibited = (
        GITHUB_TOKEN,
        response_sentinel,
        "github_actor_id",
        "github_actor_node_id",
        "publication_claim_token",
        "https://api.github.com/user",
        "https://api.github.com/repos/",
        r"C:\private\checkout",
        "python -m pytest",
        "remote response body",
        "environment=",
    )
    assert all(value not in serialized_status for value in prohibited)
    assert all(value not in rendered for value in prohibited)


@pytest.mark.asyncio
async def test_moved_head_publishes_stale_without_rewriting_tested_sha() -> None:
    transport = FakeGitHubTransport()
    async with AsyncSessionLocal() as session:
        service = _service(session, transport)
        requested = await service.request_validation(
            repository_full_name=REPOSITORY,
            pull_request_number=125,
            manifest_name="validate-switchboard",
            manifest_version="1",
        )
        await _complete_with_compact_evidence(service, requested.request_id)
        transport.resolved = _resolved(head_sha=MOVED_SHA)

        published = await service.publish(requested.request_id)
        assert published.publication_state == "published_stale"
        assert published.publication_decision == "stale"
        assert published.publication_head_sha == MOVED_SHA
        assert published.tested_head_sha == HEAD_SHA
        assert published.publication_reason == "github_publication_stale"
        assert len(transport.comments) == 1
        body = transport.comments[0].body

    assert "Head decision: `stale` (`github_head_changed`)" in body
    assert HEAD_SHA in body
    assert MOVED_SHA not in body
    assert "current success" not in body.lower()


@pytest.mark.asyncio
async def test_unavailable_head_publishes_bounded_stale_state() -> None:
    transport = FakeGitHubTransport()
    async with AsyncSessionLocal() as session:
        service = _service(session, transport)
        requested = await service.request_validation(
            repository_full_name=REPOSITORY,
            pull_request_number=125,
            manifest_name="validate-switchboard",
            manifest_version="1",
        )
        await _complete_with_compact_evidence(service, requested.request_id)
        transport.resolved = _resolved(
            head_sha=None,
            head_repository_full_name=None,
            head_repository_id=None,
        )

        published = await service.publish(requested.request_id)

    assert published.publication_state == "published_stale"
    assert published.publication_decision == "stale"
    assert published.publication_head_sha is None
    assert published.tested_head_sha == HEAD_SHA
    assert "github_head_unavailable" in transport.comments[0].body


@pytest.mark.asyncio
async def test_stable_identity_change_fails_closed_without_comment() -> None:
    transport = FakeGitHubTransport()
    async with AsyncSessionLocal() as session:
        service = _service(session, transport)
        requested = await service.request_validation(
            repository_full_name=REPOSITORY,
            pull_request_number=125,
            manifest_name="validate-switchboard",
            manifest_version="1",
        )
        await _complete_with_compact_evidence(service, requested.request_id)
        transport.resolved = _resolved(pull_request_id=201)

        published = await service.publish(requested.request_id)

    assert published.publication_state == "failed"
    assert published.publication_decision == "stale"
    assert published.publication_reason == "github_pr_identity_changed"
    assert transport.comments == []


@pytest.mark.asyncio
async def test_ambiguous_create_recovers_exact_marker_without_duplicate() -> None:
    transport = FakeGitHubTransport()
    transport.ambiguous_create = True
    async with AsyncSessionLocal() as session:
        service = _service(session, transport)
        requested = await service.request_validation(
            repository_full_name=REPOSITORY,
            pull_request_number=125,
            manifest_name="validate-switchboard",
            manifest_version="1",
        )
        await _complete_with_compact_evidence(service, requested.request_id)

        published = await service.publish(requested.request_id)

    assert published.publication_state == "published_current"
    assert len(transport.created_comment_ids) == 1
    assert len(transport.comments) == 1
    assert transport.updated_comment_ids == [transport.comments[0].comment_id]


@pytest.mark.asyncio
async def test_rate_limited_publication_is_retryable_without_duplicate_work() -> None:
    transport = FakeGitHubTransport()
    async with AsyncSessionLocal() as session:
        service = _service(session, transport)
        requested = await service.request_validation(
            repository_full_name=REPOSITORY,
            pull_request_number=125,
            manifest_name="validate-switchboard",
            manifest_version="1",
        )
        await _complete_with_compact_evidence(service, requested.request_id)
        transport.rate_limit_publication = True

        failed = await service.publish(requested.request_id)
        assert failed.publication_state == "retryable_failure"
        assert failed.publication_reason == "github_rate_limited"
        assert transport.comments == []

        transport.rate_limit_publication = False
        recovered = await service.publish(requested.request_id)
        request_count = await session.scalar(
            select(func.count()).select_from(GitHubValidationRequest)
        )
        work_count = await session.scalar(
            select(func.count()).select_from(ExecutionWorkOrder)
        )

    assert recovered.publication_state == "published_current"
    assert len(transport.created_comment_ids) == 1
    assert int(request_count or 0) == 1
    assert int(work_count or 0) == 1


@pytest.mark.asyncio
async def test_authenticated_api_flow_and_status_response_are_bounded(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("SWITCHBOARD_ADMIN_TOKEN", ADMIN_TOKEN)
    reload_admin_token()
    transport = FakeGitHubTransport()
    app = server_app

    def override(session: SessionDependency) -> GitHubAdapterService:
        return _service(session, transport)

    app.dependency_overrides[get_github_adapter_service] = override
    request_payload = {
        "repository_full_name": REPOSITORY,
        "pull_request_number": 125,
        "manifest": {"name": "validate-switchboard", "version": "1"},
    }
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            unauthenticated = await client.post(
                "/api/execution/github/pull-requests/validate",
                json=request_payload,
            )
            created = await client.post(
                "/api/execution/github/pull-requests/validate",
                json=request_payload,
                headers={"Authorization": f"Bearer {ADMIN_TOKEN}"},
            )
            duplicate = await client.post(
                "/api/execution/github/pull-requests/validate",
                json=request_payload,
                headers={"X-Switchboard-Admin-Token": ADMIN_TOKEN},
            )
            status = await client.get(
                f"/api/execution/github/requests/{created.json()['request_id']}",
                headers={"Authorization": f"Bearer {ADMIN_TOKEN}"},
            )
    finally:
        app.dependency_overrides.clear()
        monkeypatch.delenv("SWITCHBOARD_ADMIN_TOKEN", raising=False)
        reload_admin_token()

    assert unauthenticated.status_code == HTTPStatus.UNAUTHORIZED
    assert created.status_code == HTTPStatus.OK
    assert duplicate.status_code == HTTPStatus.OK
    assert duplicate.json()["request_id"] == created.json()["request_id"]
    assert status.status_code == HTTPStatus.OK
    payload = status.json()
    assert payload["tested_head_sha"] == HEAD_SHA
    assert payload["work_order_status"] == "pending_approval"
    assert GITHUB_TOKEN not in status.text
    forbidden_keys = {
        "token",
        "authorization",
        "response_body",
        "commands",
        "argv",
        "environment",
        "local_path",
        "artifact_locations",
    }
    assert forbidden_keys.isdisjoint(payload)


@pytest.mark.asyncio
async def test_unknown_preferred_executor_is_bounded_and_rolls_back(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("SWITCHBOARD_ADMIN_TOKEN", ADMIN_TOKEN)
    reload_admin_token()
    transport = FakeGitHubTransport()
    app = server_app
    request_session = AsyncSessionLocal()

    async def isolated_session() -> AsyncGenerator[AsyncSession, None]:
        yield request_session

    def override(session: SessionDependency) -> GitHubAdapterService:
        return _service(session, transport)

    app.dependency_overrides[get_session] = isolated_session
    app.dependency_overrides[get_github_adapter_service] = override
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app, raise_app_exceptions=False),
            base_url="http://test",
        ) as client:
            response = await client.post(
                "/api/execution/github/pull-requests/validate",
                json={
                    "repository_full_name": REPOSITORY,
                    "pull_request_number": 125,
                    "manifest": {"name": "validate-switchboard", "version": "1"},
                    "preferred_executor": "worker-not-registered",
                },
                headers={"Authorization": f"Bearer {ADMIN_TOKEN}"},
            )
        async with AsyncSessionLocal() as verification:
            request_count = await verification.scalar(
                select(func.count()).select_from(GitHubValidationRequest)
            )
            work_order_count = await verification.scalar(
                select(func.count()).select_from(ExecutionWorkOrder)
            )
    finally:
        app.dependency_overrides.clear()
        await request_session.close()
        monkeypatch.delenv("SWITCHBOARD_ADMIN_TOKEN", raising=False)
        reload_admin_token()

    assert response.status_code == HTTPStatus.NOT_FOUND
    assert response.json() == {"detail": "preferred_executor_not_found"}
    assert int(request_count or 0) == 0
    assert int(work_order_count or 0) == 0
    assert not request_session.in_transaction()
    for prohibited in (
        ADMIN_TOKEN,
        GITHUB_TOKEN,
        "ExecutionNotFoundError",
        "Traceback",
        "response_body",
        r"C:\\",
    ):
        assert prohibited not in response.text


@pytest.mark.asyncio
async def test_missing_server_token_returns_bounded_api_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("SWITCHBOARD_ADMIN_TOKEN", ADMIN_TOKEN)
    monkeypatch.delenv("SWITCHBOARD_GITHUB_TOKEN", raising=False)
    reload_admin_token()
    get_github_settings.cache_clear()
    app = server_app
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.post(
                "/api/execution/github/pull-requests/validate",
                json={
                    "repository_full_name": REPOSITORY,
                    "pull_request_number": 125,
                    "manifest": {
                        "name": "validate-switchboard",
                        "version": "1",
                    },
                },
                headers={"Authorization": f"Bearer {ADMIN_TOKEN}"},
            )
    finally:
        monkeypatch.delenv("SWITCHBOARD_ADMIN_TOKEN", raising=False)
        reload_admin_token()
        get_github_settings.cache_clear()

    assert response.status_code == HTTPStatus.SERVICE_UNAVAILABLE
    assert response.json()["detail"] == "github_token_not_configured"
    assert "github_pat" not in response.text


@pytest.mark.asyncio
async def test_api_rejects_caller_owned_injection_before_service_call(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("SWITCHBOARD_ADMIN_TOKEN", ADMIN_TOKEN)
    reload_admin_token()
    app = server_app

    def invalid_service() -> object:
        return object()

    app.dependency_overrides[get_github_adapter_service] = invalid_service
    payload = {
        "repository_full_name": REPOSITORY,
        "pull_request_number": 125,
        "manifest": {"name": "validate-switchboard", "version": "1"},
        "commands": ["python", "-c", "malicious"],
    }
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app, raise_app_exceptions=False),
            base_url="http://test",
        ) as client:
            response = await client.post(
                "/api/execution/github/pull-requests/validate",
                json=payload,
                headers={"Authorization": f"Bearer {ADMIN_TOKEN}"},
            )
    finally:
        app.dependency_overrides.clear()
        monkeypatch.delenv("SWITCHBOARD_ADMIN_TOKEN", raising=False)
        reload_admin_token()

    assert response.status_code == HTTPStatus.UNPROCESSABLE_ENTITY
