"""Focused regression coverage for the persisted execution control plane."""

from __future__ import annotations

import datetime as dt
import hashlib
import json
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
from server.execution.evidence import (
    ArtifactRecord,
    EnvironmentIdentity,
    EvidenceReuseIdentity,
    ExecutionEvidence,
    ExecutionEvidenceDraft,
    StepEvidence,
    compute_result_contract_hash,
    compute_reuse_identity_hash,
    finalize_evidence,
)
from server.execution.exceptions import (
    ApprovalDeniedError,
    LifecycleConflictError,
    ManifestIntegrityError,
    OwnershipConflictError,
)
from server.execution.registry import get_trusted_manifest
from server.execution.repository import ExecutionRepository
from server.execution.schemas import WorkOrderCreateIn
from server.execution.service import ExecutionService
from server.models import ExecutionLease, ExecutionRun, Lease, Task
from server.settings import reload_admin_token
from server.task_status import TaskStatus
from server.time_utils import utcnow_naive

VALID_SHA = "a" * 40
_SHA256_LENGTH = 64


def _evidence_for_run(
    *, work_order_id: int, run_id: int, worker_id: str, manifest_digest: str
) -> ExecutionEvidence:
    now = dt.datetime(2026, 7, 22, 12, tzinfo=dt.UTC)
    artifact = ArtifactRecord(
        kind="command-log",
        relative_path="logs/tests.stdout.log",
        size_bytes=4,
        sha256="b" * 64,
        media_type="text/plain",
        retention_expires_at=now + dt.timedelta(days=14),
        redaction_state="none",
        produced_by_step="tests",
    )
    return finalize_evidence(
        ExecutionEvidenceDraft(
            work_order_id=work_order_id,
            run_id=run_id,
            repository_full_name="Nobodyworld/dev-agent-switchboard",
            tested_sha=VALID_SHA,
            manifest_name="validate-switchboard",
            manifest_version="1",
            manifest_digest=manifest_digest,
            worker_id=worker_id,
            environment=EnvironmentIdentity(
                operating_system="windows",
                architecture="amd64",
                python_version="3.11.9",
                fingerprint="c" * 64,
            ),
            started_at=now,
            finished_at=now + dt.timedelta(seconds=1),
            duration_seconds=1,
            terminal_status="succeeded",
            steps=[
                StepEvidence(
                    step_id="tests",
                    title="Run tests",
                    status="succeeded",
                    started_at=now,
                    finished_at=now + dt.timedelta(seconds=1),
                    duration_seconds=1,
                    exit_code=0,
                    summary="1 passed",
                    log_artifact_paths=[artifact.relative_path],
                )
            ],
            artifacts=[artifact],
            dependency_lock_status="not_declared",
            artifact_finalization_status="succeeded",
            source_cleanup_status="succeeded",
            local_record_status="succeeded",
        )
    )


def _recompute_raw_evidence_fingerprint(payload: dict[str, object]) -> None:
    canonical = dict(payload)
    canonical.pop("fingerprint", None)
    encoded = json.dumps(
        canonical, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    )
    payload["fingerprint"] = hashlib.sha256(encoded.encode("utf-8")).hexdigest()


async def _create_api_execution(
    client: AsyncClient, *, worker_id: str
) -> tuple[dict[str, object], int]:
    created = await client.post(
        "/api/execution/work-orders",
        json={
            "repository_full_name": "Nobodyworld/dev-agent-switchboard",
            "commit_sha": VALID_SHA,
            "manifest": {"name": "validate-switchboard", "version": "1"},
        },
    )
    assert created.status_code == HTTPStatus.OK
    work_order = created.json()
    approved = await client.post(
        f"/api/execution/work-orders/{work_order['id']}/approve", json={}
    )
    assert approved.status_code == HTTPStatus.OK
    registered = await client.post(
        "/api/execution/workers",
        json={
            "worker_id": worker_id,
            "display_name": "Malformed worker regression",
            "operating_system": "windows",
            "architecture": "amd64",
            "python_version": "3.11.9",
        },
    )
    assert registered.status_code == HTTPStatus.OK
    checkout = await client.post(
        "/api/execution/checkout", json={"worker_id": worker_id}
    )
    assert checkout.status_code == HTTPStatus.OK
    run_id = checkout.json()["run"]["id"]
    return work_order, run_id


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
        preferred_executor=None,
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

        busy = await service.heartbeat_worker("worker-busy", status=WorkerStatus.BUSY)
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
async def test_execution_api_defaults_reuse_off_and_rejects_caller_provenance() -> None:
    transport = ASGITransport(app=app)
    base = {
        "repository_full_name": "Nobodyworld/dev-agent-switchboard",
        "commit_sha": VALID_SHA,
        "manifest": {"name": "worker-smoke", "version": "1"},
    }
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        defaulted = await client.post("/api/execution/work-orders", json=base)
        opted_in = await client.post(
            "/api/execution/work-orders",
            json={**base, "reuse_policy": "allow_exact"},
        )
        rejected = await client.post(
            "/api/execution/work-orders",
            json={**base, "source_run_id": 7},
        )

    assert defaulted.status_code == HTTPStatus.OK
    assert defaulted.json()["reuse_policy"] == "never"
    assert opted_in.status_code == HTTPStatus.OK
    assert opted_in.json()["reuse_policy"] == "allow_exact"
    assert len(opted_in.json()["execution_policy_hash"]) == _SHA256_LENGTH
    assert rejected.status_code == HTTPStatus.UNPROCESSABLE_ENTITY
    assert "source_run_id" not in opted_in.text
    assert "evidence_root" not in opted_in.text


