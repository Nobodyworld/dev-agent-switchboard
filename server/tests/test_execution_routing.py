# ruff: noqa: PLR0913, PLR2004
"""Focused coverage for operator-owned cheapest-capable local routing."""

from __future__ import annotations

import datetime as dt
from dataclasses import replace
from http import HTTPStatus

import pytest
from httpx import ASGITransport, AsyncClient
from pydantic import ValidationError
from sqlalchemy import func, select

from server.app import app
from server.db import AsyncSessionLocal
from server.execution.entities import (
    ExecutionCompletion,
    RoutingProfileDraft,
    RoutingProfileReplacement,
    RoutingQuotaReset,
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
)
from server.execution.exceptions import (
    ExecutionNotFoundError,
    LifecycleConflictError,
    OwnershipConflictError,
)
from server.execution.repository import ExecutionRepository
from server.execution.routing import (
    RoutingCandidate,
    evaluate_routing_candidate,
    rank_routing_candidates,
)
from server.execution.schemas import (
    RoutingQuotaResetIn,
    WorkerHeartbeatIn,
    WorkerRegistrationIn,
    WorkerRoutingProfileCreateIn,
    WorkOrderCreateIn,
)
from server.execution.service import ExecutionService
from server.models import (
    CommandManifest,
    ExecutionLease,
    ExecutionRun,
    ExecutionWorker,
    ExecutionWorkOrder,
    WorkerRoutingProfile,
)
from server.settings import reload_admin_token

_SHA = "d" * 40
_NOW = dt.datetime(2026, 7, 31, 12, 0, 0, tzinfo=dt.UTC).replace(tzinfo=None)


def _service(session, *, now: dt.datetime = _NOW) -> ExecutionService:
    return ExecutionService(
        repository=ExecutionRepository(session),
        clock=lambda: now,
        lease_seconds=lambda: 60,
        routing_freshness_seconds=lambda: (300, 60),
    )


def _worker(
    worker_id: str,
    *,
    max_concurrency: int = 4,
    status: WorkerStatus = WorkerStatus.ONLINE,
    docker_available: bool = False,
    network_policy: NetworkPolicy = NetworkPolicy.WORKER_RESTRICTED,
    repository_full_names: tuple[str, ...] = ("Nobodyworld/dev-agent-switchboard",),
    python_version: str = "3.11.9",
    capabilities: dict[str, object] | None = None,
) -> WorkerRegistration:
    return WorkerRegistration(
        worker_id=worker_id,
        display_name=worker_id,
        operating_system="linux",
        architecture="x86_64",
        python_version=python_version,
        node_version="20.0.0",
        docker_available=docker_available,
        browsers=("chromium",),
        gpu_available=False,
        unity_available=False,
        desktop_available=False,
        capabilities=capabilities or {},
        max_concurrency=max_concurrency,
        network_policy_capability=network_policy,
        repository_write_capability=False,
        status=status,
        repository_full_names=repository_full_names,
    )


def _draft(
    *,
    routing_policy: RoutingPolicy = RoutingPolicy.FIRST_AVAILABLE,
    maximum_cost_units: int | None = None,
    required_quota_units: int = 0,
    preferred_executor: str | None = None,
    required_capabilities: dict[str, object] | None = None,
    cost_ceiling: float | None = 0.0,
    repository_full_name: str = "Nobodyworld/dev-agent-switchboard",
    manifest_name: str = "validate-switchboard",
) -> WorkOrderDraft:
    return WorkOrderDraft(
        schema_version=1,
        repository_full_name=repository_full_name,
        commit_sha=_SHA,
        manifest_name=manifest_name,
        manifest_version="1",
        manifest_parameters={},
        required_capabilities=required_capabilities or {},
        permitted_paths=("server", "client"),
        forbidden_scope_notes="local read-only validation",
        expected_artifact_kinds=("command-log",),
        approval_policy=ApprovalPolicy.EXPLICIT,
        timeout_seconds=3600,
        resource_metadata={},
        network_policy=NetworkPolicy.WORKER_RESTRICTED,
        repository_write_allowed=False,
        preferred_executor=preferred_executor,
        cost_ceiling=cost_ceiling,
        routing_policy=routing_policy,
        maximum_cost_units=maximum_cost_units,
        required_quota_units=required_quota_units,
    )


def _profile(
    worker_id: str,
    *,
    cost: int,
    capacity: int = 100,
    remaining: int = 100,
    priority: int = 0,
    enabled: bool = True,
) -> RoutingProfileDraft:
    return RoutingProfileDraft(
        schema_version=1,
        worker_id=worker_id,
        enabled=enabled,
        estimated_cost_units_per_run=cost,
        quota_capacity_units=capacity,
        quota_remaining_units=remaining,
        quota_reset_at=None,
        routing_priority=priority,
    )


async def _approved(service: ExecutionService, draft: WorkOrderDraft) -> int:
    order = await service.create_work_order(draft)
    await service.approve_work_order(order.id)
    return order.id


async def _active_poll(service: ExecutionService, worker_id: str) -> None:
    result = await service.checkout(worker_id)
    assert not result.assigned
    assert result.reason == "no_queued_work_orders"


