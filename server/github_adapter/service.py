"""Server-owned exact-PR request, status, and publication workflow."""

from __future__ import annotations

import datetime as dt
import hashlib
import json
from collections.abc import Callable
from dataclasses import dataclass

from sqlalchemy.exc import IntegrityError

from server.execution.entities import WorkOrderDraft
from server.execution.enums import ApprovalPolicy, is_terminal_run
from server.execution.evidence import ExecutionEvidence
from server.execution.exceptions import ExecutionNotFoundError, MalformedEvidenceError
from server.execution.registry import (
    TRUSTED_REPOSITORIES,
    get_trusted_manifest,
)
from server.execution.service import ExecutionService
from server.models import ExecutionRun, GitHubValidationRequest
from server.settings import GitHubSettings

from .errors import (
    GitHubAdapterError,
    GitHubAmbiguousWriteError,
    GitHubManifestError,
    GitHubRepositoryNotAllowedError,
    GitHubRequestNotFoundError,
    GitHubTerminalEvidenceRequiredError,
    GitHubTransportError,
)
from .rendering import (
    has_exact_marker,
    managed_comment_marker,
    render_managed_comment,
)
from .repository import GitHubAdapterRepository
from .transport import GitHubComment, GitHubTransport, ResolvedPullRequest

GITHUB_ADAPTER_SCHEMA_VERSION = 1


@dataclass(frozen=True, slots=True)
class GitHubRequestStatus:
    """Bounded adapter provenance and linked execution lifecycle."""

    request_id: int
    schema_version: int
    github_host: str
    repository_full_name: str
    repository_id: int
    repository_node_id: str
    pull_request_number: int
    pull_request_id: int
    pull_request_node_id: str
    pull_request_state: str
    pull_request_draft: bool
    pull_request_merged: bool
    tested_head_sha: str
    base_sha: str
    manifest_name: str
    manifest_version: str
    manifest_digest: str
    operator_id: str
    work_order_id: int
    work_order_status: str
    terminal_run_id: int | None
    terminal_run_status: str | None
    evidence_fingerprint: str | None
    managed_comment_id: int | None
    publication_state: str
    publication_decision: str
    publication_head_sha: str | None
    transport_reason: str | None
    publication_reason: str | None
    created_at: dt.datetime
    updated_at: dt.datetime
    last_resolved_at: dt.datetime
    last_publication_attempt_at: dt.datetime | None
    published_at: dt.datetime | None


