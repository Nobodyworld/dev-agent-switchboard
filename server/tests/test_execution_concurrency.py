# ruff: noqa: PLR0915, PLR2004
"""Independent-session, file-backed SQLite concurrency tests for execution."""

from __future__ import annotations

import asyncio
import datetime as dt
from dataclasses import replace

import pytest
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from server.db import Base
from server.execution.entities import (
    ExecutionCompletion,
    RoutingProfileDraft,
    WorkerRegistration,
    WorkOrderDraft,
)
from server.execution.enums import (
    ApprovalPolicy,
    ExecutionRunStatus,
    NetworkPolicy,
    QuotaReservationState,
    RoutingPolicy,
    WorkerStatus,
    WorkOrderStatus,
)
from server.execution.exceptions import LifecycleConflictError, OwnershipConflictError
from server.execution.repository import ExecutionRepository
from server.execution.service import ExecutionService
from server.models import (
    ExecutionLease,
    ExecutionRun,
    ExecutionWorker,
    ExecutionWorkOrder,
    WorkerRoutingProfile,
)
from server.time_utils import utcnow_naive


def _draft() -> WorkOrderDraft:
    return WorkOrderDraft(
        schema_version=1,
        repository_full_name="Nobodyworld/dev-agent-switchboard",
        commit_sha="b" * 40,
        manifest_name="validate-switchboard",
        manifest_version="1",
        manifest_parameters={},
        required_capabilities={},
        permitted_paths=("server",),
        forbidden_scope_notes="read-only",
        expected_artifact_kinds=("command-log",),
        approval_policy=ApprovalPolicy.EXPLICIT,
        timeout_seconds=3600,
        resource_metadata={},
        network_policy=NetworkPolicy.WORKER_RESTRICTED,
        repository_write_allowed=False,
        preferred_executor=None,
        cost_ceiling=None,
    )


def _routed_draft(*, required_quota_units: int = 3) -> WorkOrderDraft:
    return replace(
        _draft(),
        routing_policy=RoutingPolicy.CHEAPEST_CAPABLE,
        maximum_cost_units=100,
        required_quota_units=required_quota_units,
    )


def _profile(worker_id: str, *, cost: int) -> RoutingProfileDraft:
    return RoutingProfileDraft(
        schema_version=1,
        worker_id=worker_id,
        enabled=True,
        estimated_cost_units_per_run=cost,
        quota_capacity_units=20,
        quota_remaining_units=20,
        quota_reset_at=None,
        routing_priority=0,
    )