def test_routing_schema_defaults_and_rejects_unknown_or_unbounded_values() -> None:
    base = {
        "repository_full_name": "Nobodyworld/dev-agent-switchboard",
        "commit_sha": _SHA,
        "manifest": {"name": "validate-switchboard", "version": "1"},
    }
    defaulted = WorkOrderCreateIn.model_validate(base)
    assert defaulted.routing_policy == RoutingPolicy.FIRST_AVAILABLE
    assert defaulted.maximum_cost_units is None
    assert defaulted.required_quota_units == 0

    legacy = WorkOrderCreateIn.model_validate({**base, "cost_ceiling": 0.125})
    assert legacy.cost_ceiling == 0.125
    assert legacy.maximum_cost_units is None

    for payload in (
        {**base, "routing_policy": "random"},
        {**base, "maximum_cost_units": 2_147_483_648},
        {**base, "maximum_cost_units": 1.0},
        {**base, "required_quota_units": -1},
        {**base, "required_quota_units": 1.0},
        {**base, "routing_profile": {"enabled": True}},
    ):
        with pytest.raises(ValidationError):
            WorkOrderCreateIn.model_validate(payload)


def test_worker_inputs_cannot_author_profiles_or_poll_freshness() -> None:
    registration = {
        "worker_id": "worker-untrusted",
        "display_name": "worker-untrusted",
        "operating_system": "linux",
        "architecture": "x86_64",
    }
    for field, value in (
        ("estimated_cost_units_per_run", 1),
        ("quota_remaining_units", 10),
        ("routing_priority", 0),
        ("last_checkout_poll_at", "2026-07-31T12:00:00Z"),
    ):
        with pytest.raises(ValidationError):
            WorkerRegistrationIn.model_validate({**registration, field: value})

    with pytest.raises(ValidationError):
        WorkerHeartbeatIn.model_validate({"quota_remaining_units": 10})
    with pytest.raises(ValidationError):
        WorkerHeartbeatIn.model_validate(
            {"last_checkout_poll_at": "2026-07-31T12:00:00Z"}
        )


def test_profile_schema_enforces_integer_and_timestamp_invariants() -> None:
    base = {
        "worker_id": "worker-profile",
        "estimated_cost_units_per_run": 1,
        "quota_capacity_units": 10,
        "quota_remaining_units": 10,
    }
    WorkerRoutingProfileCreateIn.model_validate(base)
    for payload in (
        {**base, "estimated_cost_units_per_run": -1},
        {**base, "routing_priority": 2_147_483_648},
        {**base, "quota_remaining_units": 11},
        {**base, "quota_reset_at": "2026-07-31T12:00:00"},
        {**base, "estimated_cost_units_per_run": 1.5},
        {**base, "quota_capacity_units": 10.0},
        {**base, "enabled": 1},
    ):
        with pytest.raises(ValidationError):
            WorkerRoutingProfileCreateIn.model_validate(payload)

    with pytest.raises(ValidationError):
        RoutingQuotaResetIn.model_validate(
            {
                "expected_revision": 1,
                "quota_remaining_units": 10,
                "quota_reset_at": "2026-07-31T12:00:00",
            }
        )


@pytest.mark.asyncio
async def test_first_available_works_without_profile_or_poll_history() -> None:
    async with AsyncSessionLocal() as session:
        service = _service(session)
        await service.register_worker(_worker("worker-legacy"))
        order_id = await _approved(service, _draft(cost_ceiling=0.0))
        result = await service.checkout("worker-legacy")
        assert result.assigned
        order = await service.get_work_order(order_id, refresh=True)
        run = await service.get_run(result.run_id or 0)

        assert order.routing_policy == RoutingPolicy.FIRST_AVAILABLE
        assert order.cost_ceiling == 0.0
        assert order.maximum_cost_units is None
        assert run.route_profile_revision is None
        assert run.route_estimated_cost_units is None
        assert run.route_quota_state == QuotaReservationState.NOT_REQUIRED


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "routing_policy",
    [RoutingPolicy.FIRST_AVAILABLE, RoutingPolicy.CHEAPEST_CAPABLE],
)
async def test_repository_mapping_precedes_capacity_and_quota_reservation(
    routing_policy: RoutingPolicy,
) -> None:
    accounting = "Nobodyworld/app-accounting-modular"
    async with AsyncSessionLocal() as session:
        service = _service(session)
        await service.register_worker(
            _worker(
                "worker-unmapped-repository",
                python_version="3.12.4",
                capabilities={"git_available": True},
            )
        )
        await service.register_worker(
            _worker(
                "worker-mapped-repository",
                repository_full_names=(accounting,),
                python_version="3.12.4",
                capabilities={"git_available": True},
            )
        )
        if routing_policy == RoutingPolicy.CHEAPEST_CAPABLE:
            await service.create_routing_profile(
                _profile("worker-unmapped-repository", cost=1, remaining=20)
            )
            await service.create_routing_profile(
                _profile("worker-mapped-repository", cost=5, remaining=20)
            )
            await _active_poll(service, "worker-unmapped-repository")
            await _active_poll(service, "worker-mapped-repository")
        order_id = await _approved(
            service,
            _draft(
                routing_policy=routing_policy,
                required_quota_units=(
                    2 if routing_policy == RoutingPolicy.CHEAPEST_CAPABLE else 0
                ),
                repository_full_name=accounting,
                manifest_name="validate-accounting-modular",
            ),
        )

        refused = await service.checkout("worker-unmapped-repository")
        assert not refused.assigned
        assert "worker_repository_unavailable" in refused.mismatch_reasons
        if routing_policy == RoutingPolicy.FIRST_AVAILABLE:
            assert refused.reason == "worker_repository_unavailable"
        unmapped = await service._repository.get_worker("worker-unmapped-repository")
        assert unmapped is not None
        assert unmapped.active_run_count == 0
        if routing_policy == RoutingPolicy.CHEAPEST_CAPABLE:
            unmapped_profile = await service.get_routing_profile(
                "worker-unmapped-repository"
            )
            assert unmapped_profile.quota_remaining_units == 20

        claimed = await service.checkout("worker-mapped-repository")
        assert claimed.assigned
        assert claimed.work_order_id == order_id


