"""Validated lifecycle service for persisted execution-plane contracts."""

from __future__ import annotations

import datetime as dt
import re
from collections.abc import Callable, Mapping
from dataclasses import dataclass

from sqlalchemy.exc import IntegrityError

from server.models import (
    CommandManifest,
    ExecutionRun,
    ExecutionWorker,
    ExecutionWorkOrder,
    WorkerRoutingProfile,
)

from .catalog import (
    TRUSTED_REPOSITORIES,
    TrustedRepository,
    iter_trusted_repositories,
    repository_allows_manifest,
)
from .entities import (
    CheckoutResult,
    ExecutionCompletion,
    ExpiryResult,
    ReuseCandidateResult,
    RouteAssessment,
    RoutingProfileDraft,
    RoutingProfileReplacement,
    RoutingQuotaReset,
    WorkerRegistration,
    WorkOrderDraft,
)
from .enums import (
    ApprovalPolicy,
    ExecutionRunStatus,
    QuotaReservationState,
    ReuseDecision,
    ReusePolicy,
    RoutingPolicy,
    WorkerStatus,
    WorkOrderStatus,
    is_terminal_run,
    is_terminal_work_order,
)
from .evidence import (
    ArtifactRecord,
    EvidenceReuseIdentity,
    ExecutionEvidence,
    ReuseCandidate,
    compute_execution_policy_hash,
    compute_result_contract_hash,
    compute_reuse_identity_hash,
)
from .exceptions import (
    ApprovalDeniedError,
    ExecutionNotFoundError,
    LifecycleConflictError,
    MalformedEvidenceError,
    ManifestIntegrityError,
    ManifestParameterError,
    OwnershipConflictError,
    RepositoryWritePolicyError,
    UnknownManifestError,
)
from .registry import TrustedManifest, get_trusted_manifest, iter_trusted_manifests
from .repository import (
    CatalogLatestRunProjection,
    ExecutionRepository,
    LeaseSnapshot,
    RunLeaseWindow,
)
from .routing import (
    MAX_ROUTING_INTEGER,
    ROUTING_SCHEMA_VERSION,
    RoutingCandidate,
    RoutingEligibility,
    RoutingEvaluationRequest,
    evaluate_routing_candidate,
    rank_routing_candidates,
    unavailable_route_reason,
)
from .workload_profiles import iter_workload_profiles

_SHA_PATTERN = re.compile(r"^[0-9a-fA-F]{40}$")
_RUNTIME_VERSION_PATTERN = re.compile(r"^\d+(?:\.\d+){1,2}$")
_MAX_CATALOG_RESULT_DURATION_SECONDS = 86_400
_MAX_CATALOG_RESULT_STEPS = 128
_LEGACY_CATALOG_EXCLUSIONS = {
    "Nobodyworld/app-accounting-modular": (
        "manual-semantic-review",
        "publication",
    ),
    "Nobodyworld/dev-agent-switchboard": (
        "manual-semantic-review",
        "publication",
    ),
}


@dataclass(frozen=True, slots=True)
class CatalogLatestResult:
    """Bounded display-only state derived from one completed execution run."""

    reuse_decision: str
    duration_seconds: int | None
    step_count: int
    avoided_work_count: int


@dataclass(frozen=True, slots=True)
class CatalogReadinessAssessment:
    """One read-only catalog entry assembled from authoritative routing inputs."""

    repository_full_name: str
    display_name: str
    manifest_name: str
    manifest_version: str
    manifest_digest: str
    runtime_requirements: dict[str, str]
    ready_count: int
    primary_blocker_code: str
    latest_result: CatalogLatestResult | None
    exclusions: tuple[str, ...]


def _safe_runtime_requirements(requirements: Mapping[str, object]) -> dict[str, str]:
    """Normalize only reviewed Python, Node, and pnpm constraints for display."""

    normalized: dict[str, str] = {}
    for runtime in ("python", "node", "pnpm"):
        requirement = requirements.get(runtime)
        mode = "minimum"
        version: object = requirement
        if isinstance(requirement, Mapping):
            if set(requirement) == {"exact"}:
                mode = "exact"
                version = requirement.get("exact")
            elif set(requirement) == {"minimum"}:
                version = requirement.get("minimum")
            else:
                continue
        if isinstance(version, str) and _RUNTIME_VERSION_PATTERN.fullmatch(version):
            normalized[runtime] = f"{'=' if mode == 'exact' else '>='}{version}"
    return normalized


def _catalog_primary_blocker(
    *,
    repository_full_name: str,
    evaluations: list[RoutingEligibility],
) -> str:
    """Collapse evaluator reasons into the small public catalog vocabulary."""

    if any(item.candidate is not None for item in evaluations):
        return "ready"
    if not evaluations:
        return "no_registered_workers"

    advertised = [
        item
        for item in evaluations
        if repository_full_name
        in (item.worker.repository_full_names or ["Nobodyworld/dev-agent-switchboard"])
    ]
    if not advertised:
        return "repository_unavailable"
    route_reason = unavailable_route_reason(
        [reason for item in advertised for reason in item.reasons],
        explicit_pin=False,
    )
    public_reasons = {
        "worker_repository_unavailable": "repository_unavailable",
        "routing_profile_missing": "profile_missing",
        "routing_profile_invalid": "profile_invalid",
        "routing_profile_disabled": "profile_disabled",
        "worker_heartbeat_stale": "stale_worker",
        "worker_checkout_poll_stale": "stale_worker",
        "worker_not_available": "worker_unavailable",
        "worker_concurrency_limit": "capacity_constrained",
        "routing_cost_ceiling_exceeded": "maximum_cost_exceeded",
        "routing_quota_insufficient": "insufficient_quota",
        "preferred_executor_unavailable": "preferred_executor_unavailable",
    }
    return public_reasons.get(route_reason, "manifest_capability_mismatch")


def _catalog_latest_result(
    projection: CatalogLatestRunProjection | None,
) -> CatalogLatestResult | None:
    """Derive compact, bounded counters without exposing stored evidence detail."""

    if projection is None:
        return None
    duration_seconds: int | None = None
    if projection.started_at is not None and projection.finished_at is not None:
        try:
            duration = int(
                (projection.finished_at - projection.started_at).total_seconds()
            )
        except TypeError:
            duration = -1
        if 0 <= duration <= _MAX_CATALOG_RESULT_DURATION_SECONDS:
            duration_seconds = duration

    steps = projection.evidence_metadata.get("steps")
    step_count = (
        len(steps)
        if isinstance(steps, list)
        and len(steps) <= _MAX_CATALOG_RESULT_STEPS
        and all(isinstance(step, Mapping) for step in steps)
        else 0
    )
    return CatalogLatestResult(
        reuse_decision=projection.reuse_decision.value,
        duration_seconds=duration_seconds,
        step_count=step_count,
        avoided_work_count=(
            step_count if projection.reuse_decision == ReuseDecision.REUSED else 0
        ),
    )


def _catalog_exclusions(repository_full_name: str) -> tuple[str, ...]:
    """Return only bounded reviewed deterministic/manual exclusion identifiers."""

    for profile in iter_workload_profiles():
        if profile.repository_full_name == repository_full_name:
            return profile.deterministic_exclusions[:16]
    return _LEGACY_CATALOG_EXCLUSIONS.get(
        repository_full_name,
        ("manual-semantic-review", "publication"),
    )


class _CheckoutReservationConflictError(RuntimeError):
    """Internal signal that rolls back one nested checkout attempt."""


