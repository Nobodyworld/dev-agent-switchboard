# ruff: noqa: PLR2004
"""Persistence, idempotency, API, and publication tests for issue #122."""

from __future__ import annotations

import datetime as dt
import json
from dataclasses import asdict
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
)
from server.github_adapter.rendering import (
    has_exact_marker,
    managed_comment_marker,
)
from server.github_adapter.repository import GitHubAdapterRepository
from server.github_adapter.schemas import GitHubValidationCreateIn
from server.github_adapter.service import (
    GitHubAdapterDependencies,
    GitHubAdapterService,
)
from server.github_adapter.transport import (
    GitHubComment,
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


class FakeGitHubTransport(GitHubTransport):
    """Stateful, offline transport that exposes comment idempotency effects."""

    def __init__(self, resolved: ResolvedPullRequest | None = None) -> None:
        self.resolved = resolved or _resolved()
        self.resolve_calls = 0
        self.comments: list[GitHubComment] = []
        self.created_comment_ids: list[int] = []
        self.updated_comment_ids: list[int] = []
        self.ambiguous_create = False
        self.rate_limit_publication = False

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
    ) -> list[GitHubComment]:
        assert repository_full_name == REPOSITORY
        assert pull_request_number == 125
        if self.rate_limit_publication:
            raise GitHubRateLimitedError("github_rate_limited")
        return list(self.comments)

    async def create_comment(
        self,
        repository_full_name: str,
        pull_request_number: int,
        body: str,
    ) -> GitHubComment:
        assert repository_full_name == REPOSITORY
        assert pull_request_number == 125
        comment = GitHubComment(comment_id=500 + len(self.comments), body=body)
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
        updated = GitHubComment(comment_id=comment_id, body=body)
        for index, comment in enumerate(self.comments):
            if comment.comment_id == comment_id:
                self.comments[index] = updated
                return updated
        self.comments.append(updated)
        return updated


def _settings() -> GitHubSettings:
    return GitHubSettings(
        api_url="https://api.github.com",
        operator_id="test-operator",
        token=GITHUB_TOKEN,
    )


def _service(
    session: AsyncSession, transport: FakeGitHubTransport
) -> GitHubAdapterService:
    return GitHubAdapterService(
        dependencies=GitHubAdapterDependencies(
            repository=GitHubAdapterRepository(session),
            execution=build_execution_service(session),
            transport=transport,
        ),
        settings=_settings(),
        clock=utcnow_naive,
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

    assert transport.comments == []


@pytest.mark.asyncio
async def test_current_publication_creates_then_updates_only_persisted_comment() -> (
    None
):
    transport = FakeGitHubTransport()
    user_comment = GitHubComment(
        comment_id=41,
        body=(
            "<!-- switchboard-validation:v1:" + "0" * 64 + " -->\nuser-authored text"
        ),
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
        copied = GitHubComment(comment_id=42, body=f"{marker}\nuser copied the marker")
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
