"""Exact validation-evidence reuse identity, selection, and lifecycle coverage."""

from __future__ import annotations

import asyncio
import datetime as dt
import json

import pytest

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
    ReuseDecision,
    ReusePolicy,
    WorkerStatus,
    WorkOrderStatus,
)
from server.execution.evidence import (
    EnvironmentIdentity,
    EvidenceReuseIdentity,
    EvidenceReuseProvenance,
    ExecutionEvidenceDraft,
    compute_result_contract_hash,
    compute_reuse_identity_hash,
    finalize_evidence,
)
from server.execution.exceptions import (
    LifecycleConflictError,
    OwnershipConflictError,
)
from server.execution.registry import get_trusted_manifest
from server.execution.schemas import ExecutionRunOut
from server.time_utils import utcnow_naive

_SHA = "a" * 40
_WORKER = "worker-reuse"
_REUSED_ORDER_COUNT = 2


def _draft(policy: ReusePolicy = ReusePolicy.NEVER, **overrides: object):
    values: dict[str, object] = {
        "schema_version": 1,
        "repository_full_name": "Nobodyworld/dev-agent-switchboard",
        "commit_sha": _SHA,
        "manifest_name": "worker-smoke",
        "manifest_version": "1",
        "manifest_parameters": {},
        "required_capabilities": {"repository_write": False},
        "permitted_paths": (),
        "forbidden_scope_notes": "read-only",
        "expected_artifact_kinds": (),
        "approval_policy": ApprovalPolicy.EXPLICIT,
        "timeout_seconds": 120,
        "resource_metadata": {},
        "network_policy": NetworkPolicy.WORKER_RESTRICTED,
        "repository_write_allowed": False,
        "preferred_executor": None,
        "cost_ceiling": None,
        "reuse_policy": policy,
    }
    values.update(overrides)
    return WorkOrderDraft(**values)  # type: ignore[arg-type]


def _worker(worker_id: str = _WORKER) -> WorkerRegistration:
    return WorkerRegistration(
        worker_id=worker_id,
        display_name="Exact reuse test worker",
        operating_system="linux",
        architecture="x86_64",
        python_version="3.11",
        node_version=None,
        docker_available=False,
        browsers=(),
        gpu_available=False,
        unity_available=False,
        desktop_available=False,
        capabilities={"git_available": True},
        max_concurrency=4,
        network_policy_capability=NetworkPolicy.WORKER_RESTRICTED,
        repository_write_capability=False,
        status=WorkerStatus.ONLINE,
    )


def _identity(order, *, environment: str = "c" * 64) -> EvidenceReuseIdentity:
    manifest = get_trusted_manifest(order.manifest_name, order.manifest_version)
    assert manifest is not None
    return EvidenceReuseIdentity(
        repository_full_name=order.repository_full_name,
        tested_sha=order.commit_sha,
        manifest_name=order.manifest_name,
        manifest_version=order.manifest_version,
        manifest_digest=order.manifest_digest,
        worker_environment_fingerprint=environment,
        dependency_lock_hashes=[],
        execution_policy_hash=order.execution_policy_hash,
        result_contract_hash=compute_result_contract_hash(
            fixed_step_metadata=manifest.fixed_step_metadata,
            artifact_declarations=manifest.artifact_declarations,
            dependency_lock_paths=manifest.dependency_lock_paths,
        ),
    )


