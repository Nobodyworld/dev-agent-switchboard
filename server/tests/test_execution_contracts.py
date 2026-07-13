"""Focused regression coverage for the persisted execution control plane."""

from __future__ import annotations

import datetime as dt
from http import HTTPStatus

import pytest
from httpx import ASGITransport, AsyncClient
from pydantic import ValidationError
from sqlalchemy import select

from server.app import app
from server.application import build_execution_service
from server.db import AsyncSessionLocal
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
from server.execution.exceptions import (
    ApprovalDeniedError,
    LifecycleConflictError,
    ManifestIntegrityError,
    OwnershipConflictError,
)
from server.execution.repository import ExecutionRepository
from server.execution.schemas import WorkOrderCreateIn
from server.execution.service import ExecutionService
from server.models import ExecutionLease, Lease, Task
from server.settings import reload_admin_token
from server.task_status import TaskStatus
from server.time_utils import utcnow_naive

VALID_SHA = "a" * 40


def _work_order_draft(
    *,
    repository_full_name: str = "Nobodyworld/dev-agent-switchboard",
    required_capabilities: dict[str, object] | None = None,
) -> WorkOrderDraft:
    return WorkOrderDraft(
        schema_version=1,
        repository_full_name=repository_full_name,
        commit_sha=VALID_SHA,
        manifest_name="validate-switchboard",
        manifest_version="1",
        manifest_parameters={},
        required_capabilities=required_capabilities or {},
        permitted_paths=("server", "tests"),
        forbidden_scope_notes="target repository remains read-only",
        expected_artifact_kinds=("command-log",),
        approval_policy=ApprovalPolicy.EXPLICIT,
        timeout_seconds=3600,
        resource_metadata={"memory_mb": 1024},
        network_policy=NetworkPolicy.WORKER_RESTRICTED,
        repository_write_allowed=False,
        preferred_executor="local",
        cost_ceiling=0.0,
    )


def _worker(
    worker_id: str,
    *,
    docker_available: bool = False,
    max_concurrency: int = 1,
    status: WorkerStatus = WorkerStatus.ONLINE,
) -> WorkerRegistration:
    return WorkerRegistration(
        worker_id=worker_id,
        display_name=worker_id,
        operating_system="linux",
        architecture="x86_64",
        python_version="3.11.9",
        node_version="20.0.0",
        docker_available=docker_available,
        browsers=("chromium",),
        gpu_available=False,
        unity_available=False,
        desktop_available=False,
        capabilities={},
        max_concurrency=max_concurrency,
        network_policy_capability=NetworkPolicy.WORKER_RESTRICTED,
        repository_write_capability=False,
        status=status,
    )


async def _create_approved(
    service: ExecutionService,
    *,
    draft: WorkOrderDraft | None = None,
) -> int:
    work_order = await service.create_work_order(draft or _work_order_draft())
    await service.approve_work_order(work_order.id)
    return work_order.id


def test_work_order_schema_requires_exact_sha_and_forbids_executable_fields() -> None:
    payload = {
        "repository_full_name": "Nobodyworld/dev-agent-switchboard",
        "commit_sha": VALID_SHA,
        "manifest": {"name": "validate-switchboard", "version": "1"},
    }
    accepted = WorkOrderCreateIn.model_validate(payload)
    assert accepted.commit_sha == VALID_SHA

    for invalid_sha in ("a" * 39, "z" * 40):
        invalid = dict(payload, commit_sha=invalid_sha)
        with pytest.raises(ValidationError):
            WorkOrderCreateIn.model_validate(invalid)

    with pytest.raises(ValidationError):
        WorkOrderCreateIn.model_validate({**payload, "command": "not allowed"})
    with pytest.raises(ValidationError):
        WorkOrderCreateIn.model_validate({**payload, "argv": ["not", "allowed"]})
    with pytest.raises(ValidationError):
        WorkOrderCreateIn.model_validate(
            {
                **payload,
                "manifest": {
                    "name": "validate-switchboard",
                    "version": "1",
                    "argv": ["not", "allowed"],
                },
            }
        )
    with pytest.raises(ValidationError):
        WorkOrderCreateIn.model_validate({**payload, "repository_write": True})
    for field, nested_payload in (
        ("manifest", {"parameters": {"nested": {"argv": ["not", "allowed"]}}}),
        ("required_capabilities", {"nested": {"command": "not allowed"}}),
        ("resource_metadata", {"nested": {"executable_path": "not-allowed"}}),
    ):
        candidate = dict(payload)
        if field == "manifest":
            candidate["manifest"] = {
                "name": "validate-switchboard",
                "version": "1",
                **nested_payload,
            }
        else:
            candidate[field] = nested_payload
        with pytest.raises(ValidationError):
            WorkOrderCreateIn.model_validate(candidate)