@pytest.mark.asyncio
async def test_unmapped_hard_pin_never_falls_back_or_mutates_route_state() -> None:
    accounting = "Nobodyworld/app-accounting-modular"
    async with AsyncSessionLocal() as session:
        service = _service(session)
        await service.register_worker(
            _worker(
                "worker-unmapped-pin",
                python_version="3.12.4",
                capabilities={"git_available": True},
            )
        )
        await service.register_worker(
            _worker(
                "worker-mapped-alternative",
                repository_full_names=(accounting,),
                python_version="3.12.4",
                capabilities={"git_available": True},
            )
        )
        for worker_id, cost in (
            ("worker-unmapped-pin", 1),
            ("worker-mapped-alternative", 5),
        ):
            await service.create_routing_profile(_profile(worker_id, cost=cost))
            await _active_poll(service, worker_id)
        order_id = await _approved(
            service,
            _draft(
                routing_policy=RoutingPolicy.CHEAPEST_CAPABLE,
                repository_full_name=accounting,
                manifest_name="validate-accounting-modular",
                preferred_executor="worker-unmapped-pin",
                required_quota_units=2,
            ),
        )
        before_runs = int(
            await session.scalar(select(func.count(ExecutionRun.id))) or 0
        )
        before_leases = int(
            await session.scalar(select(func.count(ExecutionLease.id))) or 0
        )
        assessment = await service.assess_route(order_id)
        assert assessment.selected_worker_id is None
        assert assessment.eligible_candidate_count == 0
        assert assessment.explicit_pin_applied is True
        assert assessment.reason == "preferred_executor_unavailable"

        alternative = await service.checkout("worker-mapped-alternative")
        pinned = await service.checkout("worker-unmapped-pin")
        assert not alternative.assigned
        assert not pinned.assigned
        assert "worker_repository_unavailable" in pinned.mismatch_reasons
        order = await service.get_work_order(order_id, refresh=True)
        assert order.status.value == "queued"
        assert order.attempt_count == 0
        assert order.route_provenance is None
        assert (
            int(await session.scalar(select(func.count(ExecutionRun.id))) or 0)
            == before_runs
        )
        assert (
            int(await session.scalar(select(func.count(ExecutionLease.id))) or 0)
            == before_leases
        )
        for worker_id in ("worker-unmapped-pin", "worker-mapped-alternative"):
            worker = await service._repository.get_worker(worker_id)
            profile = await service.get_routing_profile(worker_id)
            assert worker is not None and worker.active_run_count == 0
            assert profile.quota_remaining_units == 100


@pytest.mark.asyncio
async def test_profile_crud_revision_conflict_and_monotonic_quota_reset() -> None:
    async with AsyncSessionLocal() as session:
        service = _service(session)
        await service.register_worker(_worker("worker-profile"))

        with pytest.raises(ExecutionNotFoundError, match="worker_not_found"):
            await service.create_routing_profile(_profile("missing", cost=1))

        created = await service.create_routing_profile(
            _profile("worker-profile", cost=7, capacity=50, remaining=40)
        )
        assert created.revision == 1
        assert [item.worker_id for item in await service.list_routing_profiles()] == [
            "worker-profile"
        ]

        replacement = RoutingProfileReplacement(
            expected_revision=1,
            enabled=False,
            estimated_cost_units_per_run=5,
            quota_capacity_units=60,
            quota_remaining_units=55,
            quota_reset_at=None,
            routing_priority=3,
        )
        replaced = await service.replace_routing_profile("worker-profile", replacement)
        assert replaced.revision == 2
        assert not replaced.enabled
        assert replaced.quota_remaining_units == 55

        with pytest.raises(
            LifecycleConflictError, match="routing_profile_revision_conflict"
        ):
            await service.replace_routing_profile("worker-profile", replacement)

        reset_at = dt.datetime(2026, 8, 1, 12, tzinfo=dt.UTC)
        reset = RoutingQuotaReset(
            expected_revision=2,
            quota_remaining_units=60,
            quota_reset_at=reset_at,
        )
        reset_profile = await service.reset_routing_quota("worker-profile", reset)
        assert reset_profile.revision == 3
        assert reset_profile.quota_remaining_units == 60
        idempotent = await service.reset_routing_quota("worker-profile", reset)
        assert idempotent.revision == 3

        with pytest.raises(
            LifecycleConflictError, match="routing_quota_reset_is_stale"
        ):
            await service.reset_routing_quota(
                "worker-profile",
                RoutingQuotaReset(
                    expected_revision=3,
                    quota_remaining_units=60,
                    quota_reset_at=reset_at - dt.timedelta(seconds=1),
                ),
            )

        replaced_after_reset = await service.replace_routing_profile(
            "worker-profile",
            RoutingProfileReplacement(
                expected_revision=3,
                enabled=False,
                estimated_cost_units_per_run=5,
                quota_capacity_units=60,
                quota_remaining_units=60,
                quota_reset_at=reset_at,
                routing_priority=3,
            ),
        )
        assert replaced_after_reset.revision == 4
        with pytest.raises(
            LifecycleConflictError, match="routing_profile_revision_conflict"
        ):
            await service.reset_routing_quota("worker-profile", reset)