def _evidence(  # noqa: PLR0913 - source provenance is explicit
    *,
    order,
    run_id: int,
    identity: EvidenceReuseIdentity,
    decision: str,
    source_run_id: int | None = None,
    source_fingerprint: str | None = None,
):
    now = dt.datetime(2026, 7, 30, 12, tzinfo=dt.UTC)
    identity_hash = compute_reuse_identity_hash(identity)
    return finalize_evidence(
        ExecutionEvidenceDraft(
            work_order_id=order.id,
            run_id=run_id,
            repository_full_name=order.repository_full_name,
            tested_sha=order.commit_sha,
            manifest_name=order.manifest_name,
            manifest_version=order.manifest_version,
            manifest_digest=order.manifest_digest,
            worker_id=_WORKER,
            environment=EnvironmentIdentity(
                operating_system="linux",
                architecture="x86_64",
                python_version="3.11",
                fingerprint=identity.worker_environment_fingerprint,
            ),
            dependency_lock_hashes=identity.dependency_lock_hashes,
            started_at=now,
            finished_at=now + dt.timedelta(seconds=1),
            duration_seconds=1,
            terminal_status="succeeded",
            steps=[],
            artifacts=[],
            dependency_lock_status="not_declared",
            artifact_finalization_status="succeeded",
            source_cleanup_status="succeeded",
            local_record_status="succeeded",
            reuse_provenance=EvidenceReuseProvenance(
                decision=decision,  # type: ignore[arg-type]
                reason=("exact_evidence_verified" if decision == "reused" else "fresh"),
                reuse_identity_hash=identity_hash,
                source_run_id=source_run_id,
                source_evidence_fingerprint=source_fingerprint,
            ),
        )
    )


async def _approved(service, policy: ReusePolicy):
    order = await service.create_work_order(_draft(policy))
    await service.approve_work_order(order.id)
    return order


async def _fresh_source(service):
    order = await _approved(service, ReusePolicy.NEVER)
    assignment = await service.checkout(_WORKER)
    assert assignment.run_id is not None
    identity = _identity(order)
    evidence = _evidence(
        order=order,
        run_id=assignment.run_id,
        identity=identity,
        decision="fresh",
    )
    retention = evidence.started_at + dt.timedelta(days=14)
    run = await service.complete_run(
        assignment.run_id,
        worker_id=_WORKER,
        completion=ExecutionCompletion(
            status=ExecutionRunStatus.SUCCEEDED,
            evidence_metadata=evidence,
            reuse_decision=ReuseDecision.FRESH,
            reuse_reason="fresh_execution_completed",
            reuse_identity=identity,
            reuse_identity_hash=compute_reuse_identity_hash(identity),
            evidence_retention_expires_at=retention,
        ),
    )
    return order, run, identity, evidence


@pytest.mark.asyncio
async def test_default_never_preserves_fresh_execution_and_legacy_completion() -> None:
    async with AsyncSessionLocal() as session:
        service = build_execution_service(session)
        await service.register_worker(_worker())
        order = await _approved(service, ReusePolicy.NEVER)
        assignment = await service.checkout(_WORKER)
        assert order.reuse_policy == ReusePolicy.NEVER
        assert assignment.run_id is not None
        run = await service.complete_run(
            assignment.run_id,
            worker_id=_WORKER,
            completion=ExecutionCompletion(status=ExecutionRunStatus.SUCCEEDED),
        )
        assert run.reuse_decision == ReuseDecision.FRESH
        assert run.reused_from_run_id is None