@pytest.mark.asyncio
async def test_trusted_manifest_resolution_and_digest_immutability() -> None:
    async with AsyncSessionLocal() as session:
        service = build_execution_service(session)
        work_order = await service.create_work_order(_work_order_draft())
        manifest = await service.get_manifest("validate-switchboard", "1")
        assert work_order.manifest_digest == manifest.digest
        assert manifest.digest
        manifest.digest = "0" * len(manifest.digest)
        await session.commit()

    async with AsyncSessionLocal() as session:
        service = build_execution_service(session)
        with pytest.raises(ManifestIntegrityError):
            await service.sync_trusted_manifests()


@pytest.mark.asyncio
async def test_trusted_manifest_metadata_snapshot_is_immutable() -> None:
    async with AsyncSessionLocal() as session:
        service = build_execution_service(session)
        manifest = await service.get_manifest("validate-switchboard", "1")
        manifest.required_capabilities = {"architecture": ["untrusted"]}
        await session.commit()

    async with AsyncSessionLocal() as session:
        service = build_execution_service(session)
        with pytest.raises(ManifestIntegrityError):
            await service.sync_trusted_manifests()


@pytest.mark.asyncio
async def test_approval_is_deny_by_default_for_non_allowlisted_repository() -> None:
    async with AsyncSessionLocal() as session:
        service = build_execution_service(session)
        work_order = await service.create_work_order(
            _work_order_draft(repository_full_name="untrusted/example")
        )
        with pytest.raises(ApprovalDeniedError, match="repository_not_allowlisted"):
            await service.approve_work_order(work_order.id)
        assert work_order.status == WorkOrderStatus.PENDING_APPROVAL


@pytest.mark.asyncio
async def test_capability_mismatch_returns_useful_reason_and_worker_limit_applies() -> (
    None
):
    async with AsyncSessionLocal() as session:
        service = build_execution_service(session)
        await service.register_worker(_worker("worker-capacity", max_concurrency=1))
        docker_order = await _create_approved(
            service,
            draft=_work_order_draft(required_capabilities={"docker": True}),
        )
        mismatch = await service.checkout("worker-capacity")
        assert mismatch.reason == "capability_mismatch"
        assert "docker_not_available" in mismatch.mismatch_reasons

        architecture_order = await _create_approved(
            service,
            draft=_work_order_draft(required_capabilities={"architecture": "arm64"}),
        )
        architecture_mismatch = await service.checkout("worker-capacity")
        assert architecture_mismatch.reason == "capability_mismatch"
        assert "architecture_not_supported" in architecture_mismatch.mismatch_reasons

        custom_order = await _create_approved(
            service,
            draft=_work_order_draft(required_capabilities={"approval_tier": "gold"}),
        )
        custom_mismatch = await service.checkout("worker-capacity")
        assert custom_mismatch.reason == "capability_mismatch"
        assert "capability_missing:approval_tier" in custom_mismatch.mismatch_reasons

        plain_order = await _create_approved(service)
        first = await service.checkout("worker-capacity")
        assert first.assigned
        assert first.work_order_id == plain_order
        limited = await service.checkout("worker-capacity")
        assert limited.reason == "worker_concurrency_limit"
        assert docker_order != plain_order
        assert architecture_order != plain_order
        assert custom_order != plain_order


