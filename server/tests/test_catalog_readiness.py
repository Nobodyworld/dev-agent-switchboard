"""File-backed regression coverage for the bounded catalog-readiness view."""

from __future__ import annotations

import datetime as dt
import json
from collections.abc import Sequence
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import HTTPException, status
from sqlalchemy import event, select
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from server.api.routers import execution as execution_router
from server.api.routers.execution import get_catalog_readiness
from server.db import Base
from server.execution.entities import (
    RoutingProfileDraft,
    WorkerRegistration,
    WorkOrderDraft,
)
from server.execution.enums import (
    ApprovalPolicy,
    ExecutionRunStatus,
    NetworkPolicy,
    ReuseDecision,
    RoutingPolicy,
    WorkerStatus,
    WorkOrderStatus,
)
from server.execution.repository import ExecutionRepository
from server.execution.service import ExecutionService
from server.models import (
    ExecutionLease,
    ExecutionRun,
    ExecutionWorker,
    ExecutionWorkOrder,
    WorkerRoutingProfile,
)

_NOW = dt.datetime(2026, 8, 17, 3, 0, 0, tzinfo=dt.UTC).replace(tzinfo=None)
_SWITCHBOARD = "Nobodyworld/dev-agent-switchboard"
_ACCOUNTING = "Nobodyworld/app-accounting-modular"
_ZSCRIPTS = "Nobodyworld/dev-logger-zscripts"
_INDUSTRY = "Nobodyworld/app-industry-resilience"
_PUBLIC_CATALOG_ENTRY_COUNT = 4
_DIGEST_PREFIX_LENGTH = 12
_CHEAPEST_CANDIDATE_COUNT = 2
_CATALOG_WORKER_LIMIT = 100


def _service(session: AsyncSession) -> ExecutionService:
    return ExecutionService(
        repository=ExecutionRepository(session),
        clock=lambda: _NOW,
        lease_seconds=lambda: 60,
        routing_freshness_seconds=lambda: (300, 300),
    )


async def _new_factory(
    tmp_path: Path, name: str
) -> tuple[AsyncEngine, async_sessionmaker[AsyncSession]]:
    database = tmp_path / f"{name}.db"
    engine = create_async_engine(f"sqlite+aiosqlite:///{database}")
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    return engine, factory


def _worker(  # noqa: PLR0913 - explicit runtime values keep mismatch fixtures legible.
    worker_id: str,
    *,
    repositories: tuple[str, ...],
    python_version: str = "3.13.1",
    node_version: str = "v24.12.0",
    pnpm_version: str = "10.18.1",
    max_concurrency: int = 4,
) -> WorkerRegistration:
    return WorkerRegistration(
        worker_id=worker_id,
        display_name=worker_id,
        operating_system="windows",
        architecture="x86_64",
        python_version=python_version,
        node_version=node_version,
        pnpm_version=pnpm_version,
        docker_available=False,
        browsers=(),
        gpu_available=False,
        unity_available=False,
        desktop_available=False,
        capabilities={"git_available": True},
        repository_full_names=repositories,
        max_concurrency=max_concurrency,
        network_policy_capability=NetworkPolicy.WORKER_RESTRICTED,
        repository_write_capability=False,
        status=WorkerStatus.ONLINE,
    )


def _profile(
    worker_id: str,
    *,
    cost: int,
    remaining: int,
    enabled: bool = True,
) -> RoutingProfileDraft:
    return RoutingProfileDraft(
        schema_version=1,
        worker_id=worker_id,
        enabled=enabled,
        estimated_cost_units_per_run=cost,
        quota_capacity_units=20,
        quota_remaining_units=remaining,
        quota_reset_at=None,
        routing_priority=0,
    )


async def _record_active_poll(service: ExecutionService, worker_id: str) -> None:
    assert await service._repository.record_checkout_poll(worker_id, now=_NOW)