class GitHubAdapterService:
    """Resolve immutable GitHub identity into the existing execution plane."""

    def __init__(
        self,
        *,
        repository: GitHubAdapterRepository,
        execution: ExecutionService,
        transport: GitHubTransport,
        settings: GitHubSettings,
        clock: Callable[[], dt.datetime],
    ) -> None:
        self._repository = repository
        self._execution = execution
        self._transport = transport
        self._settings = settings
        self._clock = clock

    async def request_validation(
        self,
        *,
        repository_full_name: str,
        pull_request_number: int,
        manifest_name: str,
        manifest_version: str,
    ) -> GitHubRequestStatus:
        """Create or return one pending work order for the exact resolved head."""

        if repository_full_name not in TRUSTED_REPOSITORIES:
            raise GitHubRepositoryNotAllowedError("github_repository_not_allowed")
        manifest = get_trusted_manifest(manifest_name, manifest_version)
        if manifest is None:
            raise GitHubManifestError("trusted_manifest_not_found")
        resolved = await self._transport.resolve_pull_request(
            repository_full_name, pull_request_number, require_head=True
        )
        if (
            resolved.repository_full_name.casefold()
            != repository_full_name.casefold()
            or resolved.head_sha is None
            or resolved.head_repository_full_name is None
            or resolved.head_repository_id is None
        ):
            raise GitHubTransportError("github_transport_failed")
        idempotency_key = _idempotency_key(
            settings=self._settings,
            resolved=resolved,
            manifest_name=manifest.name,
            manifest_version=manifest.version,
            manifest_digest=manifest.digest,
        )
        existing = await self._repository.get_by_idempotency_key(idempotency_key)
        if existing is not None:
            return await self._status(existing)

        now = self._clock()
        try:
            async with self._repository.session.begin_nested():
                work_order = await self._execution.create_work_order(
                    WorkOrderDraft(
                        schema_version=1,
                        repository_full_name=repository_full_name,
                        commit_sha=resolved.head_sha,
                        manifest_name=manifest.name,
                        manifest_version=manifest.version,
                        manifest_parameters={},
                        required_capabilities=dict(manifest.required_capabilities),
                        permitted_paths=(),
                        forbidden_scope_notes=(
                            "GitHub resolved identity only; canonical repository "
                            "remains read-only and the exact commit must exist locally."
                        ),
                        expected_artifact_kinds=tuple(
                            dict.fromkeys(
                                str(item["kind"])
                                for item in manifest.artifact_declarations
                            )
                        ),
                        approval_policy=ApprovalPolicy.EXPLICIT,
                        timeout_seconds=manifest.timeout_seconds,
                        resource_metadata={},
                        network_policy=manifest.network_policy,
                        repository_write_allowed=False,
                        preferred_executor="local",
                        cost_ceiling=0.0,
                    )
                )
                request = await self._repository.create(
                    {
                        "schema_version": GITHUB_ADAPTER_SCHEMA_VERSION,
                        "idempotency_key": idempotency_key,
                        "github_api_url": self._settings.api_url,
                        "github_host": self._settings.host,
                        "repository_full_name": repository_full_name,
                        "repository_id": resolved.repository_id,
                        "repository_node_id": resolved.repository_node_id,
                        "pull_request_number": resolved.pull_request_number,
                        "pull_request_id": resolved.pull_request_id,
                        "pull_request_node_id": resolved.pull_request_node_id,
                        "pull_request_state": resolved.state,
                        "pull_request_draft": resolved.draft,
                        "pull_request_merged": resolved.merged,
                        "base_ref": resolved.base_ref,
                        "base_sha": resolved.base_sha,
                        "head_ref": resolved.head_ref,
                        "head_sha": resolved.head_sha,
                        "head_repository_full_name": (
                            resolved.head_repository_full_name
                        ),
                        "head_repository_id": resolved.head_repository_id,
                        "manifest_name": manifest.name,
                        "manifest_version": manifest.version,
                        "manifest_digest": manifest.digest,
                        "operator_id": self._settings.operator_id,
                        "work_order_id": work_order.id,
                        "publication_state": "not_published",
                        "publication_decision": "not_evaluated",
                        "last_transport_reason": "github_pr_resolved",
                        "last_resolved_at": now,
                    }
                )
        except IntegrityError:
            recovered = await self._repository.get_by_idempotency_key(
                idempotency_key, refresh=True
            )
            if recovered is None:
                raise
            request = recovered
        return await self._status(request)

    async def get_status(self, request_id: int) -> GitHubRequestStatus:
        """Return bounded provenance and execution/publication lifecycle only."""

        request = await self._get_request(request_id)
        return await self._status(request)

    async def publish(self, request_id: int) -> GitHubRequestStatus:
        """Recheck the exact head and create or update one managed comment."""

        request = await self._get_request(request_id)
        run, evidence = await self._terminal_evidence(request)
        request.terminal_run_id = run.id
        request.last_publication_attempt_at = self._clock()
        await self._repository.flush()

        try:
            resolved = await self._transport.resolve_pull_request(
                request.repository_full_name,
                request.pull_request_number,
                require_head=False,
            )
        except GitHubAdapterError as error:
            request.last_transport_reason = str(error)
            request.publication_reason = str(error)
            request.publication_state = "retryable_failure"
            if str(error) in {
                "github_pr_not_found",
                "github_repository_not_found",
                "github_head_unavailable",
            }:
                request.publication_decision = "stale"
            await self._repository.flush()
            return await self._status(request)

        now = self._clock()
        request.last_resolved_at = now
        request.last_transport_reason = "github_pr_resolved"
        request.publication_head_sha = resolved.head_sha
        if not _same_stable_identity(request, resolved):
            request.publication_state = "failed"
            request.publication_decision = "stale"
            request.publication_reason = "github_pr_identity_changed"
            await self._repository.flush()
            return await self._status(request)

        decision = "current"
        decision_reason = "github_pr_resolved"
        if resolved.head_sha is None:
            decision = "stale"
            decision_reason = "github_head_unavailable"
        elif resolved.head_sha != request.head_sha:
            decision = "stale"
            decision_reason = "github_head_changed"
        request.publication_decision = decision

        try:
            body = render_managed_comment(
                request,
                evidence,
                decision=decision,
                decision_reason=decision_reason,
            )
            comment = await self._upsert_managed_comment(request, body)
        except GitHubAdapterError as error:
            request.publication_state = "retryable_failure"
            request.publication_reason = str(error)
            await self._repository.flush()
            return await self._status(request)
        except ValueError:
            request.publication_state = "failed"
            request.publication_reason = "github_publication_failed"
            await self._repository.flush()
            return await self._status(request)

        request.managed_comment_id = comment.comment_id
        request.publication_state = (
            "published_current" if decision == "current" else "published_stale"
        )
        request.publication_reason = (
            "github_publication_succeeded"
            if decision == "current"
            else "github_publication_stale"
        )
        request.published_at = self._clock()
        await self._repository.flush()
        return await self._status(request)

    async def _upsert_managed_comment(
        self, request: GitHubValidationRequest, body: str
    ) -> GitHubComment:
        marker = managed_comment_marker(request.idempotency_key)
        comments = await self._transport.list_comments(
            request.repository_full_name, request.pull_request_number
        )
        persisted = next(
            (
                comment
                for comment in comments
                if comment.comment_id == request.managed_comment_id
            ),
            None,
        )
        if persisted is not None and not has_exact_marker(persisted.body, marker):
            # A corrupted persisted ID must never authorize editing remote user text.
            request.managed_comment_id = None
        exact = next(
            (comment for comment in comments if has_exact_marker(comment.body, marker)),
            None,
        )
        target_id = request.managed_comment_id
        if target_id is None and exact is not None:
            target_id = exact.comment_id
        if target_id is not None:
            updated = await self._transport.update_comment(
                request.repository_full_name, target_id, body
            )
            if not has_exact_marker(updated.body, marker):
                raise GitHubTransportError("github_publication_failed")
            return updated

        try:
            created = await self._transport.create_comment(
                request.repository_full_name,
                request.pull_request_number,
                body,
            )
        except GitHubAmbiguousWriteError:
            recovered_comments = await self._transport.list_comments(
                request.repository_full_name, request.pull_request_number
            )
            recovered = next(
                (
                    comment
                    for comment in recovered_comments
                    if has_exact_marker(comment.body, marker)
                ),
                None,
            )
            if recovered is None:
                raise
            created = await self._transport.update_comment(
                request.repository_full_name, recovered.comment_id, body
            )
        if not has_exact_marker(created.body, marker):
            raise GitHubTransportError("github_publication_failed")
        return created

    async def _get_request(self, request_id: int) -> GitHubValidationRequest:
        request = await self._repository.get(request_id)
        if request is None:
            raise GitHubRequestNotFoundError("github_request_not_found")
        return request

    async def _terminal_evidence(
        self, request: GitHubValidationRequest
    ) -> tuple[ExecutionRun, ExecutionEvidence]:
        runs = await self._execution.list_runs(request.work_order_id)
        for run in reversed(runs):
            if not is_terminal_run(run.status):
                continue
            try:
                evidence = await self._execution.get_run_evidence(run.id)
            except (ExecutionNotFoundError, MalformedEvidenceError):
                continue
            return run, evidence
        raise GitHubTerminalEvidenceRequiredError(
            "github_terminal_evidence_required"
        )

    async def _status(
        self, request: GitHubValidationRequest
    ) -> GitHubRequestStatus:
        work_order = await self._execution.get_work_order(request.work_order_id)
        runs = await self._execution.list_runs(request.work_order_id)
        run = next(
            (item for item in runs if item.id == request.terminal_run_id),
            runs[-1] if runs else None,
        )
        fingerprint: str | None = None
        if run is not None and run.evidence_metadata:
            try:
                fingerprint = (
                    await self._execution.get_run_evidence(run.id)
                ).fingerprint
            except (ExecutionNotFoundError, MalformedEvidenceError):
                fingerprint = None
        return GitHubRequestStatus(
            request_id=request.id,
            schema_version=request.schema_version,
            github_host=request.github_host,
            repository_full_name=request.repository_full_name,
            repository_id=request.repository_id,
            repository_node_id=request.repository_node_id,
            pull_request_number=request.pull_request_number,
            pull_request_id=request.pull_request_id,
            pull_request_node_id=request.pull_request_node_id,
            pull_request_state=request.pull_request_state,
            pull_request_draft=request.pull_request_draft,
            pull_request_merged=request.pull_request_merged,
            tested_head_sha=request.head_sha,
            base_sha=request.base_sha,
            manifest_name=request.manifest_name,
            manifest_version=request.manifest_version,
            manifest_digest=request.manifest_digest,
            operator_id=request.operator_id,
            work_order_id=request.work_order_id,
            work_order_status=work_order.status.value,
            terminal_run_id=run.id if run is not None else None,
            terminal_run_status=(
                run.status.value if run is not None else None
            ),
            evidence_fingerprint=fingerprint,
            managed_comment_id=request.managed_comment_id,
            publication_state=request.publication_state,
            publication_decision=request.publication_decision,
            publication_head_sha=request.publication_head_sha,
            transport_reason=request.last_transport_reason,
            publication_reason=request.publication_reason,
            created_at=request.created_at,
            updated_at=request.updated_at,
            last_resolved_at=request.last_resolved_at,
            last_publication_attempt_at=request.last_publication_attempt_at,
            published_at=request.published_at,
        )