def _candidate(
    worker_id: str,
    *,
    cost: int,
    remaining: int,
    active: int,
    maximum: int,
    priority: int,
) -> RoutingCandidate:
    worker = ExecutionWorker(
        worker_id=worker_id,
        active_run_count=active,
        max_concurrency=maximum,
    )
    profile = WorkerRoutingProfile(
        worker_id=worker_id,
        schema_version=1,
        enabled=True,
        estimated_cost_units_per_run=cost,
        quota_capacity_units=1_000,
        quota_remaining_units=remaining,
        routing_priority=priority,
        revision=1,
    )
    return RoutingCandidate(worker, profile)


def test_exact_deterministic_score_and_input_order_independence() -> None:
    candidates = [
        _candidate("worker-z", cost=2, remaining=900, active=0, maximum=4, priority=0),
        _candidate(
            "worker-cost", cost=1, remaining=10, active=3, maximum=4, priority=9
        ),
        _candidate(
            "worker-headroom", cost=1, remaining=30, active=3, maximum=4, priority=9
        ),
        _candidate(
            "worker-load", cost=1, remaining=30, active=1, maximum=3, priority=9
        ),
        _candidate(
            "worker-priority", cost=1, remaining=30, active=1, maximum=3, priority=2
        ),
        _candidate("worker-a", cost=1, remaining=30, active=1, maximum=3, priority=2),
    ]
    expected = [
        "worker-a",
        "worker-priority",
        "worker-load",
        "worker-headroom",
        "worker-cost",
        "worker-z",
    ]
    assert [
        item.worker.worker_id
        for item in rank_routing_candidates(candidates, required_quota_units=5)
    ] == expected
    assert [
        item.worker.worker_id
        for item in rank_routing_candidates(
            list(reversed(candidates)), required_quota_units=5
        )
    ] == expected


@pytest.mark.parametrize(
    ("failure", "expected_reason"),
    [
        ("missing_profile", "routing_profile_missing"),
        ("disabled", "routing_profile_disabled"),
        ("heartbeat", "worker_heartbeat_stale"),
        ("poll", "worker_checkout_poll_stale"),
        ("status", "worker_not_available"),
        ("capacity", "worker_concurrency_limit"),
        ("capability", "docker_not_available"),
        ("network", "network_policy_not_supported"),
        ("write", "repository_write_capability_must_be_false"),
        ("cost", "routing_cost_ceiling_exceeded"),
        ("quota", "routing_quota_insufficient"),
    ],
)
def test_routed_eligibility_fails_closed_at_every_pin_boundary(
    failure: str, expected_reason: str
) -> None:
    worker = ExecutionWorker(
        worker_id="worker-eligible",
        operating_system="linux",
        architecture="x86_64",
        python_version="3.11.9",
        node_version="20.0.0",
        docker_available=True,
        browsers=["chromium"],
        gpu_available=False,
        unity_available=False,
        desktop_available=False,
        capabilities={},
        max_concurrency=2,
        active_run_count=0,
        network_policy_capability=NetworkPolicy.WORKER_RESTRICTED,
        repository_write_capability=False,
        status=WorkerStatus.ONLINE,
        last_heartbeat_at=_NOW,
        last_checkout_poll_at=_NOW,
    )
    profile: WorkerRoutingProfile | None = WorkerRoutingProfile(
        worker_id=worker.worker_id,
        schema_version=1,
        enabled=True,
        estimated_cost_units_per_run=5,
        quota_capacity_units=20,
        quota_remaining_units=20,
        routing_priority=0,
        revision=1,
    )
    order = ExecutionWorkOrder(
        preferred_executor=worker.worker_id,
        maximum_cost_units=10,
        required_quota_units=3,
        required_capabilities={},
        network_policy=NetworkPolicy.WORKER_RESTRICTED,
    )
    manifest = CommandManifest(required_capabilities={})

    if failure == "missing_profile":
        profile = None
    elif failure == "disabled":
        assert profile is not None
        profile.enabled = False
    elif failure == "heartbeat":
        worker.last_heartbeat_at = _NOW - dt.timedelta(seconds=301)
    elif failure == "poll":
        worker.last_checkout_poll_at = _NOW - dt.timedelta(seconds=61)
    elif failure == "status":
        worker.status = WorkerStatus.DRAINING
    elif failure == "capacity":
        worker.active_run_count = worker.max_concurrency
    elif failure == "capability":
        worker.docker_available = False
        order.required_capabilities = {"docker": True}
    elif failure == "network":
        worker.network_policy_capability = NetworkPolicy.DISABLED
    elif failure == "write":
        worker.repository_write_capability = True
    elif failure == "cost":
        assert profile is not None
        profile.estimated_cost_units_per_run = 11
    elif failure == "quota":
        assert profile is not None
        profile.quota_remaining_units = 2

    eligibility = evaluate_routing_candidate(
        worker,
        profile,
        work_order=order,
        manifest=manifest,
        now=_NOW,
        heartbeat_freshness_seconds=300,
        active_poll_freshness_seconds=60,
    )
    assert eligibility.candidate is None
    assert expected_reason in eligibility.reasons