@pytest.mark.asyncio
async def test_allow_exact_selects_source_and_records_distinct_reused_run() -> None:
    async with AsyncSessionLocal() as session:
        service = build_execution_service(session)
        await service.register_worker(_worker())
        _, source, _, source_evidence = await _fresh_source(service)

        order = await _approved(service, ReusePolicy.ALLOW_EXACT)
        assignment = await service.checkout(_WORKER)
        assert assignment.run_id is not None and assignment.run_id != source.id
        identity = _identity(order)
        lookup = await service.resolve_reuse_candidate(
            assignment.run_id,
            worker_id=_WORKER,
            reuse_identity=identity,
            reuse_identity_hash=compute_reuse_identity_hash(identity),
        )
        assert lookup.candidate is not None
        assert lookup.candidate.source_run_id == source.id
        assert lookup.candidate.expected_source_worker_id == _WORKER
        assert (
            lookup.candidate.expected_source_evidence_fingerprint
            == source_evidence.fingerprint
        )

        reused_evidence = _evidence(
            order=order,
            run_id=assignment.run_id,
            identity=identity,
            decision="reused",
            source_run_id=source.id,
            source_fingerprint=source_evidence.fingerprint,
        )
        completed = await service.complete_run(
            assignment.run_id,
            worker_id=_WORKER,
            completion=ExecutionCompletion(
                status=ExecutionRunStatus.SUCCEEDED,
                evidence_metadata=reused_evidence,
                reuse_decision=ReuseDecision.REUSED,
                reuse_reason="exact_evidence_verified",
                reuse_identity=identity,
                reuse_identity_hash=compute_reuse_identity_hash(identity),
                evidence_retention_expires_at=(
                    reused_evidence.started_at + dt.timedelta(days=14)
                ),
            ),
        )
        assert completed.id != source.id
        assert completed.reused_from_run_id == source.id
        assert completed.source_evidence_fingerprint == source_evidence.fingerprint
        assert completed.reuse_decision == ReuseDecision.REUSED
        api_payload = ExecutionRunOut.model_validate(completed).model_dump(mode="json")
        assert api_payload["reuse_identity_hash"] == compute_reuse_identity_hash(
            identity
        )
        assert api_payload["reused_from_run_id"] == source.id
        encoded = json.dumps(api_payload, sort_keys=True)
        for forbidden in (
            "evidence_root",
            "local_artifact_path",
            '"argv"',
            '"command"',
            '"script"',
        ):
            assert forbidden not in encoded
        unchanged = await service.get_run(source.id)
        assert unchanged.evidence_metadata == source.evidence_metadata


@pytest.mark.asyncio
async def test_multiple_orders_reuse_one_source_without_mutating_it() -> None:
    async with AsyncSessionLocal() as session:
        service = build_execution_service(session)
        await service.register_worker(_worker())
        _, source, _, source_evidence = await _fresh_source(service)
        reused_ids: list[int] = []
        for _ in range(_REUSED_ORDER_COUNT):
            order = await _approved(service, ReusePolicy.ALLOW_EXACT)
            assignment = await service.checkout(_WORKER)
            assert assignment.run_id is not None
            identity = _identity(order)
            lookup = await service.resolve_reuse_candidate(
                assignment.run_id,
                worker_id=_WORKER,
                reuse_identity=identity,
                reuse_identity_hash=compute_reuse_identity_hash(identity),
            )
            assert lookup.candidate is not None
            evidence = _evidence(
                order=order,
                run_id=assignment.run_id,
                identity=identity,
                decision="reused",
                source_run_id=source.id,
                source_fingerprint=source_evidence.fingerprint,
            )
            completed = await service.complete_run(
                assignment.run_id,
                worker_id=_WORKER,
                completion=ExecutionCompletion(
                    status=ExecutionRunStatus.SUCCEEDED,
                    evidence_metadata=evidence,
                    reuse_decision=ReuseDecision.REUSED,
                    reuse_reason="exact_evidence_verified",
                    reuse_identity=identity,
                    reuse_identity_hash=compute_reuse_identity_hash(identity),
                    evidence_retention_expires_at=(
                        evidence.started_at + dt.timedelta(days=14)
                    ),
                ),
            )
            reused_ids.append(completed.id)
        assert len(set(reused_ids)) == _REUSED_ORDER_COUNT
        assert all(run_id != source.id for run_id in reused_ids)
        assert (
            await service.get_run(source.id)
        ).evidence_metadata == source.evidence_metadata