def _worker(worker_id: str) -> WorkerRegistration:
    return WorkerRegistration(
        worker_id=worker_id,
        display_name=worker_id,
        operating_system="linux",
        architecture="x86_64",
        python_version="3.11.0",
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


def _service(session) -> ExecutionService:
    return ExecutionService(
        repository=ExecutionRepository(session),
        clock=utcnow_naive,
        lease_seconds=lambda: 60,
    )


def _service_at(session, *, now: dt.datetime, lease_seconds: int) -> ExecutionService:
    return ExecutionService(
        repository=ExecutionRepository(session),
        clock=lambda: now,
        lease_seconds=lambda: lease_seconds,
    )


def _base_time() -> dt.datetime:
    return utcnow_naive().replace(
        year=2026,
        month=7,
        day=12,
        hour=12,
        minute=0,
        second=0,
        microsecond=0,
    )


async def _seed_active_assignment(
    factory,
    *,
    worker_id: str,
    now: dt.datetime,
    lease_seconds: int,
) -> tuple[int, int]:
    async with factory() as session:
        service = _service_at(session, now=now, lease_seconds=lease_seconds)
        await service.register_worker(_worker(worker_id))
        work_order = await service.create_work_order(_draft())
        await service.approve_work_order(work_order.id)
        assignment = await service.checkout(worker_id)
        assert assignment.run_id is not None
        await session.commit()
        return work_order.id, assignment.run_id


async def _load_active_state(
    factory,
    *,
    worker_id: str,
    work_order_id: int,
    run_id: int,
) -> tuple[ExecutionRun, ExecutionWorkOrder, int, ExecutionWorker]:
    async with factory() as session:
        run = await session.get(ExecutionRun, run_id)
        persisted_order = await session.get(ExecutionWorkOrder, work_order_id)
        lease_count = await session.scalar(
            select(func.count()).select_from(ExecutionLease)
        )
        worker = await session.scalar(
            select(ExecutionWorker).where(ExecutionWorker.worker_id == worker_id)
        )
    assert run is not None
    assert persisted_order is not None
    assert isinstance(lease_count, int)
    assert worker is not None
    return run, persisted_order, lease_count, worker


@pytest.mark.asyncio
async def test_two_workers_concurrently_checkout_exactly_one_run_file_backed_sqlite(
    tmp_path,
) -> None:
    database = tmp_path / "execution-concurrency.db"
    engine = create_async_engine(
        f"sqlite+aiosqlite:///{database}",
        connect_args={"timeout": 30},
    )
    factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        async with factory() as session:
            service = _service(session)
            await service.register_worker(_worker("worker-race-a"))
            await service.register_worker(_worker("worker-race-b"))
            work_order = await service.create_work_order(_draft())
            await service.approve_work_order(work_order.id)
            await session.commit()

        start = asyncio.Event()

        async def attempt(worker_id: str):
            await start.wait()
            async with factory() as session:
                result = await _service(session).checkout(worker_id)
                await session.commit()
                return result

        first_task = asyncio.create_task(attempt("worker-race-a"))
        second_task = asyncio.create_task(attempt("worker-race-b"))
        start.set()
        results = await asyncio.gather(first_task, second_task)
        winners = [result for result in results if result.assigned]
        losers = [result for result in results if not result.assigned]
        assert len(winners) == 1
        assert len(losers) == 1
        assert losers[0].reason in {"no_queued_work_orders", "checkout_conflict"}

        async with factory() as session:
            lease_count = await session.scalar(
                select(func.count()).select_from(ExecutionLease)
            )
            run_count = await session.scalar(
                select(func.count()).select_from(ExecutionRun)
            )
            work_order = await session.scalar(select(ExecutionWorkOrder))
            assert lease_count == 1
            assert run_count == 1
            assert work_order is not None
            assert work_order.status.value == "assigned"
            assert work_order.attempt_count == 1
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_database_unique_lease_enforces_one_active_run_and_attempts_are_per_order(
    tmp_path,
) -> None:
    database = tmp_path / "execution-invariant.db"
    engine = create_async_engine(f"sqlite+aiosqlite:///{database}")
    factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        async with factory() as session:
            service = _service(session)
            await service.register_worker(_worker("worker-invariant"))
            first_order = await service.create_work_order(_draft())
            second_order = await service.create_work_order(_draft())
            await service.approve_work_order(first_order.id)
            await service.approve_work_order(second_order.id)
            first_claim = await service.checkout("worker-invariant")
            assert first_claim.run_id is not None
            first_run = await service.get_run(first_claim.run_id)
            assert first_run.attempt_number == 1
            await service.cancel_work_order(first_order.id, reason="release_capacity")
            second_claim = await service.checkout("worker-invariant")
            assert second_claim.run_id is not None
            second_run = await service.get_run(second_claim.run_id)
            assert second_run.attempt_number == 1
            await session.commit()

        async with factory() as session:
            existing_lease = await session.scalar(select(ExecutionLease))
            assert existing_lease is not None
            timestamp = utcnow_naive().replace(
                year=2026,
                month=7,
                day=12,
                hour=12,
                minute=0,
                second=0,
                microsecond=0,
            )
            duplicate_run = ExecutionRun(
                work_order_id=existing_lease.work_order_id,
                worker_id=existing_lease.worker_id,
                attempt_number=2,
                status=ExecutionRunStatus.ASSIGNED,
                queued_at=timestamp,
                assigned_at=timestamp,
                lease_expires_at=timestamp + dt.timedelta(seconds=60),
                last_heartbeat_at=timestamp,
            )
            session.add(duplicate_run)
            await session.flush()
            session.add(
                ExecutionLease(
                    work_order_id=existing_lease.work_order_id,
                    execution_run_id=duplicate_run.id,
                    worker_id=existing_lease.worker_id,
                    expires_at=timestamp + dt.timedelta(seconds=60),
                    last_heartbeat_at=timestamp,
                )
            )
            with pytest.raises(IntegrityError):
                await session.flush()
            await session.rollback()
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_heartbeat_and_stale_expiry_race_preserves_one_consistent_outcome(
    tmp_path,
) -> None:
    """A stale expiry cannot delete a lease that a concurrent heartbeat renewed."""

    database = tmp_path / "execution-heartbeat-expiry-race.db"
    engine = create_async_engine(
        f"sqlite+aiosqlite:///{database}",
        connect_args={"timeout": 30},
    )
    factory = async_sessionmaker(engine, expire_on_commit=False)
    initial = _base_time()
    try:
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        work_order_id, run_id = await _seed_active_assignment(
            factory,
            worker_id="worker-heartbeat-expiry",
            now=initial,
            lease_seconds=1,
        )

        gate = asyncio.Event()
        renewed_at = initial + dt.timedelta(milliseconds=500)
        stale_at = initial + dt.timedelta(seconds=2)

        async def heartbeat() -> str:
            await gate.wait()
            async with factory() as session:
                service = _service_at(session, now=renewed_at, lease_seconds=60)
                try:
                    await service.heartbeat_run(
                        run_id, worker_id="worker-heartbeat-expiry"
                    )
                except OwnershipConflictError:
                    await session.rollback()
                    return "lost"
                await session.commit()
                return "renewed"

        async def expire() -> tuple[int, ...]:
            await gate.wait()
            async with factory() as session:
                service = _service_at(session, now=stale_at, lease_seconds=60)
                result = await service.expire_stale_leases()
                await session.commit()
                return result.requeued_work_order_ids

        heartbeat_task = asyncio.create_task(heartbeat())
        expiry_task = asyncio.create_task(expire())
        gate.set()
        heartbeat_result, requeued = await asyncio.gather(heartbeat_task, expiry_task)

        run, persisted_order, lease_count, worker = await _load_active_state(
            factory,
            worker_id="worker-heartbeat-expiry",
            work_order_id=work_order_id,
            run_id=run_id,
        )
        if heartbeat_result == "renewed":
            assert requeued == ()
            assert run.status == ExecutionRunStatus.RUNNING
            assert persisted_order.status == WorkOrderStatus.RUNNING
            assert lease_count == 1
            assert worker.active_run_count == 1
        else:
            assert requeued == (work_order_id,)
            assert run.status == ExecutionRunStatus.TIMED_OUT
            assert persisted_order.status == WorkOrderStatus.QUEUED
            assert lease_count == 0
            assert worker.active_run_count == 0
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_completion_and_cancellation_race_terminalize_once(
    tmp_path,
) -> None:
    """Only the actor that consumes the lease may finish and release capacity."""

    database = tmp_path / "execution-complete-cancel-race.db"
    engine = create_async_engine(
        f"sqlite+aiosqlite:///{database}",
        connect_args={"timeout": 30},
    )
    factory = async_sessionmaker(engine, expire_on_commit=False)
    initial = _base_time()
    try:
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        work_order_id, run_id = await _seed_active_assignment(
            factory,
            worker_id="worker-complete-cancel",
            now=initial,
            lease_seconds=60,
        )

        gate = asyncio.Event()
        terminal_at = initial + dt.timedelta(seconds=1)

        async def complete() -> str:
            await gate.wait()
            async with factory() as session:
                service = _service_at(session, now=terminal_at, lease_seconds=60)
                try:
                    await service.complete_run(
                        run_id,
                        worker_id="worker-complete-cancel",
                        completion=ExecutionCompletion(
                            status=ExecutionRunStatus.SUCCEEDED
                        ),
                    )
                except OwnershipConflictError:
                    await session.rollback()
                    return "lost"
                await session.commit()
                return "succeeded"

        async def cancel() -> str:
            await gate.wait()
            async with factory() as session:
                service = _service_at(session, now=terminal_at, lease_seconds=60)
                try:
                    await service.cancel_work_order(work_order_id, reason="operator")
                except LifecycleConflictError:
                    await session.rollback()
                    return "lost"
                await session.commit()
                return "cancelled"

        completion_task = asyncio.create_task(complete())
        cancellation_task = asyncio.create_task(cancel())
        gate.set()
        results = await asyncio.gather(completion_task, cancellation_task)
        assert sorted(results) in (["cancelled", "lost"], ["lost", "succeeded"])

        run, persisted_order, lease_count, worker = await _load_active_state(
            factory,
            worker_id="worker-complete-cancel",
            work_order_id=work_order_id,
            run_id=run_id,
        )
        assert (run.status, persisted_order.status) in {
            (ExecutionRunStatus.SUCCEEDED, WorkOrderStatus.SUCCEEDED),
            (ExecutionRunStatus.CANCELLED, WorkOrderStatus.CANCELLED),
        }
        assert lease_count == 0
        assert worker.active_run_count == 0
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_routed_concurrent_sessions_select_only_cheapest_active_worker(
    tmp_path,
) -> None:
    """Committed poll state makes the deterministic winner authoritative."""

    database = tmp_path / "execution-routing-concurrency.db"
    engine = create_async_engine(
        f"sqlite+aiosqlite:///{database}", connect_args={"timeout": 30}
    )
    factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        async with factory() as session:
            service = _service(session)
            for worker_id, cost in (("worker-cheap", 2), ("worker-expensive", 9)):
                await service.register_worker(_worker(worker_id))
                await service.create_routing_profile(_profile(worker_id, cost=cost))
                polled = await service.checkout(worker_id)
                assert polled.reason == "no_queued_work_orders"
            work_order = await service.create_work_order(_routed_draft())
            await service.approve_work_order(work_order.id)
            await session.commit()

        gate = asyncio.Event()

        async def attempt(worker_id: str):
            await gate.wait()
            async with factory() as session:
                result = await _service(session).checkout(worker_id)
                await session.commit()
                return result

        cheap_task = asyncio.create_task(attempt("worker-cheap"))
        expensive_task = asyncio.create_task(attempt("worker-expensive"))
        gate.set()
        cheap_result, expensive_result = await asyncio.gather(
            cheap_task, expensive_task
        )

        assert cheap_result.assigned
        assert not expensive_result.assigned
        assert expensive_result.reason in {
            "better_candidate_active",
            "no_queued_work_orders",
        }
        async with factory() as session:
            runs = list((await session.execute(select(ExecutionRun))).scalars())
            leases = list((await session.execute(select(ExecutionLease))).scalars())
            profiles = {
                item.worker_id: item
                for item in (
                    await session.execute(select(WorkerRoutingProfile))
                ).scalars()
            }
            workers = {
                item.worker_id: item
                for item in (await session.execute(select(ExecutionWorker))).scalars()
            }
            assert len(runs) == 1
            assert len(leases) == 1
            assert runs[0].worker_id == "worker-cheap"
            assert runs[0].route_eligible_candidate_count == 2
            assert runs[0].route_profile_revision == 2
            assert profiles["worker-cheap"].quota_remaining_units == 17
            assert profiles["worker-expensive"].quota_remaining_units == 20
            assert workers["worker-cheap"].active_run_count == 1
            assert workers["worker-expensive"].active_run_count == 0
    finally:
        await engine.dispose()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("failure_point", "expected_reason"),
    [
        ("capacity", "worker_concurrency_limit"),
        ("quota", "routing_reservation_conflict"),
        ("claim", "checkout_conflict"),
        ("run_or_lease", "checkout_conflict"),
    ],
)
async def test_routed_checkout_failure_rolls_back_every_mutation(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
    failure_point: str,
    expected_reason: str,
) -> None:
    """Each conditional-write loss rolls back capacity, quota, order, run, and lease."""

    database = tmp_path / f"execution-routing-rollback-{failure_point}.db"
    engine = create_async_engine(f"sqlite+aiosqlite:///{database}")
    factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        async with factory() as session:
            service = _service(session)
            await service.register_worker(_worker("worker-rollback"))
            await service.create_routing_profile(_profile("worker-rollback", cost=1))
            work_order = await service.create_work_order(_routed_draft())
            await service.approve_work_order(work_order.id)
            await session.commit()

        async with factory() as session:
            repository = ExecutionRepository(session)
            service = ExecutionService(
                repository=repository,
                clock=utcnow_naive,
                lease_seconds=lambda: 60,
            )
            create_active_run = repository.create_active_run

            async def fail_capacity(*_args, **_kwargs) -> bool:
                return False

            async def fail_quota(*_args, **_kwargs) -> None:
                return None

            async def fail_claim(*_args, **_kwargs) -> bool:
                return False

            async def fail_run(*_args, **_kwargs):
                await create_active_run(*_args, **_kwargs)
                raise IntegrityError("forced run failure", {}, RuntimeError())

            if failure_point == "capacity":
                monkeypatch.setattr(
                    repository, "reserve_worker_capacity", fail_capacity
                )
            elif failure_point == "quota":
                monkeypatch.setattr(repository, "reserve_routing_quota", fail_quota)
            elif failure_point == "claim":
                monkeypatch.setattr(repository, "claim_queued_work_order", fail_claim)
            else:
                monkeypatch.setattr(repository, "create_active_run", fail_run)

            result = await service.checkout("worker-rollback")
            assert not result.assigned
            assert result.reason == expected_reason
            await session.commit()

        async with factory() as session:
            worker = await session.scalar(select(ExecutionWorker))
            profile = await session.scalar(select(WorkerRoutingProfile))
            work_order = await session.scalar(select(ExecutionWorkOrder))
            run_count = await session.scalar(select(func.count(ExecutionRun.id)))
            lease_count = await session.scalar(select(func.count(ExecutionLease.id)))
            assert worker is not None
            assert profile is not None
            assert work_order is not None
            assert worker.active_run_count == 0
            assert worker.status == WorkerStatus.ONLINE
            assert profile.quota_remaining_units == 20
            assert profile.revision == 1
            assert work_order.status == WorkOrderStatus.QUEUED
            assert work_order.attempt_count == 0
            assert work_order.route_provenance is None
            assert run_count == 0
            assert lease_count == 0
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_stale_prestart_routed_lease_releases_once_and_requeues_once(
    tmp_path,
) -> None:
    database = tmp_path / "execution-routing-stale-release.db"
    engine = create_async_engine(f"sqlite+aiosqlite:///{database}")
    factory = async_sessionmaker(engine, expire_on_commit=False)
    assigned_at = _base_time()
    try:
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        async with factory() as session:
            service = _service_at(session, now=assigned_at, lease_seconds=30)
            await service.register_worker(_worker("worker-stale-routing"))
            await service.create_routing_profile(
                _profile("worker-stale-routing", cost=1)
            )
            work_order = await service.create_work_order(_routed_draft())
            await service.approve_work_order(work_order.id)
            assignment = await service.checkout("worker-stale-routing")
            assert assignment.assigned
            await session.commit()

        expired_at = assigned_at + dt.timedelta(seconds=31)
        async with factory() as session:
            first = await _service_at(
                session, now=expired_at, lease_seconds=30
            ).expire_stale_leases()
            await session.commit()
            assert first.requeued_work_order_ids == (work_order.id,)
            assert first.timed_out_run_ids == (assignment.run_id,)

        async with factory() as session:
            second = await _service_at(
                session, now=expired_at, lease_seconds=30
            ).expire_stale_leases()
            await session.commit()
            assert second.requeued_work_order_ids == ()
            profile = await session.scalar(select(WorkerRoutingProfile))
            run = await session.get(ExecutionRun, assignment.run_id)
            persisted = await session.get(ExecutionWorkOrder, work_order.id)
            assert profile is not None
            assert run is not None
            assert persisted is not None
            assert profile.quota_remaining_units == 20
            assert profile.revision == 3
            assert run.route_quota_state == QuotaReservationState.RELEASED
            assert run.status == ExecutionRunStatus.TIMED_OUT
            assert persisted.status == WorkOrderStatus.QUEUED
            assert persisted.route_quota_state == QuotaReservationState.RELEASED

            retry_service = _service_at(session, now=expired_at, lease_seconds=30)
            await retry_service.heartbeat_worker("worker-stale-routing")
            retry = await retry_service.checkout("worker-stale-routing")
            assert retry.assigned
            assert retry.run_id != assignment.run_id
            await session.commit()
            await session.refresh(profile)
            await session.refresh(persisted)
            assert profile.quota_remaining_units == 17
            assert profile.revision == 4
            assert persisted.attempt_count == 2
            assert persisted.route_quota_state == QuotaReservationState.RESERVED
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_stale_started_routed_lease_requeues_without_quota_refund(
    tmp_path,
) -> None:
    database = tmp_path / "execution-routing-stale-consumed.db"
    engine = create_async_engine(f"sqlite+aiosqlite:///{database}")
    factory = async_sessionmaker(engine, expire_on_commit=False)
    assigned_at = _base_time()
    try:
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        async with factory() as session:
            service = _service_at(session, now=assigned_at, lease_seconds=30)
            await service.register_worker(_worker("worker-stale-consumed"))
            await service.create_routing_profile(
                _profile("worker-stale-consumed", cost=1)
            )
            work_order = await service.create_work_order(_routed_draft())
            await service.approve_work_order(work_order.id)
            assignment = await service.checkout("worker-stale-consumed")
            assert assignment.assigned
            await session.commit()

        heartbeat_at = assigned_at + dt.timedelta(seconds=1)
        async with factory() as session:
            service = _service_at(session, now=heartbeat_at, lease_seconds=30)
            running = await service.heartbeat_run(
                assignment.run_id,
                worker_id="worker-stale-consumed",
            )
            assert running.route_quota_state == QuotaReservationState.CONSUMED
            await session.commit()

        expired_at = heartbeat_at + dt.timedelta(seconds=31)
        async with factory() as session:
            expired = await _service_at(
                session, now=expired_at, lease_seconds=30
            ).expire_stale_leases()
            await session.commit()
            assert expired.requeued_work_order_ids == (work_order.id,)
            profile = await session.scalar(select(WorkerRoutingProfile))
            run = await session.get(ExecutionRun, assignment.run_id)
            persisted = await session.get(ExecutionWorkOrder, work_order.id)
            assert profile is not None
            assert run is not None
            assert persisted is not None
            assert profile.quota_remaining_units == 17
            assert profile.revision == 2
            assert run.route_quota_state == QuotaReservationState.CONSUMED
            assert persisted.route_quota_state == QuotaReservationState.CONSUMED
            assert persisted.status == WorkOrderStatus.QUEUED
    finally:
        await engine.dispose()