@pytest.mark.asyncio
async def test_cheapest_active_worker_wins_and_provenance_is_bounded() -> None:
    async with AsyncSessionLocal() as session:
        service = _service(session)
        await service.register_worker(_worker("worker-cheap"))
        await service.register_worker(_worker("worker-expensive"))
        await service.create_routing_profile(
            _profile("worker-cheap", cost=2, remaining=20)
        )
        await service.create_routing_profile(
            _profile("worker-expensive", cost=9, remaining=100)
        )
        await _active_poll(service, "worker-cheap")
        order_id = await _approved(
            service,
            _draft(
                routing_policy=RoutingPolicy.CHEAPEST_CAPABLE,
                maximum_cost_units=10,
                required_quota_units=4,
            ),
        )

        expensive = await service.checkout("worker-expensive")
        assert not expensive.assigned
        assert expensive.reason == "better_candidate_active"

        cheap = await service.checkout("worker-cheap")
        assert cheap.assigned
        run = await service.get_run(cheap.run_id or 0)
        order = await service.get_work_order(order_id, refresh=True)
        profile = await service.get_routing_profile("worker-cheap")
        assert profile.quota_remaining_units == 16
        assert profile.revision == 2
        assert run.route_profile_revision == 2
        assert run.route_estimated_cost_units == 2
        assert run.route_required_quota_units == 4
        assert run.route_reserved_quota_units == 4
        assert run.route_quota_state == QuotaReservationState.RESERVED
        assert run.route_eligible_candidate_count == 2
        assert order.route_provenance == run.route_provenance
        assert set(run.route_provenance) == {
            "schema_version",
            "routing_policy",
            "selected_worker_id",
            "selected_routing_profile_revision",
            "estimated_cost_units",
            "required_quota_units",
            "reserved_quota_units",
            "quota_reservation_state",
            "eligible_candidate_count",
            "explicit_pin_applied",
            "reason",
            "decision_timestamp",
        }


@pytest.mark.asyncio
async def test_zero_quota_route_still_conditionally_advances_profile_revision() -> None:
    async with AsyncSessionLocal() as session:
        service = _service(session)
        await service.register_worker(_worker("worker-zero-quota"))
        await service.create_routing_profile(
            _profile("worker-zero-quota", cost=1, capacity=0, remaining=0)
        )
        await _approved(
            service,
            _draft(
                routing_policy=RoutingPolicy.CHEAPEST_CAPABLE,
                required_quota_units=0,
            ),
        )
        assignment = await service.checkout("worker-zero-quota")
        assert assignment.assigned
        profile = await service.get_routing_profile("worker-zero-quota")
        run = await service.get_run(assignment.run_id or 0)
        assert profile.revision == 2
        assert profile.quota_remaining_units == 0
        assert run.route_profile_revision == 2
        assert run.route_quota_state == QuotaReservationState.NOT_REQUIRED


@pytest.mark.asyncio
async def test_profile_revision_overflow_fails_closed_without_claim() -> None:
    async with AsyncSessionLocal() as session:
        service = _service(session)
        await service.register_worker(_worker("worker-revision-max"))
        profile = await service.create_routing_profile(
            _profile("worker-revision-max", cost=1)
        )
        profile.revision = 2_147_483_647
        await session.flush()
        order_id = await _approved(
            service,
            _draft(routing_policy=RoutingPolicy.CHEAPEST_CAPABLE),
        )
        result = await service.checkout("worker-revision-max")
        assert not result.assigned
        assert result.reason == "routing_reservation_conflict"
        persisted = await service.get_work_order(order_id, refresh=True)
        worker = await ExecutionRepository(session).get_worker("worker-revision-max")
        assert persisted.status.value == "queued"
        assert persisted.attempt_count == 0
        assert persisted.route_provenance is None
        assert worker is not None
        assert worker.active_run_count == 0


@pytest.mark.asyncio
async def test_stale_poll_ages_out_even_with_fresh_heartbeat() -> None:
    async with AsyncSessionLocal() as session:
        repository = ExecutionRepository(session)
        service = _service(session)
        await service.register_worker(_worker("worker-cheap-stale"))
        await service.register_worker(_worker("worker-active"))
        await service.create_routing_profile(_profile("worker-cheap-stale", cost=1))
        await service.create_routing_profile(_profile("worker-active", cost=8))
        assert await repository.record_checkout_poll(
            "worker-cheap-stale", now=_NOW - dt.timedelta(seconds=61)
        )
        await _approved(
            service,
            _draft(
                routing_policy=RoutingPolicy.CHEAPEST_CAPABLE,
                required_quota_units=1,
            ),
        )

        result = await service.checkout("worker-active")
        assert result.assigned
        run = await service.get_run(result.run_id or 0)
        assert run.worker_id == "worker-active"
        stale_worker = await repository.get_worker("worker-cheap-stale")
        assert stale_worker is not None
        assert stale_worker.last_heartbeat_at == _NOW
        assert stale_worker.last_checkout_poll_at == _NOW - dt.timedelta(seconds=61)