def _switchboard_draft(*, preferred_executor: str | None = None) -> WorkOrderDraft:
    return WorkOrderDraft(
        schema_version=1,
        repository_full_name=_SWITCHBOARD,
        commit_sha="c" * 40,
        manifest_name="validate-switchboard",
        manifest_version="1",
        manifest_parameters={},
        required_capabilities={},
        permitted_paths=("server",),
        forbidden_scope_notes="read-only catalog readiness agreement",
        expected_artifact_kinds=("command-log",),
        approval_policy=ApprovalPolicy.EXPLICIT,
        timeout_seconds=3600,
        resource_metadata={},
        network_policy=NetworkPolicy.WORKER_RESTRICTED,
        repository_write_allowed=False,
        preferred_executor=preferred_executor,
        cost_ceiling=None,
        routing_policy=RoutingPolicy.FIRST_AVAILABLE,
        maximum_cost_units=None,
        required_quota_units=0,
    )


async def _snapshot(factory: async_sessionmaker[AsyncSession]) -> dict[str, object]:
    """Read route-sensitive state in a distinct session for mutation assertions."""

    async with factory() as session:
        workers = list(
            (
                await session.execute(
                    select(ExecutionWorker).order_by(ExecutionWorker.worker_id)
                )
            ).scalars()
        )
        profiles = list(
            (
                await session.execute(
                    select(WorkerRoutingProfile).order_by(
                        WorkerRoutingProfile.worker_id
                    )
                )
            ).scalars()
        )
        orders = list(
            (
                await session.execute(
                    select(ExecutionWorkOrder).order_by(ExecutionWorkOrder.id)
                )
            ).scalars()
        )
        runs = list(
            (
                await session.execute(select(ExecutionRun).order_by(ExecutionRun.id))
            ).scalars()
        )
        leases = list(
            (
                await session.execute(
                    select(ExecutionLease).order_by(ExecutionLease.id)
                )
            ).scalars()
        )
    return {
        "workers": [
            (
                item.worker_id,
                item.active_run_count,
                item.status.value,
                item.last_heartbeat_at,
                item.last_checkout_poll_at,
                item.updated_at,
            )
            for item in workers
        ],
        "profiles": [
            (
                item.worker_id,
                item.enabled,
                item.quota_remaining_units,
                item.revision,
                item.updated_at,
            )
            for item in profiles
        ],
        "orders": [
            (
                item.id,
                item.status.value,
                item.attempt_count,
                item.route_selected_worker_id,
                item.route_profile_revision,
                item.route_reserved_quota_units,
                item.route_decided_at,
                item.updated_at,
            )
            for item in orders
        ],
        "runs": [
            (
                item.id,
                item.status.value,
                item.route_quota_state.value,
                item.updated_at,
            )
            for item in runs
        ],
        "leases": [
            (item.id, item.work_order_id, item.execution_run_id) for item in leases
        ],
    }


