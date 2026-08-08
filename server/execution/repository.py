"""SQLAlchemy persistence operations for the isolated execution plane."""

from __future__ import annotations

import datetime as dt
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any

from sqlalchemy import case, delete, func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from server.models import (
    CommandManifest,
    ExecutionLease,
    ExecutionRun,
    ExecutionWorker,
    ExecutionWorkOrder,
    WorkerRoutingProfile,
)

from .entities import RoutingQuotaReset
from .enums import (
    ExecutionRunStatus,
    QuotaReservationState,
    ReuseDecision,
    ReusePolicy,
    RoutingPolicy,
    WorkerStatus,
    WorkOrderStatus,
)
from .exceptions import ManifestIntegrityError
from .registry import TrustedManifest

_MAX_EXACT_REUSE_CANDIDATES = 32
_MAX_ROUTING_REVISION = 2_147_483_647


@dataclass(frozen=True, slots=True)
class LeaseSnapshot:
    """Immutable identifiers retained while conditionally consuming a lease."""

    id: int
    work_order_id: int
    execution_run_id: int
    worker_id: str


@dataclass(frozen=True, slots=True)
class RunLeaseWindow:
    """Server-owned assignment and lease-expiry timestamps for one run."""

    assigned_at: dt.datetime
    expires_at: dt.datetime