def _idempotency_key(
    *,
    settings: GitHubSettings,
    resolved: ResolvedPullRequest,
    manifest_name: str,
    manifest_version: str,
    manifest_digest: str,
) -> str:
    if resolved.head_sha is None:  # pragma: no cover - request requires it
        raise GitHubTransportError("github_head_unavailable")
    payload = {
        "github_api_url": settings.api_url,
        "manifest_digest": manifest_digest,
        "manifest_name": manifest_name,
        "manifest_version": manifest_version,
        "pull_request_id": resolved.pull_request_id,
        "pull_request_node_id": resolved.pull_request_node_id,
        "repository_id": resolved.repository_id,
        "repository_node_id": resolved.repository_node_id,
        "schema_version": GITHUB_ADAPTER_SCHEMA_VERSION,
        "tested_head_sha": resolved.head_sha,
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _same_stable_identity(
    request: GitHubValidationRequest, resolved: ResolvedPullRequest
) -> bool:
    return (
        request.repository_id == resolved.repository_id
        and request.repository_node_id == resolved.repository_node_id
        and request.pull_request_id == resolved.pull_request_id
        and request.pull_request_node_id == resolved.pull_request_node_id
        and request.pull_request_number == resolved.pull_request_number
    )


__all__ = [
    "GITHUB_ADAPTER_SCHEMA_VERSION",
    "GitHubAdapterService",
    "GitHubRequestStatus",
]