@pytest.mark.asyncio
async def test_exact_lookup_rejects_changed_environment_expiry_and_database_only() -> (
    None
):
    async with AsyncSessionLocal() as session:
        service = build_execution_service(session)
        await service.register_worker(_worker())
        _, source, _, _ = await _fresh_source(service)

        order = await _approved(service, ReusePolicy.ALLOW_EXACT)
        assignment = await service.checkout(_WORKER)
        assert assignment.run_id is not None
        changed = _identity(order, environment="9" * 64)
        lookup = await service.resolve_reuse_candidate(
            assignment.run_id,
            worker_id=_WORKER,
            reuse_identity=changed,
            reuse_identity_hash=compute_reuse_identity_hash(changed),
        )
        assert lookup.candidate is None

        source.evidence_retention_expires_at = utcnow_naive() - dt.timedelta(seconds=1)
        await session.flush()
        next_order = await _approved(service, ReusePolicy.ALLOW_EXACT)
        next_assignment = await service.checkout(_WORKER)
        assert next_assignment.run_id is not None
        exact = _identity(next_order)
        expired = await service.resolve_reuse_candidate(
            next_assignment.run_id,
            worker_id=_WORKER,
            reuse_identity=exact,
            reuse_identity_hash=compute_reuse_identity_hash(exact),
        )
        assert expired.candidate is None

        source.evidence_retention_expires_at = utcnow_naive() + dt.timedelta(days=14)
        source.evidence_metadata = {}
        await session.flush()
        third_order = await _approved(service, ReusePolicy.ALLOW_EXACT)
        third_assignment = await service.checkout(_WORKER)
        assert third_assignment.run_id is not None
        third_identity = _identity(third_order)
        database_only = await service.resolve_reuse_candidate(
            third_assignment.run_id,
            worker_id=_WORKER,
            reuse_identity=third_identity,
            reuse_identity_hash=compute_reuse_identity_hash(third_identity),
        )
        assert database_only.candidate is None


@pytest.mark.asyncio
async def test_candidate_selection_is_newest_valid_and_skips_malformed_newer() -> None:
    async with AsyncSessionLocal() as session:
        service = build_execution_service(session)
        await service.register_worker(_worker())
        _, older, _, _ = await _fresh_source(service)
        _, newer, _, _ = await _fresh_source(service)
        order = await _approved(service, ReusePolicy.ALLOW_EXACT)
        assignment = await service.checkout(_WORKER)
        assert assignment.run_id is not None
        identity = _identity(order)
        newest = await service.resolve_reuse_candidate(
            assignment.run_id,
            worker_id=_WORKER,
            reuse_identity=identity,
            reuse_identity_hash=compute_reuse_identity_hash(identity),
        )
        assert newest.candidate is not None
        assert newest.candidate.source_run_id == newer.id

        await service.cancel_work_order(order.id, reason="test_next_lookup")
        newer.evidence_metadata = {}
        await session.flush()
        fallback_order = await _approved(service, ReusePolicy.ALLOW_EXACT)
        fallback_assignment = await service.checkout(_WORKER)
        assert fallback_assignment.run_id is not None
        fallback_identity = _identity(fallback_order)
        fallback = await service.resolve_reuse_candidate(
            fallback_assignment.run_id,
            worker_id=_WORKER,
            reuse_identity=fallback_identity,
            reuse_identity_hash=compute_reuse_identity_hash(fallback_identity),
        )
        assert fallback.candidate is not None
        assert fallback.candidate.source_run_id == older.id


