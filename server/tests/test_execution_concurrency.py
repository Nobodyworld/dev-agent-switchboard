"""Independent-session, file-backed SQLite concurrency tests for execution."""

from __future__ import annotations

import asyncio
import datetime as dt

import pytest
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from server.db import Base
from server.execution.entities import (
    ExecutionCompletion,
    WorkerRegistration,
    WorkOrderDraft,
)
from server.execution.enums import (
    ApprovalPolicy,
    ExecutionRunStatus,
    NetworkPolicy,
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