async def _insert_latest_zscripts_result(service: ExecutionService) -> None:
    """Seed a compact persisted reused success without invoking a worker."""

    manifests = await service.sync_trusted_manifests()
    manifest = next(
        item
        for item in manifests
        if item.name == "validate-zscripts" and item.version == "1"
    )
    session = service._repository.session
    for attempt_number, decision, finished_at in (
        (1, ReuseDecision.FRESH, _NOW - dt.timedelta(seconds=10)),
        (2, ReuseDecision.REUSED, _NOW),
    ):
        order = ExecutionWorkOrder(
            schema_version=1,
            repository_full_name=_ZSCRIPTS,
            commit_sha=("a" if attempt_number == 1 else "b") * 40,
            manifest_id=manifest.id,
            manifest_name=manifest.name,
            manifest_version=manifest.version,
            manifest_digest=manifest.digest,
            manifest_parameters={},
            required_capabilities={},
            permitted_paths=(),
            forbidden_scope_notes="synthetic latest-result projection",
            expected_artifact_kinds=(),
            approval_policy=ApprovalPolicy.EXPLICIT,
            status=WorkOrderStatus.SUCCEEDED,
            timeout_seconds=3600,
            resource_metadata={},
            network_policy=NetworkPolicy.WORKER_RESTRICTED,
            repository_write_allowed=False,
            preferred_executor=None,
            cost_ceiling=None,
            routing_policy=RoutingPolicy.FIRST_AVAILABLE,
            maximum_cost_units=None,
            required_quota_units=0,
            execution_policy_hash="f" * 64,
            attempt_count=attempt_number,
            approved_at=_NOW,
            queued_at=_NOW,
            finished_at=finished_at,
        )
        session.add(order)
        await session.flush()
        session.add(
            ExecutionRun(
                work_order_id=order.id,
                worker_id="worker-zscripts",
                attempt_number=attempt_number,
                status=ExecutionRunStatus.SUCCEEDED,
                queued_at=_NOW - dt.timedelta(seconds=20),
                assigned_at=_NOW - dt.timedelta(seconds=10),
                started_at=(
                    _NOW - dt.timedelta(seconds=7)
                    if decision == ReuseDecision.FRESH
                    else finished_at
                ),
                finished_at=finished_at,
                lease_expires_at=_NOW,
                last_heartbeat_at=finished_at,
                evidence_metadata={
                    "steps": [{"id": "quality-gate"}],
                    "private_sentinel": "C:\\private-catalog-sentinel",
                },
                reuse_decision=decision,
                route_schema_version=1,
                routing_policy=RoutingPolicy.FIRST_AVAILABLE,
                route_required_quota_units=0,
                route_reserved_quota_units=0,
            )
        )
    await session.flush()


