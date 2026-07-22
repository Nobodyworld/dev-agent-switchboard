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
    WorkerRegistration,
    WorkOrderDraft,
)
from .enums import (
    ApprovalPolicy,
    ExecutionRunStatus,
    WorkerStatus,
    WorkOrderStatus,
    is_terminal_run,
    is_terminal_work_order,
)
from .evidence import ExecutionEvidence
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
