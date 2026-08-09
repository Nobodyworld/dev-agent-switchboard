"""Real Switchboard app with synthetic completion for UI-only browser acceptance.

Worker-local execution and cryptographic reuse verification are intentionally proved by
the real ``ExecutionClient``/``LocalWorker`` acceptance in the Python client suite.
"""

from __future__ import annotations

import datetime as dt

from fastapi import HTTPException

from server.api.dependencies import SessionDependency, get_github_adapter_service
from server.app import app
from server.application import build_execution_service
from server.execution.entities import ExecutionCompletion
from server.execution.enums import ExecutionRunStatus, ReuseDecision
from server.execution.evidence import (
    DependencyLockHash,
    EnvironmentIdentity,
    EvidenceReuseIdentity,
    EvidenceReuseProvenance,
    ExecutionEvidenceDraft,
    compute_result_contract_hash,
    compute_reuse_identity_hash,
    finalize_evidence,
)
from server.execution.registry import get_trusted_manifest
from server.github_adapter.repository import GitHubAdapterRepository
from server.github_adapter.service import (
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
from server.settings import GitHubSettings
from server.time_utils import utcnow_naive

REPOSITORY = "Nobodyworld/dev-agent-switchboard"
INITIAL_HEAD = "7d3a91c" + "0" * 33
BASE_SHA = "223df77" + "0" * 33
CHEAP_WORKER = "ui-worker-cheap"
EXPENSIVE_WORKER = "ui-worker-expensive"
SHA1_HEX_LENGTH = 40


class OfflineGitHubTransport(GitHubTransport):
    """Minimal stateful transport that never performs network I/O."""

    def __init__(self) -> None:
        self.head_sha = INITIAL_HEAD
        self.comments: list[GitHubComment] = []
        self.actor = GitHubActorIdentity(actor_id=700, node_id="U_ui_operator")

    async def resolve_authenticated_actor(self) -> GitHubActorIdentity:
        return self.actor

    async def resolve_pull_request(
        self,
        repository_full_name: str,
        pull_request_number: int,
        *,
        require_head: bool = True,
    ) -> ResolvedPullRequest:
        _ = require_head
        return ResolvedPullRequest(
            repository_full_name=repository_full_name,
            repository_id=100,
            repository_node_id="R_ui_repo",
            pull_request_number=pull_request_number,
            pull_request_id=200,
            pull_request_node_id="PR_ui_request",
            state="open",
            draft=True,
            merged=False,
            base_ref="main",
            base_sha=BASE_SHA,
            head_ref="feat/operator-validation-command-center",
            head_sha=self.head_sha,
            head_repository_full_name=repository_full_name,
            head_repository_id=100,
        )

    async def list_comments(
        self, repository_full_name: str, pull_request_number: int
    ) -> GitHubCommentListing:
        return GitHubCommentListing(
            comments=tuple(
                comment
                for comment in self.comments
                if comment.repository_full_name == repository_full_name
                and comment.pull_request_number == pull_request_number
            ),
            complete=True,
        )

    async def get_comment(
        self, repository_full_name: str, comment_id: int
    ) -> GitHubComment:
        for comment in self.comments:
            if (
                comment.repository_full_name == repository_full_name
                and comment.comment_id == comment_id
            ):
                return comment
        raise AssertionError("offline UI transport comment not found")

    async def create_comment(
        self,
        repository_full_name: str,
        pull_request_number: int,
        body: str,
    ) -> GitHubComment:
        comment = GitHubComment(
            comment_id=500 + len(self.comments),
            body=body,
            author=self.actor,
            repository_full_name=repository_full_name,
            pull_request_number=pull_request_number,
        )
        self.comments.append(comment)
        return comment

    async def update_comment(
        self,
        repository_full_name: str,
        comment_id: int,
        body: str,
    ) -> GitHubComment:
        current = await self.get_comment(repository_full_name, comment_id)
        updated = GitHubComment(
            comment_id=current.comment_id,
            body=body,
            author=current.author,
            repository_full_name=current.repository_full_name,
            pull_request_number=current.pull_request_number,
        )
        self.comments[self.comments.index(current)] = updated
        return updated


offline_transport = OfflineGitHubTransport()
offline_settings = GitHubSettings(
    api_url="https://api.github.com",
    operator_id="synthetic-ui-operator",
    token="offline-ui-placeholder",  # noqa: S106
)


def get_offline_github_adapter(session: SessionDependency) -> GitHubAdapterService:
    """Build the real adapter around a stateful no-network transport."""

    return GitHubAdapterService(
        dependencies=GitHubAdapterDependencies(
            repository=GitHubAdapterRepository(session),
            execution=build_execution_service(session),
            transport=offline_transport,
        ),
        settings=offline_settings,
        clock=utcnow_naive,
    )


app.dependency_overrides[get_github_adapter_service] = get_offline_github_adapter


def _identity(order) -> EvidenceReuseIdentity:
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


def _evidence(  # noqa: PLR0913
    *,
    order,
    run_id: int,
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
            worker_id=CHEAP_WORKER,
            environment=EnvironmentIdentity(
                operating_system="linux",
                architecture="x86_64",
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


@app.post("/__test__/github/head/{sha}")
async def set_offline_head(sha: str) -> dict[str, str]:
    if len(sha) != SHA1_HEX_LENGTH or any(
        character not in "0123456789abcdef" for character in sha
    ):
        raise HTTPException(status_code=422, detail="invalid_test_sha")
    offline_transport.head_sha = sha
    return {"head_sha": sha}


@app.post("/__test__/complete/{request_id}")
async def complete_offline_validation(
    request_id: int, session: SessionDependency
) -> dict[str, object]:
    request = await GitHubAdapterRepository(session).get(request_id)
    if request is None:
        raise HTTPException(status_code=404, detail="github_request_not_found")
    execution = build_execution_service(session)
    await execution.checkout(EXPENSIVE_WORKER)
    assignment = await execution.checkout(CHEAP_WORKER)
    if assignment.run_id is None:
        raise HTTPException(status_code=409, detail=assignment.reason or "not_assigned")
    await execution.heartbeat_run(assignment.run_id, worker_id=CHEAP_WORKER)
    order = await execution.get_work_order(request.work_order_id)
    identity = _identity(order)
    identity_hash = compute_reuse_identity_hash(identity)
    decision = ReuseDecision.FRESH
    source_run_id = None
    source_fingerprint = None
    if order.reuse_policy.value != "never":
        lookup = await execution.resolve_reuse_candidate(
            assignment.run_id,
            worker_id=CHEAP_WORKER,
            reuse_identity=identity,
            reuse_identity_hash=identity_hash,
        )
        if lookup.candidate is None:
            raise HTTPException(status_code=409, detail=lookup.reason)
        decision = ReuseDecision.REUSED
        source_run_id = lookup.candidate.source_run_id
        source_fingerprint = lookup.candidate.expected_source_evidence_fingerprint
    evidence = _evidence(
        order=order,
        run_id=assignment.run_id,
        identity=identity,
        decision=decision.value,
        source_run_id=source_run_id,
        source_fingerprint=source_fingerprint,
    )
    run = await execution.complete_run(
        assignment.run_id,
        worker_id=CHEAP_WORKER,
        completion=ExecutionCompletion(
            status=ExecutionRunStatus.SUCCEEDED,
            evidence_metadata=evidence,
            reuse_decision=decision,
            reuse_reason=(
                "exact_evidence_verified"
                if decision == ReuseDecision.REUSED
                else "fresh_execution_completed"
            ),
            reuse_identity=identity,
            reuse_identity_hash=identity_hash,
            evidence_retention_expires_at=(evidence.started_at + dt.timedelta(days=14)),
        ),
    )
    if decision == ReuseDecision.FRESH:
        run.started_at = dt.datetime(2026, 8, 8, 12, 0, 0, tzinfo=dt.UTC)
        run.finished_at = dt.datetime(2026, 8, 8, 12, 0, 7, tzinfo=dt.UTC)
    await session.commit()
    return {
        "run_id": run.id,
        "reuse_decision": decision.value,
        "evidence_fingerprint": evidence.fingerprint,
    }