@pytest.mark.asyncio
async def test_reuse_candidate_api_persists_only_bounded_server_provenance() -> None:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        created = await client.post(
            "/api/execution/work-orders",
            json={
                "repository_full_name": "Nobodyworld/dev-agent-switchboard",
                "commit_sha": VALID_SHA,
                "manifest": {"name": "worker-smoke", "version": "1"},
                "reuse_policy": "allow_exact",
            },
        )
        assert created.status_code == HTTPStatus.OK
        order = created.json()
        approved = await client.post(
            f"/api/execution/work-orders/{order['id']}/approve", json={}
        )
        assert approved.status_code == HTTPStatus.OK
        registered = await client.post(
            "/api/execution/workers",
            json={
                "worker_id": "api-reuse-worker",
                "display_name": "API reuse worker",
                "operating_system": "linux",
                "architecture": "x86_64",
                "python_version": "3.11",
                "capabilities": {"git_available": True},
            },
        )
        assert registered.status_code == HTTPStatus.OK
        checkout = await client.post(
            "/api/execution/checkout", json={"worker_id": "api-reuse-worker"}
        )
        assert checkout.status_code == HTTPStatus.OK
        run_id = checkout.json()["run"]["id"]
        manifest = get_trusted_manifest("worker-smoke", "1")
        assert manifest is not None
        identity = EvidenceReuseIdentity(
            repository_full_name=order["repository_full_name"],
            tested_sha=order["commit_sha"],
            manifest_name=order["manifest_name"],
            manifest_version=order["manifest_version"],
            manifest_digest=order["manifest_digest"],
            worker_environment_fingerprint="c" * 64,
            dependency_lock_hashes=[],
            execution_policy_hash=order["execution_policy_hash"],
            result_contract_hash=compute_result_contract_hash(
                fixed_step_metadata=manifest.fixed_step_metadata,
                artifact_declarations=manifest.artifact_declarations,
                dependency_lock_paths=manifest.dependency_lock_paths,
            ),
        )
        identity_hash = compute_reuse_identity_hash(identity)
        lookup = await client.post(
            f"/api/execution/runs/{run_id}/reuse-candidate",
            json={
                "worker_id": "api-reuse-worker",
                "reuse_identity": identity.model_dump(mode="json"),
                "reuse_identity_hash": identity_hash,
            },
        )
        persisted = await client.get(f"/api/execution/runs/{run_id}")

    assert lookup.status_code == HTTPStatus.OK
    assert lookup.json() == {
        "decision": "unavailable",
        "reason": "exact_candidate_not_found",
        "candidate": None,
    }
    assert persisted.status_code == HTTPStatus.OK
    assert persisted.json()["reuse_identity_hash"] == identity_hash
    assert persisted.json()["reuse_decision"] == "unavailable"
    assert persisted.json()["reused_from_run_id"] is None
    for forbidden in ("evidence_root", "local_path", '"argv"', '"command"'):
        assert forbidden not in lookup.text
        assert forbidden not in persisted.text


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