@pytest.mark.asyncio
async def test_checkout_poll_updates_only_the_authenticated_requester() -> None:
    async with AsyncSessionLocal() as session:
        repository = ExecutionRepository(session)
        service = _service(session)
        await service.register_worker(_worker("worker-poll-a"))
        await service.register_worker(_worker("worker-poll-b"))
        result = await service.checkout("worker-poll-a")
        assert result.reason == "no_queued_work_orders"
        first = await repository.get_worker("worker-poll-a")
        second = await repository.get_worker("worker-poll-b")
        assert first is not None
        assert second is not None
        assert first.last_checkout_poll_at == _NOW
        assert second.last_checkout_poll_at is None


@pytest.mark.asyncio
async def test_hard_pin_overrides_cost_but_not_eligibility_and_has_no_fallback() -> (
    None
):
    async with AsyncSessionLocal() as session:
        service = _service(session)
        await service.register_worker(_worker("worker-pinned"))
        await service.register_worker(_worker("worker-cheaper"))
        await service.create_routing_profile(_profile("worker-pinned", cost=9))
        await service.create_routing_profile(_profile("worker-cheaper", cost=1))
        await _active_poll(service, "worker-pinned")
        await _active_poll(service, "worker-cheaper")

        order_id = await _approved(
            service,
            _draft(
                routing_policy=RoutingPolicy.CHEAPEST_CAPABLE,
                preferred_executor="worker-pinned",
                maximum_cost_units=10,
                required_quota_units=1,
            ),
        )
        loser = await service.checkout("worker-cheaper")
        assert loser.reason == "better_candidate_active"
        winner = await service.checkout("worker-pinned")
        assert winner.assigned
        run = await service.get_run(winner.run_id or 0)
        assert run.worker_id == "worker-pinned"
        assert run.route_explicit_pin_applied

        await service.cancel_work_order(order_id, reason="pin test complete")
        disabled = await service.replace_routing_profile(
            "worker-pinned",
            RoutingProfileReplacement(
                expected_revision=(
                    await service.get_routing_profile("worker-pinned")
                ).revision,
                enabled=False,
                estimated_cost_units_per_run=9,
                quota_capacity_units=100,
                quota_remaining_units=100,
                quota_reset_at=None,
                routing_priority=0,
            ),
        )
        assert not disabled.enabled
        await _approved(
            service,
            _draft(
                routing_policy=RoutingPolicy.CHEAPEST_CAPABLE,
                preferred_executor="worker-pinned",
                required_quota_units=1,
            ),
        )
        unavailable = await service.checkout("worker-cheaper")
        assert not unavailable.assigned
        assert unavailable.reason == "preferred_executor_unavailable"

        with pytest.raises(
            ExecutionNotFoundError, match="preferred_executor_not_found"
        ):
            await service.create_work_order(
                _draft(preferred_executor="worker-does-not-exist")
            )


@pytest.mark.asyncio
async def test_quota_reserve_consume_and_prestart_release_are_exactly_once() -> None:
    async with AsyncSessionLocal() as session:
        service = _service(session)
        await service.register_worker(_worker("worker-quota"))
        await service.create_routing_profile(
            _profile("worker-quota", cost=1, capacity=10, remaining=10)
        )

        first_order = await _approved(
            service,
            _draft(
                routing_policy=RoutingPolicy.CHEAPEST_CAPABLE,
                required_quota_units=3,
            ),
        )
        first = await service.checkout("worker-quota")
        assert first.assigned
        assert (
            await service.get_routing_profile("worker-quota")
        ).quota_remaining_units == 7
        await service.cancel_work_order(first_order, reason="before start")
        released = await service.get_run(first.run_id or 0)
        assert released.route_quota_state == QuotaReservationState.RELEASED
        assert (
            await service.get_routing_profile("worker-quota")
        ).quota_remaining_units == 10

        second_order = await _approved(
            service,
            _draft(
                routing_policy=RoutingPolicy.CHEAPEST_CAPABLE,
                required_quota_units=3,
            ),
        )
        second = await service.checkout("worker-quota")
        assert second.assigned
        running = await service.heartbeat_run(
            second.run_id or 0, worker_id="worker-quota"
        )
        assert running.route_quota_state == QuotaReservationState.CONSUMED
        repeated = await service.heartbeat_run(
            second.run_id or 0, worker_id="worker-quota"
        )
        assert repeated.route_quota_state == QuotaReservationState.CONSUMED
        assert (
            await service.get_routing_profile("worker-quota")
        ).quota_remaining_units == 7
        await service.complete_run(
            second.run_id or 0,
            worker_id="worker-quota",
            completion=ExecutionCompletion(status=ExecutionRunStatus.FAILED),
        )
        assert (
            await service.get_routing_profile("worker-quota")
        ).quota_remaining_units == 7
        order = await service.get_work_order(second_order, refresh=True)
        assert order.route_quota_state == QuotaReservationState.CONSUMED


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "terminal_status",
    [
        ExecutionRunStatus.SUCCEEDED,
        ExecutionRunStatus.FAILED,
        ExecutionRunStatus.TIMED_OUT,
        ExecutionRunStatus.CANCELLED,
    ],
)
async def test_started_terminal_runs_never_refund_consumed_quota(
    terminal_status: ExecutionRunStatus,
) -> None:
    async with AsyncSessionLocal() as session:
        service = _service(session)
        await service.register_worker(_worker(f"worker-{terminal_status.value}"))
        worker_id = f"worker-{terminal_status.value}"
        await service.create_routing_profile(
            _profile(worker_id, cost=1, capacity=10, remaining=10)
        )
        await _approved(
            service,
            _draft(
                routing_policy=RoutingPolicy.CHEAPEST_CAPABLE,
                required_quota_units=2,
            ),
        )
        assignment = await service.checkout(worker_id)
        assert assignment.assigned
        await service.heartbeat_run(assignment.run_id or 0, worker_id=worker_id)
        await service.complete_run(
            assignment.run_id or 0,
            worker_id=worker_id,
            completion=ExecutionCompletion(status=terminal_status),
        )
        profile = await service.get_routing_profile(worker_id)
        run = await service.get_run(assignment.run_id or 0)
        assert profile.quota_remaining_units == 8
        assert run.route_quota_state == QuotaReservationState.CONSUMED