@pytest.mark.asyncio
async def test_catalog_readiness_file_sqlite_is_safe_bounded_and_read_only(
    tmp_path: Path,
) -> None:
    engine, factory = await _new_factory(tmp_path, "catalog-readiness")
    try:
        async with factory() as session:
            service = _service(session)
            await service.register_worker(
                _worker("worker-zscripts", repositories=(_ZSCRIPTS,))
            )
            await _record_active_poll(service, "worker-zscripts")
            await _insert_latest_zscripts_result(service)
            await session.commit()

        before = await _snapshot(factory)
        async with factory() as session:
            payload = (await get_catalog_readiness(_service(session))).model_dump(
                mode="json"
            )

        assert [item["repository"] for item in payload["entries"]] == [
            _ACCOUNTING,
            _INDUSTRY,
            _SWITCHBOARD,
            _ZSCRIPTS,
        ]
        assert len(payload["entries"]) == _PUBLIC_CATALOG_ENTRY_COUNT
        zscripts = next(
            item for item in payload["entries"] if item["repository"] == _ZSCRIPTS
        )
        assert zscripts["default_manifest"] == {
            "name": "validate-zscripts",
            "version": "1",
            "digest_prefix": zscripts["default_manifest"]["digest_prefix"],
        }
        assert (
            len(zscripts["default_manifest"]["digest_prefix"]) == _DIGEST_PREFIX_LENGTH
        )
        assert zscripts["runtime_requirements"] == {
            "python": ">=3.11",
            "node": ">=24.12.0",
            "pnpm": "=10.18.1",
        }
        assert zscripts["latest_result"] == {
            "reuse_decision": "reused",
            "duration_seconds": 0,
            "step_count": 1,
            "avoided_work_count": 1,
        }
        assert zscripts["source_availability"] == {
            "status": "requires_exact_source",
            "caveat": (
                "Exact source availability requires an operator-configured canonical "
                "checkout at the requested SHA."
            ),
        }
        serialized = json.dumps(payload, sort_keys=True)
        for prohibited in (
            '"argv"',
            '"environment"',
            '"working_directory"',
            "private-catalog-sentinel",
            "C:\\\\",
        ):
            assert prohibited not in serialized
        assert await _snapshot(factory) == before
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_catalog_readiness_worker_overflow_is_bounded_stable_and_non_mutating(
    tmp_path: Path,
) -> None:
    engine, factory = await _new_factory(tmp_path, "catalog-worker-overflow")
    worker_ids = [f"worker-{index:03d}" for index in range(_CATALOG_WORKER_LIMIT + 1)]
    try:
        async with factory() as session:
            service = _service(session)
            for worker_id in reversed(worker_ids):
                await service.register_worker(
                    _worker(worker_id, repositories=(_SWITCHBOARD,))
                )
                await _record_active_poll(service, worker_id)
            await session.commit()

        async with factory() as session:
            snapshot = await ExecutionRepository(
                session
            ).list_catalog_readiness_workers()
        assert snapshot.limit_exceeded
        assert len(snapshot.workers) == _CATALOG_WORKER_LIMIT
        assert [worker.worker_id for worker, _profile in snapshot.workers] == sorted(
            worker_ids
        )[:_CATALOG_WORKER_LIMIT]

        before = await _snapshot(factory)
        worker_selects: list[tuple[str, object]] = []

        def capture_worker_select(
            _connection: object,
            _cursor: object,
            statement: str,
            parameters: object,
            _context: object,
            _executemany: bool,
        ) -> None:
            if statement.lstrip().upper().startswith("SELECT") and (
                "FROM execution_workers" in statement
            ):
                worker_selects.append((statement, parameters))

        event.listen(engine.sync_engine, "before_cursor_execute", capture_worker_select)
        try:
            async with factory() as session:
                with (
                    patch.object(
                        ExecutionRepository,
                        "list_workers_with_profiles",
                        new_callable=AsyncMock,
                        side_effect=AssertionError(
                            "catalog readiness must not use the unbounded worker read"
                        ),
                    ),
                    patch.object(
                        execution_router,
                        "CatalogReadinessEntryOut",
                        side_effect=AssertionError(
                            "overflow must stop before response-model construction"
                        ),
                    ),
                    pytest.raises(HTTPException) as error,
                ):
                    await get_catalog_readiness(_service(session))
        finally:
            event.remove(
                engine.sync_engine, "before_cursor_execute", capture_worker_select
            )

        assert error.value.status_code == status.HTTP_503_SERVICE_UNAVAILABLE
        assert error.value.detail == "catalog_readiness_worker_limit_exceeded"
        assert len(worker_selects) == 1
        statement, parameters = worker_selects[0]
        assert "ORDER BY execution_workers.worker_id" in statement
        assert "LIMIT" in statement
        assert _CATALOG_WORKER_LIMIT + 1 in parameters
        assert await _snapshot(factory) == before

        async with factory() as session:
            service = _service(session)
            evaluations, selected = await service.assess_repository_readiness(
                repository_full_name=_SWITCHBOARD,
                manifest_name="validate-switchboard",
                manifest_version="1",
                routing_policy=RoutingPolicy.FIRST_AVAILABLE,
                maximum_cost_units=None,
                required_quota_units=0,
                preferred_executor=None,
            )
            assert len(evaluations) == len(worker_ids)
            assert all(item.candidate is not None for item in evaluations)
            assert selected is None

            work_order = await service.create_work_order(_switchboard_draft())
            await service.approve_work_order(work_order.id)
            checkout = await service.checkout(worker_ids[0])
            assert checkout.assigned
            assert checkout.work_order_id == work_order.id
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_catalog_readiness_requires_advertisement_and_runtime_mismatches(
    tmp_path: Path,
) -> None:
    engine, factory = await _new_factory(tmp_path, "catalog-runtime-mismatches")
    try:
        async with factory() as session:
            service = _service(session)
            await service.register_worker(
                _worker(
                    "worker-zscripts-node-mismatch",
                    repositories=(_ZSCRIPTS,),
                    python_version="3.11.9",
                    node_version="v20.0.0",
                )
            )
            await service.register_worker(
                _worker(
                    "worker-zscripts-pnpm-mismatch",
                    repositories=(_ZSCRIPTS,),
                    python_version="3.11.9",
                    pnpm_version="10.18.2",
                )
            )
            await service.register_worker(
                _worker(
                    "worker-industry-python-mismatch",
                    repositories=(_INDUSTRY,),
                    python_version="3.12.9",
                )
            )
            for worker_id in (
                "worker-zscripts-node-mismatch",
                "worker-zscripts-pnpm-mismatch",
                "worker-industry-python-mismatch",
            ):
                await _record_active_poll(service, worker_id)
            await session.commit()

            zscripts_evaluations, _ = await service.assess_repository_readiness(
                repository_full_name=_ZSCRIPTS,
                manifest_name="validate-zscripts",
                manifest_version="1",
                routing_policy=RoutingPolicy.FIRST_AVAILABLE,
                maximum_cost_units=None,
                required_quota_units=0,
                preferred_executor=None,
            )
            all_reasons = {
                reason for item in zscripts_evaluations for reason in item.reasons
            }
            assert "node_version_too_old_or_missing" in all_reasons
            assert "pnpm_version_mismatch_or_missing" in all_reasons

            results = await service.assess_catalog_readiness()
            by_repository = {item.repository_full_name: item for item in results}
            assert by_repository[_ZSCRIPTS].ready_count == 0
            assert by_repository[_ZSCRIPTS].primary_blocker_code == (
                "manifest_capability_mismatch"
            )
            assert by_repository[_INDUSTRY].primary_blocker_code == (
                "manifest_capability_mismatch"
            )
            assert by_repository[_ACCOUNTING].primary_blocker_code == (
                "repository_unavailable"
            )
            assert by_repository[_SWITCHBOARD].primary_blocker_code == (
                "repository_unavailable"
            )
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_catalog_readiness_assessment_and_checkout_agree_for_first_available(
    tmp_path: Path,
) -> None:
    engine, factory = await _new_factory(tmp_path, "catalog-route-agreement")
    try:
        async with factory() as session:
            service = _service(session)
            await service.register_worker(
                _worker(
                    "worker-switchboard",
                    repositories=(_SWITCHBOARD,),
                    python_version="3.11.9",
                )
            )
            await _record_active_poll(service, "worker-switchboard")
            await session.commit()

        async with factory() as session:
            service = _service(session)
            catalog = {
                item.repository_full_name: item
                for item in await service.assess_catalog_readiness()
            }
            evaluations, selected = await service.assess_repository_readiness(
                repository_full_name=_SWITCHBOARD,
                manifest_name="validate-switchboard",
                manifest_version="1",
                routing_policy=RoutingPolicy.FIRST_AVAILABLE,
                maximum_cost_units=None,
                required_quota_units=0,
                preferred_executor=None,
            )
            assert catalog[_SWITCHBOARD].ready_count == 1
            assert sum(item.candidate is not None for item in evaluations) == 1
            assert selected is None

            work_order = await service.create_work_order(_switchboard_draft())
            await service.approve_work_order(work_order.id)
            checkout = await service.checkout("worker-switchboard")
            assert checkout.assigned
            assert checkout.work_order_id == work_order.id
            await session.commit()
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_routing_profiles_and_hard_pins_remain_authoritative_for_readiness(
    tmp_path: Path,
) -> None:
    engine, factory = await _new_factory(tmp_path, "catalog-routing-policy")
    try:
        async with factory() as session:
            service = _service(session)
            for registration in (
                _worker(
                    "worker-profile-free",
                    repositories=(_ACCOUNTING,),
                    python_version="3.12.9",
                ),
                _worker(
                    "worker-cheap", repositories=(_ACCOUNTING,), python_version="3.12.9"
                ),
                _worker(
                    "worker-expensive",
                    repositories=(_ACCOUNTING,),
                    python_version="3.12.9",
                ),
                _worker(
                    "worker-pinned-mismatch",
                    repositories=(_ACCOUNTING,),
                    python_version="3.11.9",
                ),
            ):
                await service.register_worker(registration)
                await _record_active_poll(service, registration.worker_id)
            await service.create_routing_profile(
                _profile("worker-cheap", cost=1, remaining=5)
            )
            await service.create_routing_profile(
                _profile("worker-expensive", cost=9, remaining=20)
            )
            await service.create_routing_profile(
                _profile("worker-pinned-mismatch", cost=0, remaining=20)
            )

            first_available, _ = await service.assess_repository_readiness(
                repository_full_name=_ACCOUNTING,
                manifest_name="validate-accounting-modular",
                manifest_version="1",
                routing_policy=RoutingPolicy.FIRST_AVAILABLE,
                maximum_cost_units=None,
                required_quota_units=0,
                preferred_executor=None,
            )
            profile_free = next(
                item
                for item in first_available
                if item.worker.worker_id == "worker-profile-free"
            )
            assert profile_free.candidate is not None

            cheapest, selected = await service.assess_repository_readiness(
                repository_full_name=_ACCOUNTING,
                manifest_name="validate-accounting-modular",
                manifest_version="1",
                routing_policy=RoutingPolicy.CHEAPEST_CAPABLE,
                maximum_cost_units=10,
                required_quota_units=5,
                preferred_executor=None,
            )
            assert (
                len([item for item in cheapest if item.candidate is not None])
                == _CHEAPEST_CANDIDATE_COUNT
            )
            assert selected is not None and selected.worker.worker_id == "worker-cheap"

            pinned, pinned_selected = await service.assess_repository_readiness(
                repository_full_name=_ACCOUNTING,
                manifest_name="validate-accounting-modular",
                manifest_version="1",
                routing_policy=RoutingPolicy.CHEAPEST_CAPABLE,
                maximum_cost_units=10,
                required_quota_units=5,
                preferred_executor="worker-pinned-mismatch",
            )
            assert pinned_selected is None
            alternate = next(
                item for item in pinned if item.worker.worker_id == "worker-cheap"
            )
            assert "preferred_executor_mismatch" in alternate.reasons
    finally:
        await engine.dispose()