@pytest.mark.parametrize(
    "summary",
    [
        r"malformed worker retained C:\Users\worker\checkout\test.log",
        "malformed worker retained /home/worker/checkout/test.log",
    ],
)
@pytest.mark.asyncio
async def test_malformed_worker_nested_evidence_path_fails_before_persistence(
    summary: str,
) -> None:
    transport = ASGITransport(app=app)
    worker_id = "malformed-evidence-worker"
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        work_order, run_id = await _create_api_execution(client, worker_id=worker_id)
        evidence = _evidence_for_run(
            work_order_id=int(work_order["id"]),
            run_id=run_id,
            worker_id=worker_id,
            manifest_digest=str(work_order["manifest_digest"]),
        )
        evidence_payload = evidence.model_dump(mode="json")
        evidence_payload["steps"][0]["summary"] = summary
        _recompute_raw_evidence_fingerprint(evidence_payload)

        rejected = await client.post(
            f"/api/execution/runs/{run_id}/complete",
            json={
                "worker_id": worker_id,
                "status": "succeeded",
                "result_summary": "ordinary summary",
                "artifact_metadata": [
                    item.model_dump(mode="json") for item in evidence.artifacts
                ],
                "evidence_metadata": evidence_payload,
            },
        )
        assert rejected.status_code == HTTPStatus.UNPROCESSABLE_ENTITY

        persisted = await client.get(f"/api/execution/runs/{run_id}")
        listed = await client.get("/api/execution/runs")

    assert persisted.status_code == HTTPStatus.OK
    assert persisted.json()["status"] == "assigned"
    assert persisted.json()["result_summary"] is None
    assert persisted.json()["evidence_metadata"] is None
    assert listed.status_code == HTTPStatus.OK
    assert summary not in listed.text


@pytest.mark.asyncio
async def test_completion_paths_rejected_then_safe_references_persist() -> None:
    transport = ASGITransport(app=app)
    worker_id = "malformed-completion-worker"
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        _work_order, run_id = await _create_api_execution(client, worker_id=worker_id)
        for field, value in (
            ("result_summary", r"result at C:\worker\result.json"),
            ("result_summary", "result at /srv/worker/result.json"),
            ("terminal_reason", r"cleanup_failed:C:\worker\checkout"),
            ("terminal_reason", "cleanup_failed:/tmp/checkout"),
        ):
            rejected = await client.post(
                f"/api/execution/runs/{run_id}/complete",
                json={
                    "worker_id": worker_id,
                    "status": "succeeded",
                    field: value,
                },
            )
            assert rejected.status_code == HTTPStatus.UNPROCESSABLE_ENTITY
            unchanged = await client.get(f"/api/execution/runs/{run_id}")
            assert unchanged.status_code == HTTPStatus.OK
            assert unchanged.json()["status"] == "assigned"
            assert unchanged.json()["result_summary"] is None

        accepted = await client.post(
            f"/api/execution/runs/{run_id}/complete",
            json={
                "worker_id": worker_id,
                "status": "succeeded",
                "result_summary": (
                    "Report artifacts/report.json and log logs/tests.stdout.log"
                ),
                "terminal_reason": "validation_completed",
                "cleanup_status": "succeeded",
            },
        )
        listed = await client.get("/api/execution/runs")

    assert accepted.status_code == HTTPStatus.OK
    assert accepted.json()["status"] == "succeeded"
    assert listed.status_code == HTTPStatus.OK
    assert listed.json()[0]["result_summary"] == (
        "Report artifacts/report.json and log logs/tests.stdout.log"
    )


@pytest.mark.asyncio
async def test_run_and_evidence_apis_fail_closed_for_persisted_local_paths() -> None:
    transport = ASGITransport(app=app)
    worker_id = "corrupt-persisted-worker"
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        work_order, run_id = await _create_api_execution(client, worker_id=worker_id)

    async with AsyncSessionLocal() as session:
        run = await session.get(ExecutionRun, run_id)
        assert run is not None
        run.result_summary = r"persisted leak C:\worker\result.json"
        await session.commit()

    fail_closed_transport = ASGITransport(app=app, raise_app_exceptions=False)
    async with AsyncClient(
        transport=fail_closed_transport, base_url="http://test"
    ) as client:
        listed = await client.get("/api/execution/runs")
    assert listed.status_code == HTTPStatus.INTERNAL_SERVER_ERROR
    assert r"C:\worker\result.json" not in listed.text

    evidence = _evidence_for_run(
        work_order_id=int(work_order["id"]),
        run_id=run_id,
        worker_id=worker_id,
        manifest_digest=str(work_order["manifest_digest"]),
    )
    malformed_evidence = evidence.model_dump(mode="json")
    steps = malformed_evidence["steps"]
    assert isinstance(steps, list)
    step = steps[0]
    assert isinstance(step, dict)
    step["summary"] = "persisted leak /home/worker/result.json"
    _recompute_raw_evidence_fingerprint(malformed_evidence)
    async with AsyncSessionLocal() as session:
        run = await session.get(ExecutionRun, run_id)
        assert run is not None
        run.result_summary = "safe relative log logs/tests.stdout.log"
        run.evidence_metadata = malformed_evidence
        await session.commit()

    async with AsyncClient(
        transport=fail_closed_transport, base_url="http://test"
    ) as client:
        evidence_response = await client.get(f"/api/execution/runs/{run_id}/evidence")
    assert evidence_response.status_code == HTTPStatus.INTERNAL_SERVER_ERROR
    assert "/home/worker/result.json" not in evidence_response.text


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
