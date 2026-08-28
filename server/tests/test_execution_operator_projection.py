# ruff: noqa: PLR0913, PLR0915
"""Focused activity and redaction coverage for operator worker projections."""

from __future__ import annotations

import datetime as dt
from http import HTTPStatus

import pytest
from httpx import ASGITransport, AsyncClient
from pydantic import ValidationError
from sqlalchemy import select

from server.app import app
from server.db import AsyncSessionLocal
from server.execution.entities import WorkerRegistration, WorkOrderDraft
from server.execution.enums import (
    ApprovalPolicy,
    NetworkPolicy,
    WorkerStatus,
)
from server.execution.operator_projection import (
    MAX_OPERATOR_BROWSER_COUNT,
    ExecutionOperatorProjection,
    ExecutionWorkerSummaryOut,
    _worker_activity_state,
)
from server.execution.repository import ExecutionRepository
from server.execution.service import ExecutionService
from server.models import ExecutionWorker
from server.time_utils import utcnow_naive


def _worker(
    worker_id: str,
    *,
    status: WorkerStatus = WorkerStatus.ONLINE,
    browsers: tuple[str, ...] = (),
    capabilities: dict[str, object] | None = None,
) -> WorkerRegistration:
    return WorkerRegistration(
        worker_id=worker_id,
        display_name=f"Synthetic {worker_id}",
        operating_system="linux",
        architecture="x86_64",
        python_version="3.11.14",
        node_version=None,
        docker_available=False,
        browsers=browsers,
        gpu_available=False,
        unity_available=False,
        desktop_available=False,
        capabilities=capabilities or {},
        max_concurrency=1,
        network_policy_capability=NetworkPolicy.WORKER_RESTRICTED,
        repository_write_capability=False,
        status=status,
    )


def _draft() -> WorkOrderDraft:
    return WorkOrderDraft(
        schema_version=1,
        repository_full_name="Nobodyworld/dev-agent-switchboard",
        commit_sha="d" * 40,
        manifest_name="validate-switchboard",
        manifest_version="1",
        manifest_parameters={},
        required_capabilities={},
        permitted_paths=("server",),
        forbidden_scope_notes="read-only operator projection proof",
        expected_artifact_kinds=("command-log",),
        approval_policy=ApprovalPolicy.EXPLICIT,
        timeout_seconds=3600,
        resource_metadata={},
        network_policy=NetworkPolicy.WORKER_RESTRICTED,
        repository_write_allowed=False,
        preferred_executor=None,
        cost_ceiling=None,
    )