@pytest.mark.asyncio
async def test_ownership_loss_cannot_consume_reserved_quota() -> None:
    async with AsyncSessionLocal() as session:
        service = _service(session)
        await service.register_worker(_worker("worker-owner"))
        await service.register_worker(_worker("worker-intruder"))
        await service.create_routing_profile(_profile("worker-owner", cost=1))
        await _approved(
            service,
            _draft(
                routing_policy=RoutingPolicy.CHEAPEST_CAPABLE,
                required_quota_units=4,
            ),
        )
        assignment = await service.checkout("worker-owner")
        assert assignment.assigned
        with pytest.raises(OwnershipConflictError, match="execution_lease_not_owned"):
            await service.heartbeat_run(
                assignment.run_id or 0, worker_id="worker-intruder"
            )
        profile = await service.get_routing_profile("worker-owner")
        run = await service.get_run(assignment.run_id or 0)
        assert profile.quota_remaining_units == 96
        assert run.route_quota_state == QuotaReservationState.RESERVED


@pytest.mark.asyncio
async def test_active_reservation_blocks_profile_replace_and_quota_reset() -> None:
    async with AsyncSessionLocal() as session:
        service = _service(session)
        await service.register_worker(_worker("worker-reset-guard"))
        await service.create_routing_profile(
            _profile("worker-reset-guard", cost=1, capacity=10, remaining=10)
        )
        order_id = await _approved(
            service,
            _draft(
                routing_policy=RoutingPolicy.CHEAPEST_CAPABLE,
                required_quota_units=2,
            ),
        )
        assignment = await service.checkout("worker-reset-guard")
        assert assignment.assigned
        profile = await service.get_routing_profile("worker-reset-guard")
        replacement = RoutingProfileReplacement(
            expected_revision=profile.revision,
            enabled=True,
            estimated_cost_units_per_run=2,
            quota_capacity_units=10,
            quota_remaining_units=8,
            quota_reset_at=None,
            routing_priority=0,
        )
        with pytest.raises(
            LifecycleConflictError, match="routing_profile_has_active_reservations"
        ):
            await service.replace_routing_profile("worker-reset-guard", replacement)
        with pytest.raises(
            LifecycleConflictError, match="routing_profile_has_active_reservations"
        ):
            await service.reset_routing_quota(
                "worker-reset-guard",
                RoutingQuotaReset(
                    expected_revision=profile.revision,
                    quota_remaining_units=10,
                    quota_reset_at=dt.datetime(2026, 8, 1, tzinfo=dt.UTC),
                ),
            )
        await service.cancel_work_order(order_id, reason="release reset guard")
        released = await service.get_routing_profile("worker-reset-guard")
        assert released.quota_remaining_units == 10
        replaced = await service.replace_routing_profile(
            "worker-reset-guard",
            replace(replacement, expected_revision=released.revision),
        )
        assert replaced.estimated_cost_units_per_run == 2


@pytest.mark.asyncio
async def test_assessment_is_read_only_and_api_provenance_is_redacted() -> None:
    async with AsyncSessionLocal() as session:
        service = _service(session)
        await service.register_worker(_worker("worker-assess"))
        await service.create_routing_profile(_profile("worker-assess", cost=3))
        await _active_poll(service, "worker-assess")
        order_id = await _approved(
            service,
            _draft(
                routing_policy=RoutingPolicy.CHEAPEST_CAPABLE,
                required_quota_units=2,
            ),
        )
        worker_before = await ExecutionRepository(session).get_worker("worker-assess")
        assert worker_before is not None
        poll_before = worker_before.last_checkout_poll_at
        profile_before = await service.get_routing_profile("worker-assess")
        assessment = await service.assess_route(order_id)
        profile_after = await service.get_routing_profile("worker-assess")
        worker_after = await ExecutionRepository(session).get_worker("worker-assess")
        assert assessment.selected_worker_id == "worker-assess"
        assert assessment.reserved_quota_units == 0
        assert assessment.quota_reservation_state == QuotaReservationState.NOT_REQUIRED
        assert profile_after.revision == profile_before.revision
        assert (
            profile_after.quota_remaining_units == profile_before.quota_remaining_units
        )
        assert worker_after is not None
        assert worker_after.last_checkout_poll_at == poll_before

        assignment = await service.checkout("worker-assess")
        assert assignment.assigned
        await session.commit()

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        work_route = await client.get(f"/api/execution/work-orders/{order_id}/route")
        run_route = await client.get(f"/api/execution/runs/{assignment.run_id}/route")
        assert work_route.status_code == HTTPStatus.OK
        assert run_route.status_code == HTTPStatus.OK
        for payload in (work_route.json(), run_route.json()):
            encoded = str(payload).lower()
            assert "command" not in encoded
            assert "argv" not in encoded
            assert "capabilities" not in encoded
            assert "local_root" not in encoded
            assert "secret" not in encoded
            assert "credential" not in encoded