@pytest.mark.asyncio
async def test_worker_busy_heartbeat_blocks_checkout_until_available() -> None:
    async with AsyncSessionLocal() as session:
        service = build_execution_service(session)
        await service.register_worker(_worker("worker-busy"))
        await _create_approved(service)

        busy = await service.heartbeat_worker(
            "worker-busy", status=WorkerStatus.BUSY
        )
        assert busy.status == WorkerStatus.BUSY
        busy_checkout = await service.checkout("worker-busy")
        assert busy_checkout.reason == "worker_concurrency_limit"

        available = await service.heartbeat_worker(
            "worker-busy", status=WorkerStatus.ONLINE
        )
        assert available.status == WorkerStatus.ONLINE
        assert (await service.checkout("worker-busy")).assigned


@pytest.mark.asyncio
async def test_heartbeat_ownership_completion_and_terminal_immutability() -> None:
    async with AsyncSessionLocal() as session:
        service = build_execution_service(session)
        await service.register_worker(_worker("worker-one"))
        await service.register_worker(_worker("worker-two"))
        work_order_id = await _create_approved(service)
        assignment = await service.checkout("worker-one")
        assert assignment.run_id is not None

        with pytest.raises(OwnershipConflictError):
            await service.heartbeat_run(assignment.run_id, worker_id="worker-two")
        running = await service.heartbeat_run(assignment.run_id, worker_id="worker-one")
        assert running.status == ExecutionRunStatus.RUNNING

        completed = await service.complete_run(
            assignment.run_id,
            worker_id="worker-one",
            completion=ExecutionCompletion(
                status=ExecutionRunStatus.SUCCEEDED,
                result_summary="placeholder only",
                cleanup_status="not_applicable",
            ),
        )
        assert completed.status == ExecutionRunStatus.SUCCEEDED
        work_order = await service.get_work_order(work_order_id)
        assert work_order.status == WorkOrderStatus.SUCCEEDED
        assert await service._repository.get_lease_for_run(assignment.run_id) is None

        with pytest.raises(LifecycleConflictError):
            await service.cancel_work_order(work_order_id, reason="too late")


@pytest.mark.asyncio
async def test_cancellation_and_timeout_release_active_leases() -> None:
    async with AsyncSessionLocal() as session:
        service = build_execution_service(session)
        await service.register_worker(_worker("worker-cancel"))
        cancelled_order_id = await _create_approved(service)
        cancelled_assignment = await service.checkout("worker-cancel")
        assert cancelled_assignment.run_id is not None
        cancelled = await service.cancel_work_order(
            cancelled_order_id, reason="operator_cancelled"
        )
        assert cancelled.status == WorkOrderStatus.CANCELLED
        cancelled_run = await service.get_run(cancelled_assignment.run_id)
        assert cancelled_run.status == ExecutionRunStatus.CANCELLED

        timeout_order_id = await _create_approved(service)
        timeout_assignment = await service.checkout("worker-cancel")
        assert timeout_assignment.run_id is not None
        timed_out = await service.complete_run(
            timeout_assignment.run_id,
            worker_id="worker-cancel",
            completion=ExecutionCompletion(status=ExecutionRunStatus.TIMED_OUT),
        )
        assert timed_out.status == ExecutionRunStatus.TIMED_OUT
        assert (
            await service.get_work_order(timeout_order_id)
        ).status == WorkOrderStatus.TIMED_OUT