class ExecutionRepository:
    """Persistence adapter for work orders, workers, runs, and active leases."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def ensure_manifest(self, definition: TrustedManifest) -> CommandManifest:
        """Persist a trusted identity once and reject a conflicting snapshot."""

        existing = await self.get_manifest(definition.name, definition.version)
        if existing is not None:
            if not _matches_trusted_manifest(existing, definition):
                raise ManifestIntegrityError("trusted_manifest_digest_conflict")
            return existing
        manifest = CommandManifest(
            name=definition.name,
            version=definition.version,
            schema_version=definition.schema_version,
            digest=definition.digest,
            description=definition.description,
            trusted_registry_source=definition.registry_source,
            required_capabilities=definition.required_capabilities,
            fixed_step_metadata=definition.fixed_step_metadata,
            environment_policy=definition.environment_policy,
            network_policy=definition.network_policy,
            repository_write_policy=definition.repository_write_policy,
            timeout_seconds=definition.timeout_seconds,
            artifact_declarations=definition.artifact_declarations,
        )
        try:
            async with self.session.begin_nested():
                self.session.add(manifest)
                await self.session.flush()
        except IntegrityError as error:
            existing = await self.get_manifest(definition.name, definition.version)
            if existing is None or not _matches_trusted_manifest(existing, definition):
                raise ManifestIntegrityError(
                    "trusted_manifest_digest_conflict"
                ) from error
            return existing
        return manifest

    async def ensure_manifests(
        self, definitions: Iterable[TrustedManifest]
    ) -> tuple[CommandManifest, ...]:
        """Ensure every static trusted manifest has an immutable DB snapshot."""

        manifests = [
            await self.ensure_manifest(definition) for definition in definitions
        ]
        return tuple(manifests)

    async def get_manifest(self, name: str, version: str) -> CommandManifest | None:
        """Look up a persisted manifest by its immutable public identity."""

        return (
            await self.session.execute(
                select(CommandManifest).where(
                    CommandManifest.name == name,
                    CommandManifest.version == version,
                )
            )
        ).scalar_one_or_none()

    async def list_manifests(self) -> list[CommandManifest]:
        """List trusted manifest snapshots in stable identity order."""

        result = await self.session.execute(
            select(CommandManifest).order_by(
                CommandManifest.name, CommandManifest.version
            )
        )
        return list(result.scalars())

    async def create_work_order(self, values: dict[str, Any]) -> ExecutionWorkOrder:
        """Insert a new pending work order without committing it."""

        work_order = ExecutionWorkOrder(**values)
        self.session.add(work_order)
        await self.session.flush()
        return work_order

    async def get_work_order(
        self, work_order_id: int, *, refresh: bool = False
    ) -> ExecutionWorkOrder | None:
        """Get a work order, optionally bypassing the identity-map snapshot."""

        if refresh:
            result = await self.session.execute(
                select(ExecutionWorkOrder)
                .where(ExecutionWorkOrder.id == work_order_id)
                .execution_options(populate_existing=True)
            )
            return result.scalar_one_or_none()
        return await self.session.get(ExecutionWorkOrder, work_order_id)

    async def list_work_orders(self) -> list[ExecutionWorkOrder]:
        """List work orders in creation order."""

        result = await self.session.execute(
            select(ExecutionWorkOrder).order_by(ExecutionWorkOrder.id)
        )
        return list(result.scalars())

    async def list_queued_work_orders(
        self,
    ) -> list[tuple[ExecutionWorkOrder, CommandManifest]]:
        """Return queued candidates and their persisted trusted snapshots."""

        result = await self.session.execute(
            select(ExecutionWorkOrder, CommandManifest)
            .join(CommandManifest, ExecutionWorkOrder.manifest_id == CommandManifest.id)
            .where(ExecutionWorkOrder.status == WorkOrderStatus.QUEUED)
            .order_by(ExecutionWorkOrder.id)
        )
        return list(result.tuples())

    async def list_workers_with_profiles(
        self,
    ) -> list[tuple[ExecutionWorker, WorkerRoutingProfile | None]]:
        """Return every worker and optional operator profile in stable order."""

        result = await self.session.execute(
            select(ExecutionWorker, WorkerRoutingProfile)
            .outerjoin(
                WorkerRoutingProfile,
                WorkerRoutingProfile.worker_id == ExecutionWorker.worker_id,
            )
            .order_by(ExecutionWorker.worker_id)
            .execution_options(populate_existing=True)
        )
        return list(result.tuples())

    async def upsert_worker(
        self, values: dict[str, Any], *, now: dt.datetime
    ) -> ExecutionWorker:
        """Register or refresh a stable worker while retaining active capacity."""

        worker_id = str(values["worker_id"])
        worker = await self.get_worker(worker_id)
        if worker is None:
            worker = ExecutionWorker(last_heartbeat_at=now, **values)
            self.session.add(worker)
            await self.session.flush()
            return worker

        for name, value in values.items():
            if name not in {"worker_id", "status"}:
                setattr(worker, name, value)
        requested_status = values.get("status", WorkerStatus.ONLINE)
        if requested_status in {
            WorkerStatus.BUSY,
            WorkerStatus.DRAINING,
            WorkerStatus.OFFLINE,
        }:
            worker.status = requested_status
        elif worker.active_run_count >= worker.max_concurrency:
            worker.status = WorkerStatus.BUSY
        else:
            worker.status = WorkerStatus.ONLINE
        worker.last_heartbeat_at = now
        await self.session.flush()
        return worker

    async def get_worker(self, worker_id: str) -> ExecutionWorker | None:
        """Return a worker by stable external identity."""

        return (
            await self.session.execute(
                select(ExecutionWorker).where(ExecutionWorker.worker_id == worker_id)
            )
        ).scalar_one_or_none()

    async def record_checkout_poll(self, worker_id: str, *, now: dt.datetime) -> bool:
        """Record one authenticated pull attempt using server time only."""

        result = await self.session.execute(
            update(ExecutionWorker)
            .where(ExecutionWorker.worker_id == worker_id)
            .values(last_checkout_poll_at=now, updated_at=now)
            .execution_options(synchronize_session=False)
        )
        return _affected_one(result)

    async def get_routing_profile(
        self, worker_id: str, *, refresh: bool = False
    ) -> WorkerRoutingProfile | None:
        """Return one operator-owned routing profile."""

        statement = select(WorkerRoutingProfile).where(
            WorkerRoutingProfile.worker_id == worker_id
        )
        if refresh:
            statement = statement.execution_options(populate_existing=True)
        return (await self.session.execute(statement)).scalar_one_or_none()

    async def list_routing_profiles(self) -> list[WorkerRoutingProfile]:
        """List profiles in stable worker-ID order."""

        result = await self.session.execute(
            select(WorkerRoutingProfile).order_by(WorkerRoutingProfile.worker_id)
        )
        return list(result.scalars())

    async def create_routing_profile(
        self, values: dict[str, Any]
    ) -> WorkerRoutingProfile:
        """Insert one routing profile without committing it."""

        profile = WorkerRoutingProfile(**values)
        self.session.add(profile)
        await self.session.flush()
        return profile

    async def replace_routing_profile(
        self,
        worker_id: str,
        *,
        expected_revision: int,
        values: dict[str, Any],
        now: dt.datetime,
    ) -> bool:
        """Replace a profile only when its optimistic revision still matches."""

        result = await self.session.execute(
            update(WorkerRoutingProfile)
            .where(
                WorkerRoutingProfile.worker_id == worker_id,
                WorkerRoutingProfile.revision == expected_revision,
                WorkerRoutingProfile.revision < _MAX_ROUTING_REVISION,
            )
            .values(**values, revision=expected_revision + 1, updated_at=now)
            .execution_options(synchronize_session=False)
        )
        return _affected_one(result)

    async def reset_routing_quota(
        self,
        worker_id: str,
        *,
        reset: RoutingQuotaReset,
        now: dt.datetime,
    ) -> bool:
        """Replace quota state only at the exact current profile revision."""

        result = await self.session.execute(
            update(WorkerRoutingProfile)
            .where(
                WorkerRoutingProfile.worker_id == worker_id,
                WorkerRoutingProfile.revision == reset.expected_revision,
                WorkerRoutingProfile.revision < _MAX_ROUTING_REVISION,
                WorkerRoutingProfile.quota_capacity_units
                >= reset.quota_remaining_units,
            )
            .values(
                quota_remaining_units=reset.quota_remaining_units,
                quota_reset_at=reset.quota_reset_at,
                revision=reset.expected_revision + 1,
                updated_at=now,
            )
            .execution_options(synchronize_session=False)
        )
        return _affected_one(result)

    async def count_reserved_quota_runs(self, worker_id: str) -> int:
        """Count active reserved quota records for fail-closed operator writes."""

        result = await self.session.execute(
            select(func.count(ExecutionRun.id)).where(
                ExecutionRun.worker_id == worker_id,
                ExecutionRun.route_quota_state == QuotaReservationState.RESERVED,
            )
        )
        return int(result.scalar_one())

    async def reserve_routing_quota(
        self,
        worker_id: str,
        *,
        expected_revision: int,
        units: int,
        now: dt.datetime,
    ) -> int | None:
        """Conditionally reserve quota and return the resulting profile revision."""

        maximum_expected_revision = _MAX_ROUTING_REVISION - (2 if units else 1)
        result = await self.session.execute(
            update(WorkerRoutingProfile)
            .where(
                WorkerRoutingProfile.worker_id == worker_id,
                WorkerRoutingProfile.enabled.is_(True),
                WorkerRoutingProfile.revision == expected_revision,
                WorkerRoutingProfile.revision <= maximum_expected_revision,
                WorkerRoutingProfile.quota_remaining_units >= units,
                WorkerRoutingProfile.quota_remaining_units
                <= WorkerRoutingProfile.quota_capacity_units,
            )
            .values(
                quota_remaining_units=(
                    WorkerRoutingProfile.quota_remaining_units - units
                ),
                revision=expected_revision + 1,
                updated_at=now,
            )
            .execution_options(synchronize_session=False)
        )
        return expected_revision + 1 if _affected_one(result) else None

    async def update_worker_heartbeat(
        self,
        worker: ExecutionWorker,
        *,
        now: dt.datetime,
        status: WorkerStatus | None,
    ) -> ExecutionWorker:
        """Refresh worker liveness without changing its immutable identity fields."""

        worker.last_heartbeat_at = now
        if status is not None:
            if status in {
                WorkerStatus.BUSY,
                WorkerStatus.DRAINING,
                WorkerStatus.OFFLINE,
            }:
                worker.status = status
            elif worker.active_run_count >= worker.max_concurrency:
                worker.status = WorkerStatus.BUSY
            else:
                worker.status = WorkerStatus.ONLINE
        await self.session.flush()
        return worker

    async def reserve_worker_capacity(
        self, worker_id: str, *, now: dt.datetime
    ) -> bool:
        """Atomically reserve one free slot on an online worker."""

        result = await self.session.execute(
            update(ExecutionWorker)
            .where(
                ExecutionWorker.worker_id == worker_id,
                ExecutionWorker.status == WorkerStatus.ONLINE,
                ExecutionWorker.active_run_count < ExecutionWorker.max_concurrency,
            )
            .values(
                active_run_count=ExecutionWorker.active_run_count + 1,
                status=case(
                    (
                        ExecutionWorker.active_run_count + 1
                        >= ExecutionWorker.max_concurrency,
                        WorkerStatus.BUSY,
                    ),
                    else_=WorkerStatus.ONLINE,
                ),
                updated_at=now,
            )
            .execution_options(synchronize_session=False)
        )
        rowcount = getattr(result, "rowcount", None)
        return isinstance(rowcount, int) and rowcount == 1

    async def release_worker_capacity(
        self, worker_id: str, *, now: dt.datetime
    ) -> bool:
        """Release one active worker slot while respecting draining/offline state."""

        result = await self.session.execute(
            update(ExecutionWorker)
            .where(
                ExecutionWorker.worker_id == worker_id,
                ExecutionWorker.active_run_count > 0,
            )
            .values(
                active_run_count=ExecutionWorker.active_run_count - 1,
                status=case(
                    (
                        ExecutionWorker.status.in_(
                            [WorkerStatus.DRAINING, WorkerStatus.OFFLINE]
                        ),
                        ExecutionWorker.status,
                    ),
                    (
                        ExecutionWorker.active_run_count - 1
                        >= ExecutionWorker.max_concurrency,
                        WorkerStatus.BUSY,
                    ),
                    else_=WorkerStatus.ONLINE,
                ),
                updated_at=now,
            )
            .execution_options(synchronize_session=False)
        )
        return _affected_one(result)

    async def claim_queued_work_order(
        self,
        work_order_id: int,
        *,
        now: dt.datetime,
        route_values: dict[str, Any] | None = None,
    ) -> bool:
        """Atomically claim a work order only while it remains queued."""

        result = await self.session.execute(
            update(ExecutionWorkOrder)
            .where(
                ExecutionWorkOrder.id == work_order_id,
                ExecutionWorkOrder.status == WorkOrderStatus.QUEUED,
            )
            .values(
                status=WorkOrderStatus.ASSIGNED,
                assigned_at=now,
                attempt_count=ExecutionWorkOrder.attempt_count + 1,
                updated_at=now,
                **(route_values or {}),
            )
            .execution_options(synchronize_session=False)
        )
        rowcount = getattr(result, "rowcount", None)
        return isinstance(rowcount, int) and rowcount == 1

    async def create_active_run(
        self,
        *,
        work_order: ExecutionWorkOrder,
        worker_id: str,
        lease_window: RunLeaseWindow,
        route_values: dict[str, Any] | None = None,
    ) -> ExecutionRun:
        """Create one historical run and the unique active lease in this transaction."""

        now = lease_window.assigned_at
        expires_at = lease_window.expires_at

        run = ExecutionRun(
            work_order_id=work_order.id,
            worker_id=worker_id,
            attempt_number=work_order.attempt_count,
            status=ExecutionRunStatus.ASSIGNED,
            queued_at=work_order.queued_at or now,
            assigned_at=now,
            lease_expires_at=expires_at,
            last_heartbeat_at=now,
            evidence_metadata={},
            reuse_decision=(
                ReuseDecision.NOT_REQUESTED
                if work_order.reuse_policy == ReusePolicy.NEVER
                else ReuseDecision.PENDING
            ),
            reuse_reason=(
                "reuse_policy_never"
                if work_order.reuse_policy == ReusePolicy.NEVER
                else "exact_candidate_pending"
            ),
            **(
                route_values
                or {
                    "route_schema_version": 1,
                    "routing_policy": RoutingPolicy.FIRST_AVAILABLE,
                    "route_required_quota_units": 0,
                    "route_reserved_quota_units": 0,
                    "route_quota_state": QuotaReservationState.NOT_REQUIRED,
                    "route_eligible_candidate_count": 1,
                    "route_explicit_pin_applied": False,
                    "route_reason": "routing_selected",
                    "route_decided_at": now,
                }
            ),
        )
        self.session.add(run)
        await self.session.flush()
        self.session.add(
            ExecutionLease(
                work_order_id=work_order.id,
                execution_run_id=run.id,
                worker_id=worker_id,
                expires_at=expires_at,
                last_heartbeat_at=now,
            )
        )
        await self.session.flush()
        return run

    async def consume_run_quota_reservation(
        self,
        run_id: int,
        *,
        work_order_id: int,
        now: dt.datetime,
    ) -> bool:
        """Consume a reserved quota record exactly once on first run heartbeat."""

        run = await self.get_run(run_id, refresh=True)
        if run is None:
            return False
        if run.route_quota_state in {
            QuotaReservationState.NOT_REQUIRED,
            QuotaReservationState.CONSUMED,
        }:
            return True
        if run.route_quota_state != QuotaReservationState.RESERVED:
            return False
        run_result = await self.session.execute(
            update(ExecutionRun)
            .where(
                ExecutionRun.id == run_id,
                ExecutionRun.route_quota_state == QuotaReservationState.RESERVED,
            )
            .values(
                route_quota_state=QuotaReservationState.CONSUMED,
                updated_at=now,
            )
            .execution_options(synchronize_session=False)
        )
        order_result = await self.session.execute(
            update(ExecutionWorkOrder)
            .where(
                ExecutionWorkOrder.id == work_order_id,
                ExecutionWorkOrder.route_quota_state == QuotaReservationState.RESERVED,
            )
            .values(
                route_quota_state=QuotaReservationState.CONSUMED,
                updated_at=now,
            )
            .execution_options(synchronize_session=False)
        )
        return _affected_one(run_result) and _affected_one(order_result)

    async def release_run_quota_reservation(
        self,
        run_id: int,
        *,
        work_order_id: int,
        worker_id: str,
        now: dt.datetime,
    ) -> bool:
        """Release one pre-start reservation without exceeding profile capacity."""

        run = await self.get_run(run_id, refresh=True)
        if run is None:
            return False
        if run.route_quota_state in {
            QuotaReservationState.NOT_REQUIRED,
            QuotaReservationState.CONSUMED,
            QuotaReservationState.RELEASED,
        }:
            return True
        if run.route_quota_state != QuotaReservationState.RESERVED:
            return False
        units = run.route_reserved_quota_units
        if units > 0:
            profile_result = await self.session.execute(
                update(WorkerRoutingProfile)
                .where(
                    WorkerRoutingProfile.worker_id == worker_id,
                    WorkerRoutingProfile.revision < _MAX_ROUTING_REVISION,
                    WorkerRoutingProfile.quota_remaining_units
                    <= WorkerRoutingProfile.quota_capacity_units - units,
                )
                .values(
                    quota_remaining_units=(
                        WorkerRoutingProfile.quota_remaining_units + units
                    ),
                    revision=WorkerRoutingProfile.revision + 1,
                    updated_at=now,
                )
                .execution_options(synchronize_session=False)
            )
            if not _affected_one(profile_result):
                return False
        run_result = await self.session.execute(
            update(ExecutionRun)
            .where(
                ExecutionRun.id == run_id,
                ExecutionRun.route_quota_state == QuotaReservationState.RESERVED,
            )
            .values(
                route_quota_state=QuotaReservationState.RELEASED,
                updated_at=now,
            )
            .execution_options(synchronize_session=False)
        )
        order_result = await self.session.execute(
            update(ExecutionWorkOrder)
            .where(
                ExecutionWorkOrder.id == work_order_id,
                ExecutionWorkOrder.route_quota_state == QuotaReservationState.RESERVED,
            )
            .values(
                route_quota_state=QuotaReservationState.RELEASED,
                updated_at=now,
            )
            .execution_options(synchronize_session=False)
        )
        return _affected_one(run_result) and _affected_one(order_result)

    async def list_exact_reuse_candidates(
        self,
        *,
        work_order: ExecutionWorkOrder,
        worker_id: str,
        reuse_identity_hash: str,
        exclude_run_id: int,
    ) -> list[tuple[ExecutionRun, ExecutionWorkOrder]]:
        """Return exact successful fresh candidates in deterministic newest order."""

        result = await self.session.execute(
            select(ExecutionRun, ExecutionWorkOrder)
            .join(
                ExecutionWorkOrder,
                ExecutionRun.work_order_id == ExecutionWorkOrder.id,
            )
            .where(
                ExecutionRun.id != exclude_run_id,
                ExecutionRun.worker_id == worker_id,
                ExecutionRun.status == ExecutionRunStatus.SUCCEEDED,
                ExecutionRun.reuse_decision == ReuseDecision.FRESH,
                ExecutionRun.reuse_identity_hash == reuse_identity_hash,
                ExecutionWorkOrder.repository_full_name
                == work_order.repository_full_name,
                ExecutionWorkOrder.commit_sha == work_order.commit_sha,
                ExecutionWorkOrder.manifest_name == work_order.manifest_name,
                ExecutionWorkOrder.manifest_version == work_order.manifest_version,
                ExecutionWorkOrder.manifest_digest == work_order.manifest_digest,
                ExecutionWorkOrder.execution_policy_hash
                == work_order.execution_policy_hash,
            )
            .order_by(ExecutionRun.id.desc())
            .limit(_MAX_EXACT_REUSE_CANDIDATES)
            .execution_options(populate_existing=True)
        )
        return list(result.tuples())

    async def update_active_run_reuse(
        self,
        run_id: int,
        *,
        values: dict[str, Any],
    ) -> bool:
        """Persist reuse context only while one run remains active."""

        result = await self.session.execute(
            update(ExecutionRun)
            .where(
                ExecutionRun.id == run_id,
                ExecutionRun.status.in_(
                    [ExecutionRunStatus.ASSIGNED, ExecutionRunStatus.RUNNING]
                ),
            )
            .values(**values)
            .execution_options(synchronize_session=False)
        )
        return _affected_one(result)

    async def get_run(
        self, run_id: int, *, refresh: bool = False
    ) -> ExecutionRun | None:
        """Return a historical execution run, optionally bypassing cached state."""

        if refresh:
            result = await self.session.execute(
                select(ExecutionRun)
                .where(ExecutionRun.id == run_id)
                .execution_options(populate_existing=True)
            )
            return result.scalar_one_or_none()
        return await self.session.get(ExecutionRun, run_id)

    async def list_runs(self, work_order_id: int | None = None) -> list[ExecutionRun]:
        """List execution attempts, optionally restricted to one work order."""

        statement = select(ExecutionRun).order_by(ExecutionRun.id)
        if work_order_id is not None:
            statement = statement.where(ExecutionRun.work_order_id == work_order_id)
        result = await self.session.execute(statement)
        return list(result.scalars())

    async def get_lease_for_run(self, run_id: int) -> ExecutionLease | None:
        """Return the active lease attached to a run, if it still exists."""

        return (
            await self.session.execute(
                select(ExecutionLease).where(ExecutionLease.execution_run_id == run_id)
            )
        ).scalar_one_or_none()

    async def get_lease_for_work_order(
        self, work_order_id: int
    ) -> ExecutionLease | None:
        """Return the database-enforced active claim for a work order."""

        return (
            await self.session.execute(
                select(ExecutionLease).where(
                    ExecutionLease.work_order_id == work_order_id
                )
            )
        ).scalar_one_or_none()

    async def get_lease_snapshot_for_run(self, run_id: int) -> LeaseSnapshot | None:
        """Return immutable lease identifiers for a run without trusting ORM state."""

        result = await self.session.execute(
            select(
                ExecutionLease.id,
                ExecutionLease.work_order_id,
                ExecutionLease.execution_run_id,
                ExecutionLease.worker_id,
            ).where(ExecutionLease.execution_run_id == run_id)
        )
        row = result.one_or_none()
        if row is None:
            return None
        return LeaseSnapshot(
            id=row.id,
            work_order_id=row.work_order_id,
            execution_run_id=row.execution_run_id,
            worker_id=row.worker_id,
        )

    async def get_lease_snapshot_for_work_order(
        self, work_order_id: int
    ) -> LeaseSnapshot | None:
        """Return immutable lease identifiers for a work order's active claim."""

        result = await self.session.execute(
            select(
                ExecutionLease.id,
                ExecutionLease.work_order_id,
                ExecutionLease.execution_run_id,
                ExecutionLease.worker_id,
            ).where(ExecutionLease.work_order_id == work_order_id)
        )
        row = result.one_or_none()
        if row is None:
            return None
        return LeaseSnapshot(
            id=row.id,
            work_order_id=row.work_order_id,
            execution_run_id=row.execution_run_id,
            worker_id=row.worker_id,
        )

    async def list_stale_lease_snapshots(
        self, *, now: dt.datetime
    ) -> list[LeaseSnapshot]:
        """Return candidates that must still pass a guarded stale-lease delete."""

        result = await self.session.execute(
            select(
                ExecutionLease.id,
                ExecutionLease.work_order_id,
                ExecutionLease.execution_run_id,
                ExecutionLease.worker_id,
            )
            .where(ExecutionLease.expires_at < now)
            .order_by(ExecutionLease.id)
        )
        return [
            LeaseSnapshot(
                id=row.id,
                work_order_id=row.work_order_id,
                execution_run_id=row.execution_run_id,
                worker_id=row.worker_id,
            )
            for row in result
        ]

    async def renew_owned_live_lease(
        self,
        run_id: int,
        *,
        worker_id: str,
        now: dt.datetime,
        expires_at: dt.datetime,
    ) -> bool:
        """Renew a lease only while its owner still holds an unexpired claim."""

        result = await self.session.execute(
            update(ExecutionLease)
            .where(
                ExecutionLease.execution_run_id == run_id,
                ExecutionLease.worker_id == worker_id,
                ExecutionLease.expires_at >= now,
            )
            .values(last_heartbeat_at=now, expires_at=expires_at)
            .execution_options(synchronize_session=False)
        )
        return _affected_one(result)

    async def consume_lease(
        self,
        snapshot: LeaseSnapshot,
        *,
        now: dt.datetime | None = None,
        require_live: bool = False,
        require_stale: bool = False,
    ) -> bool:
        """Delete exactly one lease when its current state still matches a guard."""

        if require_live and require_stale:
            raise ValueError("lease cannot be both live and stale")
        statement = delete(ExecutionLease).where(
            ExecutionLease.id == snapshot.id,
            ExecutionLease.work_order_id == snapshot.work_order_id,
            ExecutionLease.execution_run_id == snapshot.execution_run_id,
            ExecutionLease.worker_id == snapshot.worker_id,
        )
        if require_live:
            if now is None:
                raise ValueError("live lease consumption requires now")
            statement = statement.where(ExecutionLease.expires_at >= now)
        if require_stale:
            if now is None:
                raise ValueError("stale lease consumption requires now")
            statement = statement.where(ExecutionLease.expires_at < now)
        result = await self.session.execute(statement)
        return _affected_one(result)

    async def mark_active_run_running(
        self, run_id: int, *, now: dt.datetime, expires_at: dt.datetime
    ) -> bool:
        """Record a heartbeat only while the run is in an active lifecycle state."""

        result = await self.session.execute(
            update(ExecutionRun)
            .where(
                ExecutionRun.id == run_id,
                ExecutionRun.status.in_(
                    [ExecutionRunStatus.ASSIGNED, ExecutionRunStatus.RUNNING]
                ),
            )
            .values(
                status=case(
                    (
                        ExecutionRun.status == ExecutionRunStatus.ASSIGNED,
                        ExecutionRunStatus.RUNNING,
                    ),
                    else_=ExecutionRun.status,
                ),
                started_at=case(
                    (ExecutionRun.status == ExecutionRunStatus.ASSIGNED, now),
                    else_=ExecutionRun.started_at,
                ),
                last_heartbeat_at=now,
                lease_expires_at=expires_at,
            )
            .execution_options(synchronize_session=False)
        )
        return _affected_one(result)

    async def mark_active_work_order_running(
        self, work_order_id: int, *, now: dt.datetime
    ) -> bool:
        """Advance an assigned/running work order using a guarded update."""

        result = await self.session.execute(
            update(ExecutionWorkOrder)
            .where(
                ExecutionWorkOrder.id == work_order_id,
                ExecutionWorkOrder.status.in_(
                    [WorkOrderStatus.ASSIGNED, WorkOrderStatus.RUNNING]
                ),
            )
            .values(
                status=case(
                    (
                        ExecutionWorkOrder.status == WorkOrderStatus.ASSIGNED,
                        WorkOrderStatus.RUNNING,
                    ),
                    else_=ExecutionWorkOrder.status,
                ),
                started_at=case(
                    (ExecutionWorkOrder.status == WorkOrderStatus.ASSIGNED, now),
                    else_=ExecutionWorkOrder.started_at,
                ),
                updated_at=now,
            )
            .execution_options(synchronize_session=False)
        )
        return _affected_one(result)

    async def finish_active_run(
        self,
        run_id: int,
        *,
        values: dict[str, Any],
    ) -> bool:
        """Terminalize one active run after its lease has been exclusively consumed."""

        result = await self.session.execute(
            update(ExecutionRun)
            .where(
                ExecutionRun.id == run_id,
                ExecutionRun.status.in_(
                    [ExecutionRunStatus.ASSIGNED, ExecutionRunStatus.RUNNING]
                ),
            )
            .values(**values)
            .execution_options(synchronize_session=False)
        )
        return _affected_one(result)

    async def finish_active_work_order(
        self,
        work_order_id: int,
        *,
        status: WorkOrderStatus,
        now: dt.datetime,
        terminal_reason: str,
    ) -> bool:
        """Terminalize one active work order after its lease has been consumed."""

        result = await self.session.execute(
            update(ExecutionWorkOrder)
            .where(
                ExecutionWorkOrder.id == work_order_id,
                ExecutionWorkOrder.status.in_(
                    [WorkOrderStatus.ASSIGNED, WorkOrderStatus.RUNNING]
                ),
            )
            .values(
                status=status,
                finished_at=now,
                terminal_reason=terminal_reason,
                updated_at=now,
            )
            .execution_options(synchronize_session=False)
        )
        return _affected_one(result)

    async def requeue_stale_active_run(self, run_id: int, *, now: dt.datetime) -> bool:
        """Mark an active run timed out after exclusively consuming its stale lease."""

        return await self.finish_active_run(
            run_id,
            values={
                "status": ExecutionRunStatus.TIMED_OUT,
                "finished_at": now,
                "last_heartbeat_at": now,
                "result_summary": None,
                "terminal_reason": "execution_lease_expired",
                "cleanup_status": "lease_expired",
                "artifact_metadata": [],
                "evidence_metadata": {},
            },
        )

    async def requeue_stale_active_work_order(
        self, work_order_id: int, *, now: dt.datetime
    ) -> bool:
        """Move an active work order back to queued after a stale lease timeout."""

        result = await self.session.execute(
            update(ExecutionWorkOrder)
            .where(
                ExecutionWorkOrder.id == work_order_id,
                ExecutionWorkOrder.status.in_(
                    [WorkOrderStatus.ASSIGNED, WorkOrderStatus.RUNNING]
                ),
            )
            .values(
                status=WorkOrderStatus.QUEUED,
                queued_at=now,
                updated_at=now,
                terminal_reason=None,
            )
            .execution_options(synchronize_session=False)
        )
        return _affected_one(result)

    async def transition_unleased_work_order(
        self,
        work_order_id: int,
        *,
        current_statuses: tuple[WorkOrderStatus, ...],
        values: dict[str, Any],
    ) -> bool:
        """Apply a lifecycle transition only while an unleased state still matches."""

        result = await self.session.execute(
            update(ExecutionWorkOrder)
            .where(
                ExecutionWorkOrder.id == work_order_id,
                ExecutionWorkOrder.status.in_(current_statuses),
            )
            .values(**values)
            .execution_options(synchronize_session=False)
        )
        return _affected_one(result)

    async def list_stale_leases(self, *, now: dt.datetime) -> list[ExecutionLease]:
        """List active execution claims whose heartbeat deadline has elapsed."""

        result = await self.session.execute(
            select(ExecutionLease)
            .where(ExecutionLease.expires_at < now)
            .order_by(ExecutionLease.id)
        )
        return list(result.scalars())

    async def delete_lease(self, lease: ExecutionLease) -> None:
        """Release only the active lease; leave the historical run intact."""

        await self.session.delete(lease)
        await self.session.flush()

    async def delete_lease_for_work_order(self, work_order_id: int) -> None:
        """Delete a work-order lease when an administrator terminalizes it."""

        await self.session.execute(
            delete(ExecutionLease).where(ExecutionLease.work_order_id == work_order_id)
        )
        await self.session.flush()


def _matches_trusted_manifest(
    persisted: CommandManifest, definition: TrustedManifest
) -> bool:
    """Return whether every persisted manifest field matches its static source."""

    return (
        persisted.schema_version == definition.schema_version
        and persisted.digest == definition.digest
        and persisted.description == definition.description
        and persisted.trusted_registry_source == definition.registry_source
        and persisted.required_capabilities == definition.required_capabilities
        and persisted.fixed_step_metadata == definition.fixed_step_metadata
        and persisted.environment_policy == definition.environment_policy
        and persisted.network_policy == definition.network_policy
        and persisted.repository_write_policy == definition.repository_write_policy
        and persisted.timeout_seconds == definition.timeout_seconds
        and persisted.artifact_declarations == definition.artifact_declarations
    )


def _affected_one(result: object) -> bool:
    """Return whether a guarded DML statement claimed exactly one database row."""

    rowcount = getattr(result, "rowcount", None)
    return isinstance(rowcount, int) and rowcount == 1