@pytest.mark.asyncio
async def test_profile_api_crud_and_worker_extra_fields_are_typed() -> None:
    transport = ASGITransport(app=app)
    worker = {
        "worker_id": "worker-api-profile",
        "display_name": "worker-api-profile",
        "operating_system": "linux",
        "architecture": "x86_64",
    }
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        registered = await client.post("/api/execution/workers", json=worker)
        assert registered.status_code == HTTPStatus.OK
        rejected_worker_state = await client.post(
            "/api/execution/workers",
            json={**worker, "estimated_cost_units_per_run": 1},
        )
        assert rejected_worker_state.status_code == HTTPStatus.UNPROCESSABLE_ENTITY
        created = await client.post(
            "/api/execution/routing-profiles",
            json={
                "worker_id": worker["worker_id"],
                "estimated_cost_units_per_run": 4,
                "quota_capacity_units": 20,
                "quota_remaining_units": 20,
                "routing_priority": 2,
            },
        )
        assert created.status_code == HTTPStatus.OK
        assert created.json()["revision"] == 1
        listed = await client.get("/api/execution/routing-profiles")
        assert listed.status_code == HTTPStatus.OK
        assert [item["worker_id"] for item in listed.json()] == [worker["worker_id"]]
        replaced = await client.put(
            f"/api/execution/routing-profiles/{worker['worker_id']}",
            json={
                "expected_revision": 1,
                "enabled": True,
                "estimated_cost_units_per_run": 3,
                "quota_capacity_units": 20,
                "quota_remaining_units": 18,
                "routing_priority": 1,
            },
        )
        assert replaced.status_code == HTTPStatus.OK
        stale = await client.put(
            f"/api/execution/routing-profiles/{worker['worker_id']}",
            json={
                "expected_revision": 1,
                "enabled": True,
                "estimated_cost_units_per_run": 2,
                "quota_capacity_units": 20,
                "quota_remaining_units": 20,
                "routing_priority": 0,
            },
        )
        assert stale.status_code == HTTPStatus.CONFLICT
        assert stale.json()["detail"] == "routing_profile_revision_conflict"


@pytest.mark.asyncio
async def test_profile_and_assessment_apis_use_privileged_admin_boundary(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("SWITCHBOARD_ADMIN_TOKEN", "routing-profile-test-token")
    reload_admin_token()
    transport = ASGITransport(app=app)
    try:
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            unauthenticated = await client.get("/api/execution/routing-profiles")
            authenticated = await client.get(
                "/api/execution/routing-profiles",
                headers={"X-Switchboard-Admin-Token": "routing-profile-test-token"},
            )
            unauthenticated_assessment = await client.get(
                "/api/execution/work-orders/1/route-assessment"
            )
        assert unauthenticated.status_code == HTTPStatus.UNAUTHORIZED
        assert authenticated.status_code == HTTPStatus.OK
        assert unauthenticated_assessment.status_code == HTTPStatus.UNAUTHORIZED
    finally:
        monkeypatch.delenv("SWITCHBOARD_ADMIN_TOKEN", raising=False)
        reload_admin_token()


@pytest.mark.asyncio
async def test_routing_inputs_change_execution_policy_identity() -> None:
    async with AsyncSessionLocal() as session:
        service = _service(session)
        await service.register_worker(_worker("worker-identity"))
        base = await service.create_work_order(_draft())
        variants = [
            replace(_draft(), routing_policy=RoutingPolicy.CHEAPEST_CAPABLE),
            replace(_draft(), maximum_cost_units=7),
            replace(_draft(), required_quota_units=3),
            replace(_draft(), preferred_executor="worker-identity"),
        ]
        hashes = {
            (await service.create_work_order(variant)).execution_policy_hash
            for variant in variants
        }
        assert base.execution_policy_hash not in hashes
        assert len(hashes) == len(variants)


@pytest.mark.asyncio
async def test_route_provenance_persists_across_sessions() -> None:
    async with AsyncSessionLocal() as session:
        service = _service(session)
        await service.register_worker(_worker("worker-persist"))
        await service.create_routing_profile(_profile("worker-persist", cost=5))
        order_id = await _approved(
            service,
            _draft(routing_policy=RoutingPolicy.CHEAPEST_CAPABLE),
        )
        assignment = await service.checkout("worker-persist")
        assert assignment.assigned
        expected = (await service.get_run(assignment.run_id or 0)).route_provenance
        await session.commit()

    async with AsyncSessionLocal() as session:
        run = await session.scalar(
            select(ExecutionRun).where(ExecutionRun.id == assignment.run_id)
        )
        assert run is not None
        assert run.route_provenance == expected
        restarted_service = _service(session)
        order = await restarted_service.get_work_order(order_id)
        assert order.route_provenance == expected
        profile = await restarted_service.get_routing_profile("worker-persist")
        assert profile.estimated_cost_units_per_run == 5
        assert profile.revision == 2
