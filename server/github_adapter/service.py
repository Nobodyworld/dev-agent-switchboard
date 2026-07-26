"""Server-owned exact-PR request, status, and publication workflow."""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import secrets
from collections.abc import Callable
from dataclasses import dataclass

from sqlalchemy.exc import IntegrityError

from server.execution.entities import WorkOrderDraft
from server.execution.enums import ApprovalPolicy, is_terminal_run
from server.execution.evidence import ExecutionEvidence
from server.execution.exceptions import ExecutionNotFoundError, MalformedEvidenceError
from server.execution.registry import (
    TRUSTED_REPOSITORIES,
    TrustedManifest,
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
from .transport import (
    GitHubActorIdentity,
    GitHubComment,
    GitHubTransport,
    ResolvedPullRequest,
)

GITHUB_ADAPTER_SCHEMA_VERSION = 1
PUBLICATION_CLAIM_TTL = dt.timedelta(minutes=5)


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


@dataclass(frozen=True, slots=True)
class GitHubAdapterDependencies:
    """Server-owned collaborators used by the GitHub adapter service."""

    repository: GitHubAdapterRepository
    execution: ExecutionService
    transport: GitHubTransport


class GitHubAdapterService:
    """Resolve immutable GitHub identity into the existing execution plane."""

    def __init__(
        self,
        *,
        dependencies: GitHubAdapterDependencies,
        settings: GitHubSettings,
        clock: Callable[[], dt.datetime],
    ) -> None:
        self._repository = dependencies.repository
        self._execution = dependencies.execution
        self._transport = dependencies.transport
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
        actor = await self._transport.resolve_authenticated_actor()
        resolved = await self._transport.resolve_pull_request(
            repository_full_name, pull_request_number, require_head=True
        )
        if (
            resolved.repository_full_name.casefold() != repository_full_name.casefold()
            or resolved.head_sha is None
            or resolved.head_repository_full_name is None
            or resolved.head_repository_id is None
        ):
            raise GitHubTransportError("github_transport_failed")
        idempotency_key = _idempotency_key(
            settings=self._settings,
            actor=actor,
            resolved=resolved,
            manifest=manifest,
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
                        "github_actor_id": actor.actor_id,
                        "github_actor_node_id": actor.node_id,
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
        persisted_request_id = request.id
        claim_token = secrets.token_hex(32)
        claimed_at = self._clock()
        acquired = await self._repository.acquire_publication_claim(
            persisted_request_id,
            token=claim_token,
            claimed_at=claimed_at,
            expires_at=claimed_at + PUBLICATION_CLAIM_TTL,
        )
        request = await self._get_request(persisted_request_id, refresh=True)
        if not acquired:
            return await self._status(
                request,
                publication_reason_override="github_publication_in_progress",
            )
        try:
            return await self._publish_claimed(request, claim_token)
        except GitHubAdapterError as error:
            await self._repository.finalize_publication_claim(
                persisted_request_id,
                token=claim_token,
                values={
                    "publication_reason": str(error),
                    "publication_state": "retryable_failure",
                },
            )
            raise
        except Exception:
            await self._repository.finalize_publication_claim(
                persisted_request_id,
                token=claim_token,
                values={
                    "publication_reason": "github_publication_failed",
                    "publication_state": "retryable_failure",
                },
            )
            raise

    async def _publish_claimed(  # noqa: PLR0911
        self,
        request: GitHubValidationRequest,
        claim_token: str,
    ) -> GitHubRequestStatus:
        """Publish while all persistence writes are fenced by one claim token."""

        run, evidence = await self._terminal_evidence(request)
        run_id = run.id
        try:
            actor = await self._transport.resolve_authenticated_actor()
        except GitHubAdapterError as error:
            reason = (
                "github_rate_limited"
                if str(error) == "github_rate_limited"
                else "github_actor_resolution_failed"
            )
            return await self._finalize_claim(
                request,
                claim_token,
                {
                    "terminal_run_id": run_id,
                    "last_transport_reason": reason,
                    "publication_reason": reason,
                    "publication_state": "retryable_failure",
                },
            )
        actor_identity_reason = _actor_identity_failure_reason(request, actor)
        if actor_identity_reason is not None:
            return await self._finalize_claim(
                request,
                claim_token,
                {
                    "terminal_run_id": run_id,
                    "last_transport_reason": actor_identity_reason,
                    "publication_reason": actor_identity_reason,
                    "publication_state": "failed",
                },
            )

        try:
            resolved = await self._transport.resolve_pull_request(
                request.repository_full_name,
                request.pull_request_number,
                require_head=False,
            )
        except GitHubAdapterError as error:
            values: dict[str, object] = {
                "terminal_run_id": run_id,
                "last_transport_reason": str(error),
                "publication_reason": str(error),
                "publication_state": "retryable_failure",
            }
            if str(error) in {
                "github_pr_not_found",
                "github_repository_not_found",
                "github_head_unavailable",
            }:
                values["publication_decision"] = "stale"
            return await self._finalize_claim(request, claim_token, values)

        now = self._clock()
        if not _same_stable_identity(request, resolved):
            return await self._finalize_claim(
                request,
                claim_token,
                {
                    "terminal_run_id": run_id,
                    "last_resolved_at": now,
                    "last_transport_reason": "github_pr_resolved",
                    "publication_head_sha": resolved.head_sha,
                    "publication_state": "failed",
                    "publication_decision": "stale",
                    "publication_reason": "github_pr_identity_changed",
                },
            )

        decision = "current"
        decision_reason = "github_pr_resolved"
        if resolved.head_sha is None:
            decision = "stale"
            decision_reason = "github_head_unavailable"
        elif resolved.head_sha != request.head_sha:
            decision = "stale"
            decision_reason = "github_head_changed"

        try:
            body = render_managed_comment(
                request,
                evidence,
                decision=decision,
                decision_reason=decision_reason,
            )
            comment = await self._upsert_managed_comment(
                request,
                body,
                actor=actor,
                claim_token=claim_token,
            )
        except GitHubAdapterError as error:
            return await self._finalize_claim(
                request,
                claim_token,
                {
                    "terminal_run_id": run_id,
                    "last_resolved_at": now,
                    "last_transport_reason": "github_pr_resolved",
                    "publication_head_sha": resolved.head_sha,
                    "publication_decision": decision,
                    "publication_state": "retryable_failure",
                    "publication_reason": str(error),
                },
            )
        except ValueError:
            return await self._finalize_claim(
                request,
                claim_token,
                {
                    "terminal_run_id": run_id,
                    "last_resolved_at": now,
                    "last_transport_reason": "github_pr_resolved",
                    "publication_head_sha": resolved.head_sha,
                    "publication_decision": decision,
                    "publication_state": "failed",
                    "publication_reason": "github_publication_failed",
                },
            )

        return await self._finalize_claim(
            request,
            claim_token,
            {
                "terminal_run_id": run_id,
                "managed_comment_id": comment.comment_id,
                "last_resolved_at": now,
                "last_transport_reason": "github_pr_resolved",
                "publication_head_sha": resolved.head_sha,
                "publication_decision": decision,
                "publication_state": (
                    "published_current" if decision == "current" else "published_stale"
                ),
                "publication_reason": (
                    "github_publication_succeeded"
                    if decision == "current"
                    else "github_publication_stale"
                ),
                "published_at": self._clock(),
            },
        )

    async def _finalize_claim(
        self,
        request: GitHubValidationRequest,
        claim_token: str,
        values: dict[str, object],
    ) -> GitHubRequestStatus:
        request_id = request.id
        finalized = await self._repository.finalize_publication_claim(
            request_id,
            token=claim_token,
            values=values,
        )
        current = await self._get_request(request_id, refresh=True)
        if not finalized and current.publication_claim_token is not None:
            return await self._status(
                current,
                publication_reason_override="github_publication_in_progress",
            )
        return await self._status(current)

    async def _upsert_managed_comment(
        self,
        request: GitHubValidationRequest,
        body: str,
        *,
        actor: GitHubActorIdentity | None = None,
        claim_token: str | None = None,
    ) -> GitHubComment:
        marker = managed_comment_marker(request.idempotency_key)
        actor = actor or await self._transport.resolve_authenticated_actor()
        if not _same_actor_identity(request, actor):
            raise GitHubTransportError("github_actor_mismatch")

        if request.managed_comment_id is not None:
            try:
                persisted = await self._transport.get_comment(
                    request.repository_full_name, request.managed_comment_id
                )
            except GitHubTransportError as error:
                if str(error) != "github_comment_not_found":
                    raise
            else:
                if _is_owned_managed_comment(
                    persisted,
                    actor=actor,
                    request=request,
                    marker=marker,
                    expected_comment_id=request.managed_comment_id,
                ):
                    return await self._update_verified_comment(
                        request=request,
                        actor=actor,
                        comment=persisted,
                        marker=marker,
                        body=body,
                        claim_token=claim_token,
                    )

        recovered = await self._unique_owned_recovery_candidate(
            request=request,
            actor=actor,
            marker=marker,
        )
        if recovered is not None:
            return await self._update_verified_comment(
                request=request,
                actor=actor,
                comment=recovered,
                marker=marker,
                body=body,
                claim_token=claim_token,
            )

        await self._renew_claim_for_write(request, claim_token)
        try:
            created = await self._transport.create_comment(
                request.repository_full_name,
                request.pull_request_number,
                body,
            )
        except GitHubAmbiguousWriteError:
            recovered = await self._unique_owned_recovery_candidate(
                request=request,
                actor=actor,
                marker=marker,
            )
            if recovered is None:
                raise
            return await self._update_verified_comment(
                request=request,
                actor=actor,
                comment=recovered,
                marker=marker,
                body=body,
                claim_token=claim_token,
            )
        if not _is_owned_managed_comment(
            created,
            actor=actor,
            request=request,
            marker=marker,
        ):
            raise GitHubTransportError("github_publication_failed")
        return created

    async def _unique_owned_recovery_candidate(
        self,
        *,
        request: GitHubValidationRequest,
        actor: GitHubActorIdentity,
        marker: str,
    ) -> GitHubComment | None:
        listing = await self._transport.list_comments(
            request.repository_full_name, request.pull_request_number
        )
        candidates = [
            comment
            for comment in listing.comments
            if _is_owned_managed_comment(
                comment,
                actor=actor,
                request=request,
                marker=marker,
            )
        ]
        if len(candidates) > 1:
            raise GitHubTransportError("github_comment_recovery_ambiguous")
        if not listing.complete:
            raise GitHubTransportError("github_comment_recovery_unverifiable")
        if not candidates:
            return None
        return candidates[0]

    async def _update_verified_comment(  # noqa: PLR0913
        self,
        *,
        request: GitHubValidationRequest,
        actor: GitHubActorIdentity,
        comment: GitHubComment,
        marker: str,
        body: str,
        claim_token: str | None,
    ) -> GitHubComment:
        verified = await self._transport.get_comment(
            request.repository_full_name, comment.comment_id
        )
        if not _is_owned_managed_comment(
            verified,
            actor=actor,
            request=request,
            marker=marker,
            expected_comment_id=comment.comment_id,
        ):
            raise GitHubTransportError("github_publication_failed")
        await self._renew_claim_for_write(request, claim_token)
        updated = await self._transport.update_comment(
            request.repository_full_name, comment.comment_id, body
        )
        if not _is_owned_managed_comment(
            updated,
            actor=actor,
            request=request,
            marker=marker,
            expected_comment_id=comment.comment_id,
        ):
            raise GitHubTransportError("github_publication_failed")
        return updated

    async def _renew_claim_for_write(
        self,
        request: GitHubValidationRequest,
        claim_token: str | None,
    ) -> None:
        if claim_token is None:
            return
        now = self._clock()
        renewed = await self._repository.renew_publication_claim(
            request.id,
            token=claim_token,
            renewed_at=now,
            expires_at=now + PUBLICATION_CLAIM_TTL,
        )
        if not renewed:
            raise GitHubTransportError("github_publication_claim_lost")

    async def _get_request(
        self,
        request_id: int,
        *,
        refresh: bool = False,
    ) -> GitHubValidationRequest:
        request = await self._repository.get(request_id, refresh=refresh)
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
        raise GitHubTerminalEvidenceRequiredError("github_terminal_evidence_required")

    async def _status(
        self,
        request: GitHubValidationRequest,
        *,
        publication_reason_override: str | None = None,
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
            terminal_run_status=(run.status.value if run is not None else None),
            evidence_fingerprint=fingerprint,
            managed_comment_id=request.managed_comment_id,
            publication_state=request.publication_state,
            publication_decision=request.publication_decision,
            publication_head_sha=request.publication_head_sha,
            transport_reason=request.last_transport_reason,
            publication_reason=(
                publication_reason_override or request.publication_reason
            ),
            created_at=request.created_at,
            updated_at=request.updated_at,
            last_resolved_at=request.last_resolved_at,
            last_publication_attempt_at=request.last_publication_attempt_at,
            published_at=request.published_at,
        )


def _idempotency_key(
    *,
    settings: GitHubSettings,
    actor: GitHubActorIdentity,
    resolved: ResolvedPullRequest,
    manifest: TrustedManifest,
) -> str:
    if resolved.head_sha is None:  # pragma: no cover - request requires it
        raise GitHubTransportError("github_head_unavailable")
    payload = {
        "github_api_url": settings.api_url,
        "github_actor_id": actor.actor_id,
        "github_actor_node_id": actor.node_id,
        "manifest_digest": manifest.digest,
        "manifest_name": manifest.name,
        "manifest_version": manifest.version,
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


def _same_actor_identity(
    request: GitHubValidationRequest,
    actor: GitHubActorIdentity,
) -> bool:
    return (
        request.github_actor_id == actor.actor_id
        and request.github_actor_node_id == actor.node_id
    )


def _actor_identity_failure_reason(
    request: GitHubValidationRequest,
    actor: GitHubActorIdentity,
) -> str | None:
    if request.github_actor_id is None or request.github_actor_node_id is None:
        return "github_actor_identity_missing"
    if not _same_actor_identity(request, actor):
        return "github_actor_mismatch"
    return None


def _is_owned_managed_comment(
    comment: GitHubComment,
    *,
    actor: GitHubActorIdentity,
    request: GitHubValidationRequest,
    marker: str,
    expected_comment_id: int | None = None,
) -> bool:
    return (
        comment.author == actor
        and comment.repository_full_name.casefold()
        == request.repository_full_name.casefold()
        and comment.pull_request_number == request.pull_request_number
        and has_exact_marker(comment.body, marker)
        and (expected_comment_id is None or comment.comment_id == expected_comment_id)
    )


__all__ = [
    "GITHUB_ADAPTER_SCHEMA_VERSION",
    "PUBLICATION_CLAIM_TTL",
    "GitHubAdapterService",
    "GitHubRequestStatus",
]