@pytest.mark.parametrize(
    (
        "status",
        "active_run_count",
        "max_concurrency",
        "heartbeat_age",
        "poll_age",
        "expected",
    ),
    [
        (WorkerStatus.ONLINE, 0, 1, 0, 0, "active"),
        (WorkerStatus.BUSY, 1, 1, 0, 0, "capacity_constrained"),
        (WorkerStatus.ONLINE, 1, 1, 0, 0, "capacity_constrained"),
        (WorkerStatus.BUSY, 1, 1, 301, 61, "stale"),
        (WorkerStatus.DRAINING, 0, 1, 0, 0, "unavailable"),
        (WorkerStatus.OFFLINE, 0, 1, 0, 0, "unavailable"),
        (WorkerStatus.ONLINE, 2, 1, 0, 0, "unavailable"),
    ],
)
def test_worker_activity_state_precedence_is_deterministic(
    *,
    status: WorkerStatus,
    active_run_count: int,
    max_concurrency: int,
    heartbeat_age: int,
    poll_age: int,
    expected: str,
) -> None:
    now = dt.datetime(2026, 8, 9, 12, 0, 0, tzinfo=dt.UTC).replace(tzinfo=None)

    result = _worker_activity_state(
        status=status,
        active_run_count=active_run_count,
        max_concurrency=max_concurrency,
        last_heartbeat_at=now - dt.timedelta(seconds=heartbeat_age),
        last_checkout_poll_at=now - dt.timedelta(seconds=poll_age),
        now=now,
        heartbeat_freshness_seconds=300,
        active_poll_freshness_seconds=60,
    )

    assert result == expected


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "insertion_order",
    [
        (
            "worker-stale",
            "worker-offline",
            "worker-active",
            "worker-busy",
            "worker-draining",
            "worker-inconsistent-full",
        ),
        (
            "worker-inconsistent-full",
            "worker-draining",
            "worker-busy",
            "worker-active",
            "worker-offline",
            "worker-stale",
        ),
    ],
)
async def test_busy_capacity_lifecycle_projects_bounded_stable_worker_state(
    insertion_order: tuple[str, ...],
) -> None:
    now = utcnow_naive()
    browser_names = tuple(f"browser-{index:02d}" for index in range(10))
    registrations = {
        "worker-active": _worker("worker-active"),
        "worker-busy": _worker(
            "worker-busy",
            browsers=browser_names,
            capabilities={
                "unlisted_flag": True,
                "nested_metadata": {"count": 7},
            },
        ),
        "worker-draining": _worker("worker-draining", status=WorkerStatus.DRAINING),
        "worker-inconsistent-full": _worker("worker-inconsistent-full"),
        "worker-offline": _worker("worker-offline", status=WorkerStatus.OFFLINE),
        "worker-stale": _worker("worker-stale"),
    }
    expected_states = {
        "worker-active": "active",
        "worker-busy": "capacity_constrained",
        "worker-draining": "unavailable",
        "worker-inconsistent-full": "capacity_constrained",
        "worker-offline": "unavailable",
        "worker-stale": "stale",
    }

    async with AsyncSessionLocal() as session:
        repository = ExecutionRepository(session)
        service = ExecutionService(
            repository=repository,
            clock=lambda: now,
            lease_seconds=lambda: 60,
            routing_freshness_seconds=lambda: (300, 60),
        )
        for worker_id in insertion_order:
            await service.register_worker(registrations[worker_id])

        for worker_id in (
            "worker-active",
            "worker-busy",
            "worker-inconsistent-full",
            "worker-stale",
        ):
            checkout = await service.checkout(worker_id)
            assert not checkout.assigned

        stale_worker = await repository.get_worker("worker-stale")
        inconsistent_worker = await repository.get_worker("worker-inconsistent-full")
        assert stale_worker is not None
        assert inconsistent_worker is not None
        stale_worker.last_heartbeat_at = now - dt.timedelta(seconds=301)
        stale_worker.last_checkout_poll_at = now - dt.timedelta(seconds=61)
        inconsistent_worker.active_run_count = inconsistent_worker.max_concurrency
        inconsistent_worker.status = WorkerStatus.ONLINE
        await session.flush()

        order = await service.create_work_order(_draft())
        await service.approve_work_order(order.id)
        assignment = await service.checkout("worker-busy")
        assert assignment.assigned
        session.expire_all()

        persisted_busy = (
            await session.execute(
                select(ExecutionWorker)
                .where(ExecutionWorker.worker_id == "worker-busy")
                .execution_options(populate_existing=True)
            )
        ).scalar_one()
        assert persisted_busy.status == WorkerStatus.BUSY
        assert persisted_busy.active_run_count == persisted_busy.max_concurrency == 1

        projection = ExecutionOperatorProjection(session)
        workers = await projection.list_workers(
            limit=100,
            offset=0,
            heartbeat_freshness_seconds=300,
            active_poll_freshness_seconds=60,
        )
        overview = await projection.overview(
            window_days=1,
            heartbeat_freshness_seconds=300,
            active_poll_freshness_seconds=60,
            now=now,
        )
        await session.commit()

    projected_states = {item.worker_id: item.activity_state for item in workers.items}
    assert projected_states == expected_states
    assert [item.worker_id for item in workers.items] == sorted(expected_states)
    assert overview.workers.model_dump() == {
        "total": 6,
        "active": 1,
        "stale": 1,
        "capacity_constrained": 2,
        "unavailable": 2,
    }
    assert (
        sum(
            (
                overview.workers.active,
                overview.workers.stale,
                overview.workers.capacity_constrained,
                overview.workers.unavailable,
            )
        )
        == overview.workers.total
    )

    transport = ASGITransport(app=app, client=("operator-worker-summary", 12_346))
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/execution/workers?limit=100&offset=0")
        overview_response = await client.get(
            "/api/execution/operator/overview?window_days=1"
        )
    assert response.status_code == HTTPStatus.OK
    assert overview_response.status_code == HTTPStatus.OK
    assert overview_response.json()["workers"] == {
        "total": 6,
        "active": 1,
        "stale": 1,
        "capacity_constrained": 2,
        "unavailable": 2,
    }
    payload = response.json()
    assert [item["worker_id"] for item in payload["items"]] == sorted(expected_states)
    payload_by_id = {item["worker_id"]: item for item in payload["items"]}
    busy_payload = payload_by_id["worker-busy"]
    assert busy_payload["activity_state"] == "capacity_constrained"
    assert busy_payload["python_version"] == "3.11.14"
    assert busy_payload["node_version"] is None
    assert busy_payload["docker_available"] is False
    assert busy_payload["browsers"] == list(browser_names[:MAX_OPERATOR_BROWSER_COUNT])
    assert busy_payload["gpu_available"] is False
    assert busy_payload["unity_available"] is False
    assert busy_payload["desktop_available"] is False
    assert busy_payload["network_policy_capability"] == "worker_restricted"
    assert busy_payload["repository_write_capability"] is False
    assert "capabilities" not in busy_payload
    assert {
        "local_root",
        "environment",
        "command",
        "argv",
        "hostname",
        "username",
        "credential",
    }.isdisjoint(busy_payload)

    with pytest.raises(ValidationError):
        ExecutionWorkerSummaryOut.model_validate(
            {
                **busy_payload,
                "browsers": [
                    *busy_payload["browsers"],
                    "one-browser-too-many",
                ],
            }
        )