async def _cheap_selection_after_registration_order(
    tmp_path: Path,
    name: str,
    registration_order: Sequence[str],
) -> tuple[str | None, int]:
    engine, factory = await _new_factory(tmp_path, name)
    try:
        async with factory() as session:
            service = _service(session)
            registrations = {
                "worker-a": _worker(
                    "worker-a", repositories=(_ACCOUNTING,), python_version="3.12.9"
                ),
                "worker-b": _worker(
                    "worker-b", repositories=(_ACCOUNTING,), python_version="3.12.9"
                ),
            }
            for worker_id in registration_order:
                await service.register_worker(registrations[worker_id])
                await _record_active_poll(service, worker_id)
            await service.create_routing_profile(
                _profile("worker-a", cost=2, remaining=20)
            )
            await service.create_routing_profile(
                _profile("worker-b", cost=2, remaining=20)
            )
            evaluations, selected = await service.assess_repository_readiness(
                repository_full_name=_ACCOUNTING,
                manifest_name="validate-accounting-modular",
                manifest_version="1",
                routing_policy=RoutingPolicy.CHEAPEST_CAPABLE,
                maximum_cost_units=None,
                required_quota_units=1,
                preferred_executor=None,
            )
            return (
                selected.worker.worker_id if selected is not None else None,
                sum(item.candidate is not None for item in evaluations),
            )
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_catalog_readiness_routing_selection_is_insertion_order_independent(
    tmp_path: Path,
) -> None:
    first = await _cheap_selection_after_registration_order(
        tmp_path,
        "catalog-order-first",
        ("worker-b", "worker-a"),
    )
    second = await _cheap_selection_after_registration_order(
        tmp_path,
        "catalog-order-second",
        ("worker-a", "worker-b"),
    )
    assert first == ("worker-a", 2)
    assert second == first