@pytest.mark.asyncio
async def test_stale_lease_expiry_safely_requeues_and_increments_attempt_number() -> (
    None
):
    current = utcnow_naive().replace(
        year=2026,
        month=7,
        day=12,
        hour=12,
        minute=0,
        second=0,
        microsecond=0,
    )

    def clock() -> dt.datetime:
        return current

    async with AsyncSessionLocal() as session:
        service = ExecutionService(
            repository=ExecutionRepository(session),
            clock=clock,
            lease_seconds=lambda: 1,
        )
        await service.register_worker(_worker("worker-stale"))
        work_order_id = await _create_approved(service)
        first = await service.checkout("worker-stale")
        assert first.run_id is not None

        current += dt.timedelta(seconds=2)
        expired = await service.expire_stale_leases()
        assert expired.requeued_work_order_ids == (work_order_id,)
        assert expired.timed_out_run_ids == (first.run_id,)
        assert (
            await service.get_work_order(work_order_id)
        ).status == WorkOrderStatus.QUEUED
        first_run = await service.get_run(first.run_id)
        assert first_run.status == ExecutionRunStatus.TIMED_OUT

        second = await service.checkout("worker-stale")
        assert second.run_id is not None
        second_run = await service.get_run(second.run_id)
        assert (first_run.attempt_number, second_run.attempt_number) == (1, 2)


@pytest.mark.asyncio
async def test_persistence_across_independent_sessions_and_task_regression() -> None:
    async with AsyncSessionLocal() as session:
        now = utcnow_naive()
        task = Task(
            title="legacy coordination",
            status=TaskStatus.PENDING,
            created_at=now,
            updated_at=now,
        )
        session.add(task)
        service = build_execution_service(session)
        work_order_id = await _create_approved(service)
        await session.commit()
        task_id = task.id

    async with AsyncSessionLocal() as session:
        service = build_execution_service(session)
        persisted = await service.get_work_order(work_order_id)
        legacy_task = await session.get(Task, task_id)
        assert persisted.status == WorkOrderStatus.QUEUED
        assert legacy_task is not None
        assert legacy_task.status == TaskStatus.PENDING


@pytest.mark.asyncio
async def test_execution_plane_coexists_with_legacy_task_checkout_lease() -> None:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        registered = await client.post(
            "/api/agents", json={"agent_name": "legacy-coexistence-agent"}
        )
        assert registered.status_code == HTTPStatus.OK
        created = await client.post(
            "/api/tasks",
            json={"title": "legacy lease remains independent", "depends_on": []},
        )
        assert created.status_code == HTTPStatus.OK
        task_id = created.json()["id"]
        checked_out = await client.post(
            "/api/tasks/checkout",
            params={"agent_id": "legacy-coexistence-agent"},
        )
        assert checked_out.status_code == HTTPStatus.OK
        assert checked_out.json()["task"]["id"] == task_id

    async with AsyncSessionLocal() as session:
        service = build_execution_service(session)
        await service.register_worker(_worker("execution-coexistence-worker"))
        await _create_approved(service)
        assignment = await service.checkout("execution-coexistence-worker")
        assert assignment.assigned
        await session.commit()

    async with AsyncSessionLocal() as session:
        legacy_task = await session.get(Task, task_id)
        legacy_lease = await session.scalar(
            select(Lease).where(Lease.task_id == task_id)
        )
        assert legacy_task is not None
        assert legacy_task.status == TaskStatus.IN_PROGRESS
        assert legacy_lease is not None
        assert legacy_lease.agent_id == "legacy-coexistence-agent"


