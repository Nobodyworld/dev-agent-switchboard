"""Validated lifecycle service for persisted execution-plane contracts."""

from __future__ import annotations

import datetime as dt
import re
from collections.abc import Callable

from sqlalchemy.exc import IntegrityError

from server.models import (
    CommandManifest,
    ExecutionRun,
    ExecutionWorker,
    ExecutionWorkOrder,
)

from .capabilities import match_worker_capabilities
from .entities import (
    CheckoutResult,
    ExecutionCompletion,
    ExpiryResult,
    ReuseCandidateResult,
    WorkerRegistration,
    WorkOrderDraft,
)
from .enums import (
    ApprovalPolicy,
    ExecutionRunStatus,
    ReuseDecision,
    ReusePolicy,
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
from .registry import (
    TRUSTED_REPOSITORIES,
    get_trusted_manifest,
    iter_trusted_manifests,
)
from .repository import ExecutionRepository, LeaseSnapshot

_SHA_PATTERN = re.compile(r"^[0-9a-fA-F]{40}$")


class ExecutionService:
    """Orchestrate the isolated, non-executing execution control plane."""

    def __init__(
        self,
        *,
        repository: ExecutionRepository,
        clock: Callable[[], dt.datetime],
        lease_seconds: Callable[[], int],
    ) -> None:
        self._repository = repository
        self._clock = clock
        self._lease_seconds = lease_seconds

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
        definition = get_trusted_manifest(draft.manifest_name, draft.manifest_version)
        if definition is None:
            raise UnknownManifestError("trusted_manifest_not_found")
        unsupported = set(draft.manifest_parameters) - definition.allowed_parameters
        if unsupported:
            names = ",".join(sorted(unsupported))
            raise ManifestParameterError(f"unsupported_manifest_parameters:{names}")

        manifest = await self._repository.ensure_manifest(definition)
        execution_policy_hash = compute_execution_policy_hash(
            manifest_parameters=draft.manifest_parameters,
            required_capabilities=draft.required_capabilities,
            permitted_paths=draft.permitted_paths,
            expected_artifact_kinds=draft.expected_artifact_kinds,
            timeout_seconds=draft.timeout_seconds,
            network_policy=draft.network_policy.value,
            repository_write_allowed=False,
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
                "docker_available": registration.docker_available,
                "browsers": list(registration.browsers),
                "gpu_available": registration.gpu_available,
                "unity_available": registration.unity_available,
                "desktop_available": registration.desktop_available,
                "capabilities": dict(registration.capabilities),
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

    async def checkout(self, worker_id: str) -> CheckoutResult:
        """Atomically assign one capability-compatible queued work order."""

        await self.sync_trusted_manifests()
        await self.expire_stale_leases()
        worker = await self._repository.get_worker(worker_id)
        if worker is None:
            raise ExecutionNotFoundError("worker_not_found")
        unavailable = self._unavailable_worker_result(worker)
        if unavailable is not None:
            return unavailable
        return await self._checkout_eligible_work(worker)

    async def _checkout_eligible_work(self, worker: ExecutionWorker) -> CheckoutResult:
        """Claim one compatible order after worker availability has been checked."""

        candidates = await self._repository.list_queued_work_orders()
        mismatch_reasons: list[str] = []
        for work_order, manifest in candidates:
            capability_match = match_worker_capabilities(
                worker,
                manifest_requirements=manifest.required_capabilities,
                requested_requirements=work_order.required_capabilities,
                network_policy=work_order.network_policy,
            )
            if not capability_match.eligible:
                mismatch_reasons.extend(capability_match.reasons)
                continue
            now = self._clock()
            expires_at = now + dt.timedelta(seconds=self._lease_seconds())
            try:
                async with self._repository.session.begin_nested():
                    reserved = await self._repository.reserve_worker_capacity(
                        worker.worker_id, now=now
                    )
                    if not reserved:
                        return CheckoutResult(None, None, "worker_concurrency_limit")
                    claimed = await self._repository.claim_queued_work_order(
                        work_order.id, now=now
                    )
                    if not claimed:
                        released = await self._repository.release_worker_capacity(
                            worker.worker_id, now=now
                        )
                        if not released:
                            raise LifecycleConflictError(
                                "worker_capacity_release_failed"
                            )
                        continue
                    claimed_order = await self._repository.get_work_order(
                        work_order.id, refresh=True
                    )
                    if claimed_order is None:  # pragma: no cover - defensive guard
                        raise ExecutionNotFoundError("work_order_not_found")
                    run = await self._repository.create_active_run(
                        work_order=claimed_order,
                        worker_id=worker.worker_id,
                        now=now,
                        expires_at=expires_at,
                    )
                    return CheckoutResult(run.id, claimed_order.id, None)
            except IntegrityError:
                # The unique active-lease invariant caught a concurrent claim.
                return CheckoutResult(None, None, "checkout_conflict")
        if mismatch_reasons:
            return CheckoutResult(
                None,
                None,
                "capability_mismatch",
                tuple(dict.fromkeys(mismatch_reasons)),
            )
        return CheckoutResult(None, None, "no_queued_work_orders")

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
            run_updated = await self._repository.mark_active_run_running(
                run_id, now=now, expires_at=expires_at
            )
            work_order_updated = await self._repository.mark_active_work_order_running(
                snapshot.work_order_id, now=now
            )
            if not run_updated or not work_order_updated:
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
                if not run_updated or not work_order_updated or not released:
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
            if not run_updated or not work_order_updated or not released:
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