@pytest.mark.parametrize(
    "inconsistency",
    [
        "source_order_failed",
        "source_order_cancelled",
        "source_order_timed_out",
        "source_order_finished_at_missing",
        "source_run_reused_from_present",
        "source_run_fingerprint_present",
        "source_run_candidate_metadata_present",
    ],
)
@pytest.mark.asyncio
async def test_inconsistent_newer_source_is_skipped_without_mutation(
    inconsistency: str,
) -> None:
    async with AsyncSessionLocal() as session:
        service = build_execution_service(session)
        await service.register_worker(_worker())
        older_order, older, _, _ = await _fresh_source(service)
        newer_order, newer, _, _ = await _fresh_source(service)
        await session.refresh(older_order)
        await session.refresh(older)
        await session.refresh(newer_order)
        await session.refresh(newer)

        if inconsistency == "source_order_failed":
            newer_order.status = WorkOrderStatus.FAILED
        elif inconsistency == "source_order_cancelled":
            newer_order.status = WorkOrderStatus.CANCELLED
        elif inconsistency == "source_order_timed_out":
            newer_order.status = WorkOrderStatus.TIMED_OUT
        elif inconsistency == "source_order_finished_at_missing":
            newer_order.finished_at = None
        elif inconsistency == "source_run_reused_from_present":
            newer.reused_from_run_id = older.id
        elif inconsistency == "source_run_fingerprint_present":
            newer.source_evidence_fingerprint = "f" * 64
        else:
            newer.reuse_candidate_metadata = {"source_run_id": older.id}
        await session.flush()
        malformed_snapshot = (
            newer_order.status,
            newer_order.finished_at,
            newer.reused_from_run_id,
            newer.source_evidence_fingerprint,
            newer.reuse_candidate_metadata,
        )

        order = await _approved(service, ReusePolicy.ALLOW_EXACT)
        assignment = await service.checkout(_WORKER)
        assert assignment.run_id is not None
        identity = _identity(order)
        fallback = await service.resolve_reuse_candidate(
            assignment.run_id,
            worker_id=_WORKER,
            reuse_identity=identity,
            reuse_identity_hash=compute_reuse_identity_hash(identity),
        )
        assert fallback.candidate is not None
        assert fallback.candidate.source_run_id == older.id

        await session.refresh(newer_order)
        await session.refresh(newer)
        assert (
            newer_order.status,
            newer_order.finished_at,
            newer.reused_from_run_id,
            newer.source_evidence_fingerprint,
            newer.reuse_candidate_metadata,
        ) == malformed_snapshot

        await service.cancel_work_order(order.id, reason="test_next_lookup")
        older_order.status = WorkOrderStatus.FAILED
        await session.flush()
        unavailable_order = await _approved(service, ReusePolicy.ALLOW_EXACT)
        unavailable_assignment = await service.checkout(_WORKER)
        assert unavailable_assignment.run_id is not None
        unavailable_identity = _identity(unavailable_order)
        unavailable = await service.resolve_reuse_candidate(
            unavailable_assignment.run_id,
            worker_id=_WORKER,
            reuse_identity=unavailable_identity,
            reuse_identity_hash=compute_reuse_identity_hash(unavailable_identity),
        )
        assert unavailable.candidate is None
        assert unavailable.decision == ReuseDecision.UNAVAILABLE

        await session.refresh(newer_order)
        await session.refresh(newer)
        assert (
            newer_order.status,
            newer_order.finished_at,
            newer.reused_from_run_id,
            newer.source_evidence_fingerprint,
            newer.reuse_candidate_metadata,
        ) == malformed_snapshot