@pytest.mark.asyncio
async def test_execution_api_requires_configured_admin_token(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("SWITCHBOARD_ADMIN_TOKEN", "execution-test-token")
    reload_admin_token()
    transport = ASGITransport(app=app)
    payload = {
        "repository_full_name": "Nobodyworld/dev-agent-switchboard",
        "commit_sha": VALID_SHA,
        "manifest": {"name": "validate-switchboard", "version": "1"},
    }
    try:
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            unauthenticated = await client.post(
                "/api/execution/work-orders", json=payload
            )
            assert unauthenticated.status_code == HTTPStatus.UNAUTHORIZED
            created = await client.post(
                "/api/execution/work-orders",
                json=payload,
                headers={"X-Switchboard-Admin-Token": "execution-test-token"},
            )
            assert created.status_code == HTTPStatus.OK
            work_order_id = created.json()["id"]
            approved = await client.post(
                f"/api/execution/work-orders/{work_order_id}/approve",
                json={},
                headers={"Authorization": "Bearer execution-test-token"},
            )
            assert approved.status_code == HTTPStatus.OK
            assert approved.json()["status"] == "queued"
    finally:
        monkeypatch.delenv("SWITCHBOARD_ADMIN_TOKEN", raising=False)
        reload_admin_token()


@pytest.mark.asyncio
async def test_execution_api_lifecycle_returns_typed_conflict_not_500() -> None:
    transport = ASGITransport(app=app)
    payload = {
        "repository_full_name": "Nobodyworld/dev-agent-switchboard",
        "commit_sha": VALID_SHA,
        "manifest": {"name": "validate-switchboard", "version": "1"},
    }
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        created = await client.post("/api/execution/work-orders", json=payload)
        assert created.status_code == HTTPStatus.OK
        work_order_id = created.json()["id"]
        rejected = await client.post(
            f"/api/execution/work-orders/{work_order_id}/reject", json={}
        )
        assert rejected.status_code == HTTPStatus.OK
        terminal_mutation = await client.post(
            f"/api/execution/work-orders/{work_order_id}/approve", json={}
        )
        assert terminal_mutation.status_code == HTTPStatus.CONFLICT
        missing = await client.get("/api/execution/work-orders/999999")
        assert missing.status_code == HTTPStatus.NOT_FOUND


@pytest.mark.asyncio
async def test_execution_api_rejects_nested_executable_metadata() -> None:
    transport = ASGITransport(app=app)
    payload = {
        "repository_full_name": "Nobodyworld/dev-agent-switchboard",
        "commit_sha": VALID_SHA,
        "manifest": {
            "name": "validate-switchboard",
            "version": "1",
            "parameters": {"nested": {"argv": ["not", "allowed"]}},
        },
    }
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post("/api/execution/work-orders", json=payload)

    assert response.status_code == HTTPStatus.UNPROCESSABLE_ENTITY


@pytest.mark.asyncio
async def test_execution_api_checkout_assigns_registered_worker() -> None:
    """Checkout uses a request session to atomically persist its assignment."""

    transport = ASGITransport(app=app)
    payload = {
        "repository_full_name": "Nobodyworld/dev-agent-switchboard",
        "commit_sha": VALID_SHA,
        "manifest": {"name": "validate-switchboard", "version": "1"},
    }
    worker = {
        "worker_id": "api-checkout-worker",
        "display_name": "API checkout worker",
        "operating_system": "linux",
        "architecture": "x86_64",
        "python_version": "3.11.9",
    }
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        created = await client.post("/api/execution/work-orders", json=payload)
        assert created.status_code == HTTPStatus.OK
        work_order_id = created.json()["id"]
        approved = await client.post(
            f"/api/execution/work-orders/{work_order_id}/approve", json={}
        )
        assert approved.status_code == HTTPStatus.OK
        registered = await client.post("/api/execution/workers", json=worker)
        assert registered.status_code == HTTPStatus.OK

        checked_out = await client.post(
            "/api/execution/checkout", json={"worker_id": worker["worker_id"]}
        )

    assert checked_out.status_code == HTTPStatus.OK
    run = checked_out.json()["run"]
    assert run["work_order_id"] == work_order_id
    assert run["worker_id"] == worker["worker_id"]
    assert run["status"] == "assigned"


@pytest.mark.asyncio
async def test_active_lease_is_separate_from_task_leases() -> None:
    async with AsyncSessionLocal() as session:
        service = build_execution_service(session)
        await service.register_worker(_worker("worker-lease"))
        await _create_approved(service)
        assignment = await service.checkout("worker-lease")
        assert assignment.run_id is not None
        leases = await session.scalars(ExecutionLease.__table__.select())
        assert len(list(leases)) == 1
