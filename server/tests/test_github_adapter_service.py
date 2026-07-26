# ruff: noqa: PLR2004
"""Persistence, idempotency, API, and publication tests for issue #122."""

from __future__ import annotations

import asyncio
import datetime as dt
import json
from collections.abc import Callable
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
)
from server.app import app as server_app
from server.application import build_execution_service
from server.db import AsyncSessionLocal
from server.execution.entities import ExecutionCompletion, WorkerRegistration
from server.execution.enums import (
    ExecutionRunStatus,
    NetworkPolicy,
    WorkerStatus,
    WorkOrderStatus,
)
from server.execution.evidence import (
    AuditSummary,
    EnvironmentIdentity,
    ExecutionEvidenceDraft,
    ParsedCoverage,
    ParsedResult,
    ParsedTestCounts,
    StepEvidence,
    finalize_evidence,
)
from server.github_adapter.errors import (
    GitHubAmbiguousWriteError,
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

    app.dependency_overrides[get_github_adapter_service] = lambda: object()
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