class ExecutionService:
    """Orchestrate the isolated, non-executing execution control plane."""

    def __init__(
        self,
        *,
        repository: ExecutionRepository,
        clock: Callable[[], dt.datetime],
        lease_seconds: Callable[[], int],
        routing_freshness_seconds: Callable[[], tuple[int, int]] | None = None,
    ) -> None:
        self._repository = repository
        self._clock = clock
        self._lease_seconds = lease_seconds
        self._routing_freshness_seconds = routing_freshness_seconds or (
            lambda: (lease_seconds(), lease_seconds())
        )

    async def sync_trusted_manifests(self) -> tuple[CommandManifest, ...]:
        """Persist the version-controlled manifest registry without mutation."""

        return await self._repository.ensure_manifests(iter_trusted_manifests())

    async def list_manifests(self) -> list[CommandManifest]:
        """Return persisted trusted manifest identities and safe metadata."""

        await self.sync_trusted_manifests()
        return await self._repository.list_manifests()

    async def get_manifest(self, name: str, version: str) -> CommandManifest:
        """Return a trusted persisted manifest or a typed not-found error."""

        await self.sync_trusted_manifests()
        manifest = await self._repository.get_manifest(name, version)
        if manifest is None:
            raise ExecutionNotFoundError("command_manifest_not_found")
        return manifest

    async def create_work_order(self, draft: WorkOrderDraft) -> ExecutionWorkOrder:
        """Create a pending, deny-by-default work order from safe request data."""

        self._validate_work_order_draft(draft)
        if draft.repository_full_name not in TRUSTED_REPOSITORIES:
            raise UnknownManifestError("trusted_repository_not_found")
        definition = get_trusted_manifest(draft.manifest_name, draft.manifest_version)
        if definition is None:
            raise UnknownManifestError("trusted_manifest_not_found")
        if not repository_allows_manifest(
            draft.repository_full_name, draft.manifest_name, draft.manifest_version
        ):
            raise UnknownManifestError("repository_manifest_not_allowed")
        unsupported = set(draft.manifest_parameters) - definition.allowed_parameters
        if unsupported:
            names = ",".join(sorted(unsupported))
            raise ManifestParameterError(f"unsupported_manifest_parameters:{names}")
        if draft.preferred_executor is not None and (
            await self._repository.get_worker(draft.preferred_executor) is None
        ):
            raise ExecutionNotFoundError("preferred_executor_not_found")

        manifest = await self._repository.ensure_manifest(definition)
        execution_policy_hash = compute_execution_policy_hash(
            manifest_parameters=draft.manifest_parameters,
            required_capabilities=draft.required_capabilities,
            permitted_paths=draft.permitted_paths,
            expected_artifact_kinds=draft.expected_artifact_kinds,
            timeout_seconds=draft.timeout_seconds,
            network_policy=draft.network_policy.value,
            repository_write_allowed=False,
            routing_policy=draft.routing_policy.value,
            maximum_cost_units=draft.maximum_cost_units,
            required_quota_units=draft.required_quota_units,
            preferred_executor=draft.preferred_executor,
        )
        return await self._repository.create_work_order(
            {
                "schema_version": draft.schema_version,
                "repository_full_name": draft.repository_full_name,
                "commit_sha": draft.commit_sha.lower(),
                "manifest_id": manifest.id,
                "manifest_name": manifest.name,
                "manifest_version": manifest.version,
                "manifest_digest": manifest.digest,
                "manifest_parameters": dict(draft.manifest_parameters),
                "required_capabilities": dict(draft.required_capabilities),
                "permitted_paths": list(draft.permitted_paths),
                "forbidden_scope_notes": draft.forbidden_scope_notes,
                "expected_artifact_kinds": list(draft.expected_artifact_kinds),
                "approval_policy": draft.approval_policy,
                "status": WorkOrderStatus.PENDING_APPROVAL,
                "timeout_seconds": draft.timeout_seconds,
                "resource_metadata": dict(draft.resource_metadata),
                "network_policy": draft.network_policy,
                "repository_write_allowed": False,
                "preferred_executor": draft.preferred_executor,
                "cost_ceiling": draft.cost_ceiling,
                "routing_policy": draft.routing_policy,
                "maximum_cost_units": draft.maximum_cost_units,
                "required_quota_units": draft.required_quota_units,
                "reuse_policy": draft.reuse_policy,
                "execution_policy_hash": execution_policy_hash,
            }
        )

    async def get_work_order(
        self, work_order_id: int, *, refresh: bool = False
    ) -> ExecutionWorkOrder:
        """Return the requested work order or a typed not-found error."""

        work_order = await self._repository.get_work_order(
            work_order_id, refresh=refresh
        )
        if work_order is None:
            raise ExecutionNotFoundError("work_order_not_found")
        return work_order

    async def list_work_orders(self) -> list[ExecutionWorkOrder]:
        """Return all work orders in stable creation order."""

        return await self._repository.list_work_orders()

    async def approve_work_order(
        self, work_order_id: int, *, queue: bool = True
    ) -> ExecutionWorkOrder:
        """Approve an allowlisted immutable work order and optionally queue it."""

        work_order = await self.get_work_order(work_order_id, refresh=True)
        if work_order.status != WorkOrderStatus.PENDING_APPROVAL:
            raise LifecycleConflictError("work_order_not_pending_approval")
        self._ensure_approvable(work_order)
        now = self._clock()
        target = WorkOrderStatus.QUEUED if queue else WorkOrderStatus.APPROVED
        updated = await self._repository.transition_unleased_work_order(
            work_order.id,
            current_statuses=(WorkOrderStatus.PENDING_APPROVAL,),
            values={
                "status": target,
                "approved_at": now,
                "queued_at": now if target == WorkOrderStatus.QUEUED else None,
                "updated_at": now,
            },
        )
        if not updated:
            raise LifecycleConflictError("work_order_not_pending_approval")
        return await self.get_work_order(work_order.id, refresh=True)

    async def queue_work_order(self, work_order_id: int) -> ExecutionWorkOrder:
        """Move an explicitly approved order into the worker-visible queue."""

        work_order = await self.get_work_order(work_order_id, refresh=True)
        now = self._clock()
        updated = await self._repository.transition_unleased_work_order(
            work_order.id,
            current_statuses=(WorkOrderStatus.APPROVED,),
            values={
                "status": WorkOrderStatus.QUEUED,
                "queued_at": now,
                "updated_at": now,
            },
        )
        if not updated:
            raise LifecycleConflictError("invalid_work_order_transition")
        return await self.get_work_order(work_order.id, refresh=True)

    async def reject_work_order(
        self, work_order_id: int, *, reason: str | None
    ) -> ExecutionWorkOrder:
        """Terminally reject a pending work order before any assignment exists."""

        work_order = await self.get_work_order(work_order_id, refresh=True)
        now = self._clock()
        updated = await self._repository.transition_unleased_work_order(
            work_order.id,
            current_statuses=(WorkOrderStatus.PENDING_APPROVAL,),
            values={
                "status": WorkOrderStatus.REJECTED,
                "finished_at": now,
                "terminal_reason": reason or "rejected_by_operator",
                "updated_at": now,
            },
        )
        if not updated:
            raise LifecycleConflictError("invalid_work_order_transition")
        return await self.get_work_order(work_order.id, refresh=True)

    async def expire_work_order(
        self, work_order_id: int, *, reason: str | None
    ) -> ExecutionWorkOrder:
        """Terminally expire an unassigned approved or queued order."""

        work_order = await self.get_work_order(work_order_id, refresh=True)
        now = self._clock()
        updated = await self._repository.transition_unleased_work_order(
            work_order.id,
            current_statuses=(WorkOrderStatus.APPROVED, WorkOrderStatus.QUEUED),
            values={
                "status": WorkOrderStatus.EXPIRED,
                "finished_at": now,
                "terminal_reason": reason or "expired_by_operator",
                "updated_at": now,
            },
        )
        if not updated:
            raise LifecycleConflictError("invalid_work_order_transition")
        return await self.get_work_order(work_order.id, refresh=True)

    async def cancel_work_order(
        self, work_order_id: int, *, reason: str | None
    ) -> ExecutionWorkOrder:
        """Cancel a work order, releasing any active execution lease safely."""

        work_order = await self.get_work_order(work_order_id, refresh=True)
        now = self._clock()
        terminal_reason = reason or "cancelled_by_operator"
        if work_order.status in {
            WorkOrderStatus.PENDING_APPROVAL,
            WorkOrderStatus.APPROVED,
            WorkOrderStatus.QUEUED,
        }:
            updated = await self._repository.transition_unleased_work_order(
                work_order.id,
                current_statuses=(
                    WorkOrderStatus.PENDING_APPROVAL,
                    WorkOrderStatus.APPROVED,
                    WorkOrderStatus.QUEUED,
                ),
                values={
                    "status": WorkOrderStatus.CANCELLED,
                    "finished_at": now,
                    "terminal_reason": terminal_reason,
                    "updated_at": now,
                },
            )
            if not updated:
                raise LifecycleConflictError("work_order_transition_in_progress")
            return await self.get_work_order(work_order.id, refresh=True)
        if is_terminal_work_order(work_order.status):
            raise LifecycleConflictError("work_order_is_terminal")
        snapshot = await self._repository.get_lease_snapshot_for_work_order(
            work_order.id
        )
        if snapshot is None:
            raise LifecycleConflictError("execution_lease_transition_in_progress")
        await self._finish_active_lease(
            snapshot,
            completion=ExecutionCompletion(
                status=ExecutionRunStatus.CANCELLED,
                terminal_reason=terminal_reason,
                cleanup_status="cancelled_by_control_plane",
            ),
            require_live=False,
            ownership_error=False,
        )
        return await self.get_work_order(work_order.id, refresh=True)

    async def register_worker(
        self, registration: WorkerRegistration
    ) -> ExecutionWorker:
        """Register or refresh a read-only worker capability declaration."""

        if registration.repository_write_capability:
            raise RepositoryWritePolicyError(
                "repository_write_capability_must_be_false"
            )
        now = self._clock()
        return await self._repository.upsert_worker(
            {
                "worker_id": registration.worker_id,
                "display_name": registration.display_name,
                "operating_system": registration.operating_system.lower(),
                "architecture": registration.architecture.lower(),
                "python_version": registration.python_version,
                "node_version": registration.node_version,
                "pnpm_version": registration.pnpm_version,
                "docker_available": registration.docker_available,
                "browsers": list(registration.browsers),
                "gpu_available": registration.gpu_available,
                "unity_available": registration.unity_available,
                "desktop_available": registration.desktop_available,
                "capabilities": dict(registration.capabilities),
                "repository_full_names": list(registration.repository_full_names),
                "max_concurrency": registration.max_concurrency,
                "network_policy_capability": registration.network_policy_capability,
                "repository_write_capability": False,
                "status": registration.status,
            },
            now=now,
        )

    async def heartbeat_worker(
        self, worker_id: str, *, status: WorkerStatus | None = None
    ) -> ExecutionWorker:
        """Refresh a known worker's liveness and optional availability state."""

        worker = await self._repository.get_worker(worker_id)
        if worker is None:
            raise ExecutionNotFoundError("worker_not_found")
        return await self._repository.update_worker_heartbeat(
            worker, now=self._clock(), status=status
        )

    async def create_routing_profile(
        self, draft: RoutingProfileDraft
    ) -> WorkerRoutingProfile:
        """Create one privileged server-owned profile for a known worker."""

        if await self._repository.get_worker(draft.worker_id) is None:
            raise ExecutionNotFoundError("worker_not_found")
        if await self._repository.get_routing_profile(draft.worker_id) is not None:
            raise LifecycleConflictError("routing_profile_already_exists")
        values = self._routing_profile_values(draft)
        try:
            async with self._repository.session.begin_nested():
                return await self._repository.create_routing_profile(values)
        except IntegrityError as error:
            raise LifecycleConflictError("routing_profile_already_exists") from error

    async def get_routing_profile(self, worker_id: str) -> WorkerRoutingProfile:
        """Return one operator-owned profile or a typed not-found error."""

        profile = await self._repository.get_routing_profile(worker_id, refresh=True)
        if profile is None:
            raise ExecutionNotFoundError("routing_profile_not_found")
        return profile

    async def list_routing_profiles(self) -> list[WorkerRoutingProfile]:
        """Return all operator profiles in stable worker-ID order."""

        return await self._repository.list_routing_profiles()

    async def replace_routing_profile(
        self,
        worker_id: str,
        replacement: RoutingProfileReplacement,
    ) -> WorkerRoutingProfile:
        """Replace a profile using optimistic revision protection."""

        if not self._valid_routing_revision(replacement.expected_revision):
            raise LifecycleConflictError("routing_profile_revision_out_of_bounds")
        profile = await self.get_routing_profile(worker_id)
        if await self._repository.count_reserved_quota_runs(worker_id):
            raise LifecycleConflictError("routing_profile_has_active_reservations")
        if profile.revision != replacement.expected_revision:
            raise LifecycleConflictError("routing_profile_revision_conflict")
        now = self._clock()
        values = self._routing_profile_values(replacement)
        updated = await self._repository.replace_routing_profile(
            worker_id,
            expected_revision=replacement.expected_revision,
            values=values,
            now=now,
        )
        if not updated:
            raise LifecycleConflictError("routing_profile_revision_conflict")
        return await self.get_routing_profile(worker_id)

    async def reset_routing_quota(
        self,
        worker_id: str,
        reset: RoutingQuotaReset,
    ) -> WorkerRoutingProfile:
        """Apply one idempotent monotonic quota reset without active reservations."""

        if not self._valid_routing_revision(reset.expected_revision):
            raise LifecycleConflictError("routing_profile_revision_out_of_bounds")
        if (
            not isinstance(reset.quota_remaining_units, int)
            or isinstance(reset.quota_remaining_units, bool)
            or not 0 <= reset.quota_remaining_units <= MAX_ROUTING_INTEGER
        ):
            raise LifecycleConflictError("routing_profile_integer_out_of_bounds")
        if (
            reset.quota_reset_at.tzinfo is None
            or reset.quota_reset_at.utcoffset() is None
        ):
            raise LifecycleConflictError("routing_quota_reset_must_be_aware")
        profile = await self.get_routing_profile(worker_id)
        requested_reset = self._utc_naive(reset.quota_reset_at)
        existing_reset = (
            self._utc_naive(profile.quota_reset_at)
            if profile.quota_reset_at is not None
            else None
        )
        if existing_reset is not None and requested_reset < existing_reset:
            raise LifecycleConflictError("routing_quota_reset_is_stale")
        if existing_reset == requested_reset:
            if (
                profile.quota_remaining_units == reset.quota_remaining_units
                and profile.revision == reset.expected_revision + 1
            ):
                return profile
            if profile.quota_remaining_units == reset.quota_remaining_units:
                raise LifecycleConflictError("routing_profile_revision_conflict")
            raise LifecycleConflictError("routing_quota_reset_conflict")
        if await self._repository.count_reserved_quota_runs(worker_id):
            raise LifecycleConflictError("routing_profile_has_active_reservations")
        if profile.revision != reset.expected_revision:
            raise LifecycleConflictError("routing_profile_revision_conflict")
        if reset.quota_remaining_units > profile.quota_capacity_units:
            raise LifecycleConflictError("routing_quota_exceeds_capacity")
        updated = await self._repository.reset_routing_quota(
            worker_id,
            reset=RoutingQuotaReset(
                expected_revision=reset.expected_revision,
                quota_remaining_units=reset.quota_remaining_units,
                quota_reset_at=requested_reset,
            ),
            now=self._clock(),
        )
        if not updated:
            raise LifecycleConflictError("routing_profile_revision_conflict")
        return await self.get_routing_profile(worker_id)

    async def assess_route(self, work_order_id: int) -> RouteAssessment:
        """Return a bounded current decision without changing poll or quota state."""

        await self.sync_trusted_manifests()
        work_order = await self.get_work_order(work_order_id, refresh=True)
        if work_order.status != WorkOrderStatus.QUEUED:
            raise LifecycleConflictError("route_assessment_requires_queued_work")
        manifest = await self._repository.get_manifest(
            work_order.manifest_name, work_order.manifest_version
        )
        if manifest is None:
            raise ManifestIntegrityError("trusted_manifest_not_found")
        now = self._clock()
        explicit_pin = work_order.preferred_executor is not None
        evaluations = await self._routing_eligibilities(
            request=self._routing_request(work_order=work_order, manifest=manifest),
            now=now,
        )
        candidates = [
            item.candidate for item in evaluations if item.candidate is not None
        ]
        mismatches = list(
            dict.fromkeys(reason for item in evaluations for reason in item.reasons)
        )
        if work_order.routing_policy == RoutingPolicy.FIRST_AVAILABLE:
            selected = (
                next(
                    (
                        item
                        for item in candidates
                        if item.worker.worker_id == work_order.preferred_executor
                    ),
                    None,
                )
                if explicit_pin
                else None
            )
            return RouteAssessment(
                schema_version=ROUTING_SCHEMA_VERSION,
                work_order_id=work_order.id,
                routing_policy=work_order.routing_policy,
                selected_worker_id=(selected.worker.worker_id if selected else None),
                selected_routing_profile_revision=None,
                estimated_cost_units=None,
                required_quota_units=work_order.required_quota_units,
                reserved_quota_units=0,
                quota_reservation_state=QuotaReservationState.NOT_REQUIRED,
                eligible_candidate_count=len(candidates),
                explicit_pin_applied=explicit_pin,
                reason=(
                    "first_available"
                    if candidates
                    else unavailable_route_reason(mismatches, explicit_pin=explicit_pin)
                ),
                decision_timestamp=now,
            )
        ranked = rank_routing_candidates(
            candidates, required_quota_units=work_order.required_quota_units
        )
        selected = ranked[0] if ranked else None
        selected_profile = selected.profile if selected is not None else None
        if selected is not None and selected_profile is None:  # pragma: no cover
            raise ManifestIntegrityError("ranked_routing_profile_missing")
        return RouteAssessment(
            schema_version=ROUTING_SCHEMA_VERSION,
            work_order_id=work_order.id,
            routing_policy=work_order.routing_policy,
            selected_worker_id=(selected.worker.worker_id if selected else None),
            selected_routing_profile_revision=(
                selected_profile.revision if selected_profile else None
            ),
            estimated_cost_units=(
                selected_profile.estimated_cost_units_per_run
                if selected_profile
                else None
            ),
            required_quota_units=work_order.required_quota_units,
            reserved_quota_units=0,
            quota_reservation_state=QuotaReservationState.NOT_REQUIRED,
            eligible_candidate_count=len(ranked),
            explicit_pin_applied=explicit_pin,
            reason=(
                "routing_selected"
                if selected is not None
                else unavailable_route_reason(mismatches, explicit_pin=explicit_pin)
            ),
            decision_timestamp=now,
        )

    async def assess_repository_readiness(  # noqa: PLR0913
        self,
        *,
        repository_full_name: str,
        manifest_name: str,
        manifest_version: str,
        routing_policy: RoutingPolicy,
        maximum_cost_units: int | None,
        required_quota_units: int,
        preferred_executor: str | None,
    ) -> tuple[list[RoutingEligibility], RoutingCandidate | None]:
        """Evaluate trusted repository readiness without mutating persisted state."""

        if not repository_allows_manifest(
            repository_full_name, manifest_name, manifest_version
        ):
            raise UnknownManifestError("repository_manifest_not_allowed")
        manifest = get_trusted_manifest(manifest_name, manifest_version)
        if manifest is None:
            raise UnknownManifestError("trusted_manifest_not_found")
        request = RoutingEvaluationRequest(
            repository_full_name=repository_full_name,
            routing_policy=routing_policy,
            preferred_executor=preferred_executor,
            maximum_cost_units=maximum_cost_units,
            required_quota_units=required_quota_units,
            manifest_requirements=manifest.required_capabilities,
            requested_requirements={},
            network_policy=manifest.network_policy,
        )
        evaluations = await self._routing_eligibilities(
            request=request,
            now=self._clock(),
        )
        candidates = [
            item.candidate for item in evaluations if item.candidate is not None
        ]
        if routing_policy == RoutingPolicy.CHEAPEST_CAPABLE:
            ranked = rank_routing_candidates(
                candidates, required_quota_units=required_quota_units
            )
            return evaluations, (ranked[0] if ranked else None)
        if preferred_executor is not None:
            selected = next(
                (
                    item
                    for item in candidates
                    if item.worker.worker_id == preferred_executor
                ),
                None,
            )
            return evaluations, selected
        return evaluations, None

    async def assess_catalog_readiness(
        self,
    ) -> tuple[CatalogReadinessAssessment, ...]:
        """Return bounded public-catalog readiness without changing lifecycle state.

        This deliberately avoids manifest synchronization, poll refreshes, source
        resolution, and routing reservations.  A single authoritative worker/profile
        snapshot and one bounded latest-result projection are shared across every
        source-controlled catalog entry.
        """

        repositories = iter_trusted_repositories()
        resolved: list[tuple[TrustedRepository, TrustedManifest]] = []
        for repository in repositories:
            reference = repository.default_manifest
            manifest = get_trusted_manifest(reference.name, reference.version)
            if manifest is None:
                raise ManifestIntegrityError("trusted_manifest_not_found")
            resolved.append((repository, manifest))

        worker_snapshot = await self._repository.list_workers_with_profiles()
        latest_results = await self._repository.list_latest_successful_catalog_runs(
            (
                (repository.full_name, manifest.name, manifest.version)
                for repository, manifest in resolved
            )
        )
        now = self._clock()
        assessments: list[CatalogReadinessAssessment] = []
        for repository, manifest in resolved:
            request = RoutingEvaluationRequest(
                repository_full_name=repository.full_name,
                routing_policy=RoutingPolicy.FIRST_AVAILABLE,
                preferred_executor=None,
                maximum_cost_units=None,
                required_quota_units=0,
                manifest_requirements=manifest.required_capabilities,
                requested_requirements={},
                network_policy=manifest.network_policy,
            )
            evaluations = await self._routing_eligibilities(
                request=request,
                now=now,
                worker_snapshot=worker_snapshot,
            )
            latest = latest_results.get(
                (repository.full_name, manifest.name, manifest.version)
            )
            assessments.append(
                CatalogReadinessAssessment(
                    repository_full_name=repository.full_name,
                    display_name=repository.display_name,
                    manifest_name=manifest.name,
                    manifest_version=manifest.version,
                    manifest_digest=manifest.digest,
                    runtime_requirements=_safe_runtime_requirements(
                        manifest.required_capabilities
                    ),
                    ready_count=sum(item.candidate is not None for item in evaluations),
                    primary_blocker_code=_catalog_primary_blocker(
                        repository_full_name=repository.full_name,
                        evaluations=evaluations,
                    ),
                    latest_result=_catalog_latest_result(latest),
                    exclusions=_catalog_exclusions(repository.full_name),
                )
            )
        return tuple(assessments)

    async def checkout(self, worker_id: str) -> CheckoutResult:
        """Atomically assign one capability-compatible queued work order."""

        await self.sync_trusted_manifests()
        await self.expire_stale_leases()
        worker = await self._repository.get_worker(worker_id)
        if worker is None:
            raise ExecutionNotFoundError("worker_not_found")
        if not await self._repository.record_checkout_poll(
            worker_id, now=self._clock()
        ):
            raise ExecutionNotFoundError("worker_not_found")
        worker = await self._repository.get_worker(worker_id)
        if worker is None:  # pragma: no cover - guarded update cannot remove it
            raise ExecutionNotFoundError("worker_not_found")
        unavailable = self._unavailable_worker_result(worker)
        if unavailable is not None:
            return unavailable
        return await self._checkout_eligible_work(worker)

    async def _checkout_eligible_work(self, worker: ExecutionWorker) -> CheckoutResult:
        """Claim one stable queued order under its selected routing policy."""

        candidates = await self._repository.list_queued_work_orders()
        mismatch_reasons: list[str] = []
        route_reasons: list[str] = []
        for work_order, manifest in candidates:
            now = self._clock()
            explicit_pin = work_order.preferred_executor is not None
            evaluations = await self._routing_eligibilities(
                request=self._routing_request(
                    work_order=work_order,
                    manifest=manifest,
                ),
                now=now,
            )
            eligibility = next(
                item
                for item in evaluations
                if item.worker.worker_id == worker.worker_id
            )
            mismatch_reasons.extend(eligibility.reasons)
            eligible = [
                item.candidate for item in evaluations if item.candidate is not None
            ]
            if work_order.routing_policy == RoutingPolicy.FIRST_AVAILABLE:
                if eligibility.candidate is None:
                    reason = unavailable_route_reason(
                        list(eligibility.reasons), explicit_pin=explicit_pin
                    )
                    if reason != "no_capable_workers":
                        route_reasons.append(reason)
                    continue
                result = await self._claim_routed_work(
                    worker=worker,
                    work_order=work_order,
                    profile=None,
                    eligible_candidate_count=len(eligible),
                    explicit_pin=explicit_pin,
                    now=now,
                )
            else:
                ranked = rank_routing_candidates(
                    eligible,
                    required_quota_units=work_order.required_quota_units,
                )
                if not ranked:
                    route_reasons.append(
                        unavailable_route_reason(
                            list(eligibility.reasons), explicit_pin=explicit_pin
                        )
                    )
                    continue
                selected = ranked[0]
                if selected.worker.worker_id != worker.worker_id:
                    route_reasons.append("better_candidate_active")
                    continue
                result = await self._claim_routed_work(
                    worker=worker,
                    work_order=work_order,
                    profile=selected.profile,
                    eligible_candidate_count=len(ranked),
                    explicit_pin=explicit_pin,
                    now=now,
                )
            if result.reason == "checkout_conflict":
                route_reasons.append("checkout_conflict")
                continue
            return result
        if route_reasons:
            return CheckoutResult(
                None,
                None,
                route_reasons[0],
                tuple(dict.fromkeys(mismatch_reasons)),
            )
        if mismatch_reasons:
            unique_mismatches = tuple(dict.fromkeys(mismatch_reasons))
            return CheckoutResult(
                None,
                None,
                (
                    "worker_repository_unavailable"
                    if "worker_repository_unavailable" in unique_mismatches
                    else "capability_mismatch"
                ),
                unique_mismatches,
            )
        return CheckoutResult(None, None, "no_queued_work_orders")

    async def _claim_routed_work(  # noqa: PLR0913
        self,
        *,
        worker: ExecutionWorker,
        work_order: ExecutionWorkOrder,
        profile: WorkerRoutingProfile | None,
        eligible_candidate_count: int,
        explicit_pin: bool,
        now: dt.datetime,
    ) -> CheckoutResult:
        """Atomically reserve capacity/quota and create one run and lease."""

        expires_at = now + dt.timedelta(seconds=self._lease_seconds())
        try:
            async with self._repository.session.begin_nested():
                if not await self._repository.reserve_worker_capacity(
                    worker.worker_id, now=now
                ):
                    raise _CheckoutReservationConflictError("worker_concurrency_limit")

                profile_revision: int | None = None
                estimated_cost_units: int | None = None
                reserved_quota_units = 0
                quota_state = QuotaReservationState.NOT_REQUIRED
                if profile is not None:
                    profile_revision = await self._repository.reserve_routing_quota(
                        worker.worker_id,
                        expected_revision=profile.revision,
                        units=work_order.required_quota_units,
                        now=now,
                    )
                    if profile_revision is None:
                        raise _CheckoutReservationConflictError(
                            "routing_reservation_conflict"
                        )
                    estimated_cost_units = profile.estimated_cost_units_per_run
                    reserved_quota_units = work_order.required_quota_units
                    if reserved_quota_units:
                        quota_state = QuotaReservationState.RESERVED

                order_route_values = {
                    "route_schema_version": ROUTING_SCHEMA_VERSION,
                    "route_selected_worker_id": worker.worker_id,
                    "route_profile_revision": profile_revision,
                    "route_estimated_cost_units": estimated_cost_units,
                    "route_reserved_quota_units": reserved_quota_units,
                    "route_quota_state": quota_state,
                    "route_eligible_candidate_count": eligible_candidate_count,
                    "route_explicit_pin_applied": explicit_pin,
                    "route_reason": "routing_selected",
                    "route_decided_at": now,
                }
                if not await self._repository.claim_queued_work_order(
                    work_order.id,
                    now=now,
                    route_values=order_route_values,
                ):
                    raise _CheckoutReservationConflictError("checkout_conflict")
                claimed_order = await self._repository.get_work_order(
                    work_order.id, refresh=True
                )
                if claimed_order is None:  # pragma: no cover - guarded claim exists
                    raise ExecutionNotFoundError("work_order_not_found")
                run = await self._repository.create_active_run(
                    work_order=claimed_order,
                    worker_id=worker.worker_id,
                    lease_window=RunLeaseWindow(
                        assigned_at=now,
                        expires_at=expires_at,
                    ),
                    route_values={
                        "route_schema_version": ROUTING_SCHEMA_VERSION,
                        "routing_policy": work_order.routing_policy,
                        "route_profile_revision": profile_revision,
                        "route_estimated_cost_units": estimated_cost_units,
                        "route_required_quota_units": (work_order.required_quota_units),
                        "route_reserved_quota_units": reserved_quota_units,
                        "route_quota_state": quota_state,
                        "route_eligible_candidate_count": eligible_candidate_count,
                        "route_explicit_pin_applied": explicit_pin,
                        "route_reason": "routing_selected",
                        "route_decided_at": now,
                    },
                )
                return CheckoutResult(run.id, claimed_order.id, None)
        except _CheckoutReservationConflictError as error:
            return CheckoutResult(None, None, str(error))
        except IntegrityError:
            return CheckoutResult(None, None, "checkout_conflict")

    @staticmethod
    def _routing_request(
        *,
        work_order: ExecutionWorkOrder,
        manifest: CommandManifest,
    ) -> RoutingEvaluationRequest:
        """Build the pure evaluator input used by every routing surface."""

        return RoutingEvaluationRequest(
            repository_full_name=work_order.repository_full_name,
            routing_policy=work_order.routing_policy,
            preferred_executor=work_order.preferred_executor,
            maximum_cost_units=work_order.maximum_cost_units,
            required_quota_units=work_order.required_quota_units,
            manifest_requirements=manifest.required_capabilities,
            requested_requirements=work_order.required_capabilities,
            network_policy=work_order.network_policy,
        )

    async def _routing_eligibilities(
        self,
        *,
        request: RoutingEvaluationRequest,
        now: dt.datetime,
        worker_snapshot: (
            list[tuple[ExecutionWorker, WorkerRoutingProfile | None]] | None
        ) = None,
    ) -> list[RoutingEligibility]:
        """Evaluate one authoritative worker set without mutations."""

        heartbeat_freshness_seconds, active_poll_freshness_seconds = (
            self._routing_freshness_seconds()
        )
        evaluations: list[RoutingEligibility] = []
        workers = (
            worker_snapshot
            if worker_snapshot is not None
            else await self._repository.list_workers_with_profiles()
        )
        for worker, profile in workers:
            evaluations.append(
                evaluate_routing_candidate(
                    worker,
                    profile,
                    request=request,
                    now=now,
                    heartbeat_freshness_seconds=heartbeat_freshness_seconds,
                    active_poll_freshness_seconds=active_poll_freshness_seconds,
                )
            )
        return evaluations

    @classmethod
    def _routing_profile_values(
        cls,
        values: RoutingProfileDraft | RoutingProfileReplacement,
    ) -> dict[str, object]:
        """Validate service-level profile inputs and normalize reset time to UTC."""

        if not isinstance(values.enabled, bool):
            raise LifecycleConflictError("routing_profile_enabled_must_be_boolean")
        integer_values = (
            values.estimated_cost_units_per_run,
            values.quota_capacity_units,
            values.quota_remaining_units,
            values.routing_priority,
        )
        if any(
            not isinstance(value, int)
            or isinstance(value, bool)
            or not 0 <= value <= MAX_ROUTING_INTEGER
            for value in integer_values
        ):
            raise LifecycleConflictError("routing_profile_integer_out_of_bounds")
        if values.quota_remaining_units > values.quota_capacity_units:
            raise LifecycleConflictError("routing_quota_exceeds_capacity")
        reset_at = values.quota_reset_at
        if reset_at is not None:
            if reset_at.tzinfo is None or reset_at.utcoffset() is None:
                raise LifecycleConflictError("routing_quota_reset_must_be_aware")
            reset_at = cls._utc_naive(reset_at)
        payload: dict[str, object] = {
            "enabled": values.enabled,
            "estimated_cost_units_per_run": values.estimated_cost_units_per_run,
            "quota_capacity_units": values.quota_capacity_units,
            "quota_remaining_units": values.quota_remaining_units,
            "quota_reset_at": reset_at,
            "routing_priority": values.routing_priority,
        }
        if isinstance(values, RoutingProfileDraft):
            if (
                not isinstance(values.schema_version, int)
                or isinstance(values.schema_version, bool)
                or values.schema_version != ROUTING_SCHEMA_VERSION
            ):
                raise LifecycleConflictError(
                    "unsupported_routing_profile_schema_version"
                )
            payload.update(
                {
                    "schema_version": values.schema_version,
                    "worker_id": values.worker_id,
                    "revision": 1,
                }
            )
        return payload

    @staticmethod
    def _valid_routing_revision(value: object) -> bool:
        """Return whether an operator revision is a bounded strict integer."""

        return (
            isinstance(value, int)
            and not isinstance(value, bool)
            and 1 <= value <= MAX_ROUTING_INTEGER
        )

    @staticmethod
    def _utc_naive(value: dt.datetime) -> dt.datetime:
        """Normalize an aware timestamp for the repository's UTC-naive storage."""

        if value.tzinfo is None or value.utcoffset() is None:
            return value
        return value.astimezone(dt.UTC).replace(tzinfo=None)

    @staticmethod
    def _unavailable_worker_result(
        worker: ExecutionWorker,
    ) -> CheckoutResult | None:
        if worker.status in {WorkerStatus.DRAINING, WorkerStatus.OFFLINE}:
            return CheckoutResult(None, None, "worker_not_available")
        if worker.status == WorkerStatus.BUSY:
            return CheckoutResult(None, None, "worker_concurrency_limit")
        return None

    async def get_run(self, run_id: int) -> ExecutionRun:
        """Return a historical run or a typed not-found error."""

        run = await self._repository.get_run(run_id)
        if run is None:
            raise ExecutionNotFoundError("execution_run_not_found")
        return run

    async def get_run_evidence(self, run_id: int) -> ExecutionEvidence:
        """Return strict persisted compact evidence or fail explicitly."""

        run = await self.get_run(run_id)
        if not run.evidence_metadata:
            raise ExecutionNotFoundError("execution_evidence_not_found")
        try:
            return ExecutionEvidence.model_validate(run.evidence_metadata)
        except (TypeError, ValueError) as error:
            raise MalformedEvidenceError("malformed_execution_evidence") from error

    async def resolve_reuse_candidate(
        self,
        run_id: int,
        *,
        worker_id: str,
        reuse_identity: EvidenceReuseIdentity,
        reuse_identity_hash: str,
    ) -> ReuseCandidateResult:
        """Resolve one exact source for the current live lease owner."""

        if compute_reuse_identity_hash(reuse_identity) != reuse_identity_hash:
            raise LifecycleConflictError("reuse_identity_hash_mismatch")
        snapshot = await self._repository.get_lease_snapshot_for_run(run_id)
        lease = await self._repository.get_lease_for_run(run_id)
        now = self._clock()
        if (
            snapshot is None
            or lease is None
            or snapshot.worker_id != worker_id
            or lease.worker_id != worker_id
            or lease.expires_at < now
        ):
            raise OwnershipConflictError("execution_lease_not_owned")
        order = await self.get_work_order(snapshot.work_order_id, refresh=True)
        if order.reuse_policy == ReusePolicy.NEVER:
            raise LifecycleConflictError("reuse_policy_never")
        self._validate_reuse_identity(order, reuse_identity)

        selected: ReuseCandidate | None = None
        sources = await self._repository.list_exact_reuse_candidates(
            work_order=order,
            worker_id=worker_id,
            reuse_identity_hash=reuse_identity_hash,
            exclude_run_id=run_id,
        )
        for source_run, source_order in sources:
            selected = await self._validated_reuse_candidate(
                source_run=source_run,
                source_order=source_order,
                expected_identity=reuse_identity,
                now=now,
            )
            if selected is not None:
                break

        decision = (
            ReuseDecision.CANDIDATE_AVAILABLE
            if selected is not None
            else ReuseDecision.UNAVAILABLE
        )
        reason = (
            "exact_candidate_available"
            if selected is not None
            else "exact_candidate_not_found"
        )
        updated = await self._repository.update_active_run_reuse(
            run_id,
            values={
                "reuse_identity": reuse_identity.model_dump(mode="json"),
                "reuse_identity_hash": reuse_identity_hash,
                "reuse_decision": decision,
                "reuse_reason": reason,
                "reuse_candidate_metadata": (
                    selected.model_dump(mode="json") if selected is not None else None
                ),
            },
        )
        if not updated:
            raise OwnershipConflictError("execution_lease_not_owned")
        return ReuseCandidateResult(decision, reason, selected)

    async def list_runs(self, work_order_id: int | None = None) -> list[ExecutionRun]:
        """Return historical attempts, optionally for one work order."""

        return await self._repository.list_runs(work_order_id)

    async def heartbeat_run(self, run_id: int, *, worker_id: str) -> ExecutionRun:
        """Refresh an owned run lease and mark its first observed execution start."""

        await self.get_run(run_id)
        snapshot = await self._repository.get_lease_snapshot_for_run(run_id)
        if snapshot is None or snapshot.worker_id != worker_id:
            raise OwnershipConflictError("execution_lease_not_owned")
        now = self._clock()
        expires_at = now + dt.timedelta(seconds=self._lease_seconds())
        async with self._repository.session.begin_nested():
            renewed = await self._repository.renew_owned_live_lease(
                run_id,
                worker_id=worker_id,
                now=now,
                expires_at=expires_at,
            )
            if not renewed:
                raise OwnershipConflictError("execution_lease_expired")
            quota_consumed = await self._repository.consume_run_quota_reservation(
                run_id,
                work_order_id=snapshot.work_order_id,
                now=now,
            )
            run_updated = await self._repository.mark_active_run_running(
                run_id, now=now, expires_at=expires_at
            )
            work_order_updated = await self._repository.mark_active_work_order_running(
                snapshot.work_order_id, now=now
            )
            if not quota_consumed or not run_updated or not work_order_updated:
                raise LifecycleConflictError("execution_run_is_not_active")
        run = await self._repository.get_run(run_id, refresh=True)
        if run is None:  # pragma: no cover - direct update cannot remove a run
            raise ExecutionNotFoundError("execution_run_not_found")
        return run

    async def complete_run(
        self,
        run_id: int,
        *,
        worker_id: str,
        completion: ExecutionCompletion,
    ) -> ExecutionRun:
        """Record a worker-owned terminal outcome without executing anything."""

        if not is_terminal_run(completion.status):
            raise LifecycleConflictError("execution_completion_must_be_terminal")
        await self.get_run(run_id)
        snapshot = await self._repository.get_lease_snapshot_for_run(run_id)
        if snapshot is None or snapshot.worker_id != worker_id:
            raise OwnershipConflictError("execution_lease_not_owned")
        return await self._finish_active_lease(
            snapshot,
            completion=completion,
            require_live=True,
            ownership_error=True,
        )

    async def expire_stale_leases(self) -> ExpiryResult:
        """Terminalize stale attempts and safely requeue their nonterminal order."""

        now = self._clock()
        requeued: list[int] = []
        timed_out: list[int] = []
        for snapshot in await self._repository.list_stale_lease_snapshots(now=now):
            async with self._repository.session.begin_nested():
                consumed = await self._repository.consume_lease(
                    snapshot, now=now, require_stale=True
                )
                if not consumed:
                    continue
                quota_released = await self._repository.release_run_quota_reservation(
                    snapshot.execution_run_id,
                    work_order_id=snapshot.work_order_id,
                    worker_id=snapshot.worker_id,
                    now=now,
                )
                run_updated = await self._repository.requeue_stale_active_run(
                    snapshot.execution_run_id, now=now
                )
                work_order_updated = (
                    await self._repository.requeue_stale_active_work_order(
                        snapshot.work_order_id, now=now
                    )
                )
                released = await self._repository.release_worker_capacity(
                    snapshot.worker_id, now=now
                )
                if (
                    not quota_released
                    or not run_updated
                    or not work_order_updated
                    or not released
                ):
                    raise LifecycleConflictError("stale_lease_state_conflict")
            timed_out.append(snapshot.execution_run_id)
            requeued.append(snapshot.work_order_id)
        return ExpiryResult(tuple(requeued), tuple(timed_out))

    async def requeue_stale_work_order(self, work_order_id: int) -> ExecutionWorkOrder:
        """Requeue only an assigned/running order whose active lease is stale."""

        result = await self.expire_stale_leases()
        if work_order_id not in result.requeued_work_order_ids:
            raise LifecycleConflictError("work_order_could_not_be_requeued")
        return await self.get_work_order(work_order_id, refresh=True)

    def _validate_work_order_draft(self, draft: WorkOrderDraft) -> None:
        if draft.schema_version != 1:
            raise LifecycleConflictError("unsupported_work_order_schema_version")
        if _SHA_PATTERN.fullmatch(draft.commit_sha) is None:
            raise LifecycleConflictError("commit_sha_must_be_exact_40_character_hex")
        if draft.repository_write_allowed:
            raise RepositoryWritePolicyError("repository_write_must_be_false")
        if draft.required_capabilities.get("repository_write") is not False and (
            "repository_write" in draft.required_capabilities
        ):
            raise RepositoryWritePolicyError(
                "repository_write_capability_not_permitted"
            )
        if draft.routing_policy not in {
            RoutingPolicy.FIRST_AVAILABLE,
            RoutingPolicy.CHEAPEST_CAPABLE,
        }:
            raise LifecycleConflictError("unsupported_routing_policy")
        routing_integers = (
            draft.required_quota_units,
            *(
                (draft.maximum_cost_units,)
                if draft.maximum_cost_units is not None
                else ()
            ),
        )
        if any(
            not isinstance(value, int)
            or isinstance(value, bool)
            or not 0 <= value <= MAX_ROUTING_INTEGER
            for value in routing_integers
        ):
            raise LifecycleConflictError("routing_integer_out_of_bounds")

    def _validate_reuse_identity(
        self, order: ExecutionWorkOrder, identity: EvidenceReuseIdentity
    ) -> None:
        definition = get_trusted_manifest(order.manifest_name, order.manifest_version)
        if definition is None:
            raise ManifestIntegrityError("trusted_manifest_not_found")
        result_contract_hash = compute_result_contract_hash(
            fixed_step_metadata=definition.fixed_step_metadata,
            artifact_declarations=definition.artifact_declarations,
            dependency_lock_paths=definition.dependency_lock_paths,
            result_contract=definition.result_contract,
        )
        if (
            identity.repository_full_name != order.repository_full_name
            or identity.tested_sha != order.commit_sha
            or identity.manifest_name != order.manifest_name
            or identity.manifest_version != order.manifest_version
            or identity.manifest_digest != order.manifest_digest
            or identity.execution_policy_hash != order.execution_policy_hash
            or identity.result_contract_hash != result_contract_hash
            or [item.relative_path for item in identity.dependency_lock_hashes]
            != sorted(definition.dependency_lock_paths)
        ):
            raise LifecycleConflictError("reuse_identity_work_order_mismatch")

    async def _validated_reuse_candidate(
        self,
        *,
        source_run: ExecutionRun,
        source_order: ExecutionWorkOrder,
        expected_identity: EvidenceReuseIdentity,
        now: dt.datetime,
    ) -> ReuseCandidate | None:
        """Return a strict eligible source or fail the candidate closed."""

        try:
            if (
                not source_run.evidence_metadata
                or not source_run.reuse_identity
                or source_run.evidence_retention_expires_at is None
                or source_run.finished_at is None
            ):
                return None
            evidence = ExecutionEvidence.model_validate(source_run.evidence_metadata)
            stored_identity = EvidenceReuseIdentity.model_validate(
                source_run.reuse_identity
            )
            retention = source_run.evidence_retention_expires_at
            if retention.tzinfo is None:
                retention = retention.replace(tzinfo=dt.UTC)
            worker = await self._repository.get_worker(source_run.worker_id)
            artifacts = tuple(
                ArtifactRecord.model_validate(item)
                for item in source_run.artifact_metadata
            )
            provenance = evidence.reuse_provenance
            if (
                worker is None
                or source_order.repository_full_name
                not in (
                    worker.repository_full_names
                    or ["Nobodyworld/dev-agent-switchboard"]
                )
                or source_order.status != WorkOrderStatus.SUCCEEDED
                or source_order.finished_at is None
                or source_run.status != ExecutionRunStatus.SUCCEEDED
                or source_run.reuse_decision != ReuseDecision.FRESH
                or source_run.reused_from_run_id is not None
                or source_run.source_evidence_fingerprint is not None
                or source_run.reuse_candidate_metadata is not None
                or retention <= now.replace(tzinfo=dt.UTC)
                or stored_identity != expected_identity
                or source_run.reuse_identity_hash
                != compute_reuse_identity_hash(stored_identity)
                or evidence.fingerprint == ""
                or evidence.run_id != source_run.id
                or evidence.work_order_id != source_order.id
                or evidence.worker_id != source_run.worker_id
                or evidence.terminal_status != "succeeded"
                or tuple(evidence.artifacts) != artifacts
                or any(item.retention_expires_at != retention for item in artifacts)
                or provenance is None
                or provenance.decision != "fresh"
                or provenance.source_run_id is not None
                or provenance.source_evidence_fingerprint is not None
                or provenance.reuse_identity_hash != source_run.reuse_identity_hash
                or stored_identity.repository_full_name != evidence.repository_full_name
                or stored_identity.tested_sha != evidence.tested_sha
                or stored_identity.manifest_name != evidence.manifest_name
                or stored_identity.manifest_version != evidence.manifest_version
                or stored_identity.manifest_digest != evidence.manifest_digest
                or stored_identity.worker_environment_fingerprint
                != evidence.environment.fingerprint
                or stored_identity.dependency_lock_hashes
                != evidence.dependency_lock_hashes
            ):
                return None
            return ReuseCandidate(
                source_run_id=source_run.id,
                expected_source_worker_id=source_run.worker_id,
                expected_source_evidence_fingerprint=evidence.fingerprint,
                reuse_identity=stored_identity,
                reuse_identity_hash=source_run.reuse_identity_hash,
                source_created_at=evidence.started_at,
                retention_expires_at=retention,
                artifacts=list(artifacts),
            )
        except (TypeError, ValueError):
            return None

    def _ensure_approvable(self, work_order: ExecutionWorkOrder) -> None:
        if work_order.approval_policy != ApprovalPolicy.EXPLICIT:
            raise ApprovalDeniedError("unsupported_approval_policy")
        if work_order.repository_full_name not in TRUSTED_REPOSITORIES:
            raise ApprovalDeniedError("repository_not_allowlisted")
        if work_order.repository_write_allowed:
            raise ApprovalDeniedError("repository_write_not_permitted")
        definition = get_trusted_manifest(
            work_order.manifest_name, work_order.manifest_version
        )
        if definition is None:
            raise ApprovalDeniedError("trusted_manifest_not_found")
        if not repository_allows_manifest(
            work_order.repository_full_name,
            work_order.manifest_name,
            work_order.manifest_version,
        ):
            raise ApprovalDeniedError("repository_manifest_not_allowed")
        if definition.digest != work_order.manifest_digest:
            raise ManifestIntegrityError("trusted_manifest_digest_conflict")

    async def _finish_active_lease(
        self,
        snapshot: LeaseSnapshot,
        *,
        completion: ExecutionCompletion,
        require_live: bool,
        ownership_error: bool,
    ) -> ExecutionRun:
        """Consume one lease, terminalize its records, and release capacity once."""

        await self._validate_completion_evidence(snapshot, completion)
        reuse_values = await self._reuse_completion_values(snapshot, completion)
        now = self._clock()
        status = completion.status
        target_work_order_status = WorkOrderStatus(status.value)
        terminal_reason = completion.terminal_reason or status.value
        async with self._repository.session.begin_nested():
            consumed = await self._repository.consume_lease(
                snapshot,
                now=now,
                require_live=require_live,
            )
            if not consumed:
                if ownership_error:
                    raise OwnershipConflictError("execution_lease_not_owned")
                raise LifecycleConflictError("execution_lease_transition_in_progress")
            quota_released = await self._repository.release_run_quota_reservation(
                snapshot.execution_run_id,
                work_order_id=snapshot.work_order_id,
                worker_id=snapshot.worker_id,
                now=now,
            )
            run_updated = await self._repository.finish_active_run(
                snapshot.execution_run_id,
                values={
                    "status": status,
                    "finished_at": now,
                    "last_heartbeat_at": now,
                    "result_summary": completion.result_summary,
                    "terminal_reason": terminal_reason,
                    "cleanup_status": completion.cleanup_status,
                    "artifact_metadata": [
                        item.model_dump(mode="json")
                        for item in completion.artifact_metadata
                    ],
                    "evidence_metadata": (
                        completion.evidence_metadata.model_dump(mode="json")
                        if completion.evidence_metadata is not None
                        else {}
                    ),
                    **reuse_values,
                },
            )
            work_order_updated = await self._repository.finish_active_work_order(
                snapshot.work_order_id,
                status=target_work_order_status,
                now=now,
                terminal_reason=terminal_reason,
            )
            released = await self._repository.release_worker_capacity(
                snapshot.worker_id, now=now
            )
            if (
                not quota_released
                or not run_updated
                or not work_order_updated
                or not released
            ):
                raise LifecycleConflictError("execution_record_transition_in_progress")
        run = await self._repository.get_run(snapshot.execution_run_id, refresh=True)
        if run is None:  # pragma: no cover - direct update cannot remove a run
            raise ExecutionNotFoundError("execution_run_not_found")
        return run

    async def _reuse_completion_values(  # noqa: PLR0912, PLR0915
        self, snapshot: LeaseSnapshot, completion: ExecutionCompletion
    ) -> dict[str, object]:
        """Validate final reuse provenance and derive server-owned run fields."""

        run = await self._repository.get_run(snapshot.execution_run_id, refresh=True)
        if run is None:
            raise ExecutionNotFoundError("execution_run_not_found")
        order = await self.get_work_order(snapshot.work_order_id, refresh=True)
        decision = completion.reuse_decision
        if decision is None and order.reuse_policy == ReusePolicy.NEVER:
            decision = ReuseDecision.FRESH
        if (
            decision is None
            and order.reuse_policy != ReusePolicy.NEVER
            and completion.status != ExecutionRunStatus.SUCCEEDED
            and completion.evidence_metadata is None
        ):
            decision = ReuseDecision.UNAVAILABLE
        if decision not in {
            ReuseDecision.FRESH,
            ReuseDecision.REUSED,
            ReuseDecision.UNAVAILABLE,
        }:
            raise LifecycleConflictError("invalid_reuse_completion_decision")
        if (
            order.reuse_policy == ReusePolicy.REQUIRE_EXACT
            and decision == ReuseDecision.FRESH
        ):
            raise LifecycleConflictError("require_exact_forbids_fresh_execution")
        if (
            decision == ReuseDecision.UNAVAILABLE
            and order.reuse_policy == ReusePolicy.NEVER
        ):
            raise LifecycleConflictError("reuse_unavailable_requires_opt_in_policy")
        if (
            decision == ReuseDecision.UNAVAILABLE
            and completion.status == ExecutionRunStatus.SUCCEEDED
        ):
            raise LifecycleConflictError("unavailable_reuse_must_not_succeed")

        identity = completion.reuse_identity
        if identity is None and run.reuse_identity:
            identity = EvidenceReuseIdentity.model_validate(run.reuse_identity)
        identity_hash = completion.reuse_identity_hash or run.reuse_identity_hash
        if identity is not None:
            self._validate_reuse_identity(order, identity)
            if identity_hash != compute_reuse_identity_hash(identity):
                raise LifecycleConflictError("reuse_identity_hash_mismatch")
        legacy_never_evidence = (
            order.reuse_policy == ReusePolicy.NEVER
            and completion.evidence_metadata is not None
            and completion.evidence_metadata.reuse_provenance is None
            and identity is None
            and identity_hash is None
        )
        if (
            completion.evidence_metadata is not None
            and identity is None
            and not legacy_never_evidence
        ):
            raise LifecycleConflictError("execution_evidence_requires_reuse_identity")

        source_run_id: int | None = None
        source_fingerprint: str | None = None
        if decision == ReuseDecision.REUSED:
            if not run.reuse_candidate_metadata or identity is None:
                raise LifecycleConflictError("verified_reuse_candidate_missing")
            candidate = ReuseCandidate.model_validate(run.reuse_candidate_metadata)
            if (
                candidate.reuse_identity != identity
                or candidate.reuse_identity_hash != identity_hash
            ):
                raise LifecycleConflictError("verified_reuse_candidate_mismatch")
            source_run_id = candidate.source_run_id
            source_fingerprint = candidate.expected_source_evidence_fingerprint

        evidence = completion.evidence_metadata
        if evidence is not None and not legacy_never_evidence:
            provenance = evidence.reuse_provenance
            if provenance is None or provenance.decision != decision.value:
                raise LifecycleConflictError("execution_reuse_provenance_mismatch")
            if provenance.reuse_identity_hash != identity_hash:
                raise LifecycleConflictError("execution_reuse_identity_mismatch")
            if (
                provenance.source_run_id != source_run_id
                or provenance.source_evidence_fingerprint != source_fingerprint
            ):
                raise LifecycleConflictError("execution_reuse_source_mismatch")
            retention = completion.evidence_retention_expires_at
            if retention is None or retention.tzinfo is None:
                raise LifecycleConflictError("execution_evidence_retention_missing")
            if any(
                item.retention_expires_at != retention.astimezone(dt.UTC)
                for item in evidence.artifacts
            ):
                raise LifecycleConflictError("execution_evidence_retention_mismatch")
        elif legacy_never_evidence:
            if completion.evidence_retention_expires_at is not None:
                raise LifecycleConflictError("legacy_evidence_retention_is_unsupported")
        elif completion.evidence_retention_expires_at is not None:
            raise LifecycleConflictError("retention_requires_execution_evidence")

        return {
            "reuse_identity": (
                identity.model_dump(mode="json") if identity is not None else None
            ),
            "reuse_identity_hash": identity_hash,
            "reused_from_run_id": source_run_id,
            "source_evidence_fingerprint": source_fingerprint,
            "reuse_decision": decision,
            "reuse_reason": completion.reuse_reason or decision.value,
            "reuse_candidate_metadata": None,
            "evidence_retention_expires_at": completion.evidence_retention_expires_at,
        }

    async def _validate_completion_evidence(
        self, snapshot: LeaseSnapshot, completion: ExecutionCompletion
    ) -> None:
        """Bind worker evidence to the exact leased run and approved work order."""

        evidence = completion.evidence_metadata
        if evidence is None:
            if completion.artifact_metadata:
                raise LifecycleConflictError("artifacts_require_execution_evidence")
            return
        order = await self.get_work_order(snapshot.work_order_id, refresh=True)
        if (
            evidence.run_id != snapshot.execution_run_id
            or evidence.work_order_id != snapshot.work_order_id
            or evidence.worker_id != snapshot.worker_id
            or evidence.repository_full_name != order.repository_full_name
            or evidence.tested_sha != order.commit_sha
            or evidence.manifest_name != order.manifest_name
            or evidence.manifest_version != order.manifest_version
            or evidence.manifest_digest != order.manifest_digest
            or evidence.terminal_status != completion.status.value
            or tuple(evidence.artifacts) != completion.artifact_metadata
        ):
            raise LifecycleConflictError("execution_evidence_identity_mismatch")