@pytest.mark.asyncio
async def test_independent_sessions_concurrently_select_one_immutable_source() -> None:
    async with AsyncSessionLocal() as seed_session:
        seed = build_execution_service(seed_session)
        await seed.register_worker(_worker())
        _, source, _, source_evidence = await _fresh_source(seed)
        source_id = source.id
        source_payload = source.evidence_metadata
        await seed_session.commit()

    async with (
        AsyncSessionLocal() as first_session,
        AsyncSessionLocal() as second_session,
    ):
        first = build_execution_service(first_session)
        second = build_execution_service(second_session)
        first_order = await _approved(first, ReusePolicy.ALLOW_EXACT)
        first_assignment = await first.checkout(_WORKER)
        assert first_assignment.run_id is not None
        await first_session.commit()
        second_order = await _approved(second, ReusePolicy.ALLOW_EXACT)
        second_assignment = await second.checkout(_WORKER)
        assert second_assignment.run_id is not None
        await second_session.commit()

        first_identity = _identity(first_order)
        second_identity = _identity(second_order)

        async def resolve(service, session, run_id: int, identity):
            result = await service.resolve_reuse_candidate(
                run_id,
                worker_id=_WORKER,
                reuse_identity=identity,
                reuse_identity_hash=compute_reuse_identity_hash(identity),
            )
            await session.commit()
            return result

        first_result, second_result = await asyncio.gather(
            resolve(first, first_session, first_assignment.run_id, first_identity),
            resolve(second, second_session, second_assignment.run_id, second_identity),
        )
        assert first_assignment.run_id != second_assignment.run_id
        assert first_result.candidate is not None
        assert second_result.candidate is not None
        assert first_result.candidate.source_run_id == source_id
        assert second_result.candidate.source_run_id == source_id
        assert (
            first_result.candidate.expected_source_evidence_fingerprint
            == source_evidence.fingerprint
        )

    async with AsyncSessionLocal() as verification_session:
        persisted = await build_execution_service(verification_session).get_run(
            source_id
        )
        assert persisted.evidence_metadata == source_payload


@pytest.mark.asyncio
async def test_require_exact_never_accepts_fresh_and_terminalizes_unavailable() -> None:
    async with AsyncSessionLocal() as session:
        service = build_execution_service(session)
        await service.register_worker(_worker())
        order = await _approved(service, ReusePolicy.REQUIRE_EXACT)
        assignment = await service.checkout(_WORKER)
        assert assignment.run_id is not None
        identity = _identity(order)
        lookup = await service.resolve_reuse_candidate(
            assignment.run_id,
            worker_id=_WORKER,
            reuse_identity=identity,
            reuse_identity_hash=compute_reuse_identity_hash(identity),
        )
        assert lookup.candidate is None
        with pytest.raises(
            LifecycleConflictError, match="require_exact_forbids_fresh_execution"
        ):
            await service.complete_run(
                assignment.run_id,
                worker_id=_WORKER,
                completion=ExecutionCompletion(
                    status=ExecutionRunStatus.SUCCEEDED,
                    reuse_decision=ReuseDecision.FRESH,
                    reuse_identity=identity,
                    reuse_identity_hash=compute_reuse_identity_hash(identity),
                ),
            )
        failed = await service.complete_run(
            assignment.run_id,
            worker_id=_WORKER,
            completion=ExecutionCompletion(
                status=ExecutionRunStatus.FAILED,
                terminal_reason="exact_candidate_not_found",
                reuse_decision=ReuseDecision.UNAVAILABLE,
                reuse_reason="exact_candidate_not_found",
                reuse_identity=identity,
                reuse_identity_hash=compute_reuse_identity_hash(identity),
            ),
        )
        assert failed.reuse_decision == ReuseDecision.UNAVAILABLE
        assert failed.status == ExecutionRunStatus.FAILED


@pytest.mark.asyncio
async def test_reuse_identity_mismatch_and_lease_loss_fail_closed() -> None:
    async with AsyncSessionLocal() as session:
        service = build_execution_service(session)
        await service.register_worker(_worker())
        order = await _approved(service, ReusePolicy.ALLOW_EXACT)
        assignment = await service.checkout(_WORKER)
        assert assignment.run_id is not None
        identity = _identity(order)
        with pytest.raises(
            LifecycleConflictError, match="reuse_identity_hash_mismatch"
        ):
            await service.resolve_reuse_candidate(
                assignment.run_id,
                worker_id=_WORKER,
                reuse_identity=identity,
                reuse_identity_hash="0" * 64,
            )
        await service.cancel_work_order(order.id, reason="operator_cancelled")
        with pytest.raises(OwnershipConflictError, match="execution_lease_not_owned"):
            await service.resolve_reuse_candidate(
                assignment.run_id,
                worker_id=_WORKER,
                reuse_identity=identity,
                reuse_identity_hash=compute_reuse_identity_hash(identity),
            )
