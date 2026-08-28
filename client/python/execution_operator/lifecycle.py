"""Authoritative fresh and guarded exact-reuse operator lifecycle."""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import os
import sqlite3
import time
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any, Literal, cast

from client.python.execution_worker.client import ExecutionClient, ExecutionClientError
from client.python.execution_worker.evidence import (
    EvidenceLimits,
    EvidenceStore,
    verify_reuse_candidate,
)
from server.execution.evidence import ExecutionEvidence, ReuseCandidate
from server.execution.schemas import ExecutionRunOut, RouteProvenanceOut, WorkOrderOut

from .config import OperatorLifecycleConfig
from .models import (
    ArtifactSummary,
    OperatorLifecycleFailure,
    OperatorLifecycleReport,
    RunSummary,
    StepSummary,
    utc_now_text,
)
from .preflight import PREFLIGHT_CHECKS, PreflightResult, run_preflight, source_snapshot
from .processes import OwnedProcess, launch_server, launch_worker, port_is_released
from .runtime import (
    REPORT_JSON_NAME,
    RuntimeLayout,
    create_runtime,
    inspect_runtime,
    write_report,
)

ApprovalCallback = Callable[[Literal["fresh", "reuse"], str], bool]
_TERMINAL = {"succeeded", "failed", "timed_out", "cancelled"}
_MAX_WORKERS = 100
_PHASE_ORDER = {
    name: index
    for index, name in enumerate(
        (
            "preflight_passed",
            "runtime_created",
            "server_healthy",
            "worker_online",
            "fresh_created",
            "fresh_approval_required",
            "fresh_approved",
            "fresh_queued",
            "fresh_running",
            "fresh_succeeded",
            "fresh_verified",
            "reuse_approval_required",
            "reuse_created",
            "reuse_approved",
            "reuse_queued",
            "reuse_succeeded",
            "reuse_verified",
            "shutdown_started",
            "cleanup_verified",
            "completed",
        )
    )
}


def _record_phase(report: OperatorLifecycleReport, phase: str) -> None:
    position = _PHASE_ORDER.get(phase)
    previous = _PHASE_ORDER.get(report.phases[-1], -1) if report.phases else -1
    if position is None or position <= previous:
        raise OperatorLifecycleFailure("lifecycle_transition_invalid")
    report.phases.append(phase)


def _wait_until(
    predicate: Callable[[], Any], *, timeout: float, interval: float, reason: str
) -> Any:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            value = predicate()
        except (ExecutionClientError, OSError, ValueError):
            value = None
        if value:
            return value
        time.sleep(interval)
    raise OperatorLifecycleFailure(reason)


def _work_order_payload(
    config: OperatorLifecycleConfig,
    *,
    phase: Literal["fresh", "reuse"],
) -> dict[str, object]:
    reuse_policy = "never" if phase == "fresh" else "require_exact"
    return {
        "schema_version": 1,
        "repository_full_name": config.repository_full_name,
        "commit_sha": config.target_sha,
        "manifest": {
            "name": config.manifest_name,
            "version": config.manifest_version,
            "parameters": {},
        },
        "required_capabilities": {},
        "permitted_paths": [],
        "forbidden_scope_notes": "operator lifecycle read-only validation",
        "expected_artifact_kinds": [],
        "approval_policy": "explicit",
        "timeout_seconds": config.work_order_timeout_seconds,
        "resource_metadata": {"operator_lifecycle_phase": phase},
        "network_policy": "worker_restricted",
        "repository_write": False,
        "preferred_executor": config.worker_id,
        "reuse_policy": reuse_policy,
        "routing_policy": config.routing_policy,
        "required_quota_units": 0,
    }


def _approval_identity(config: OperatorLifecycleConfig, phase: str) -> str:
    return f"{phase}:{config.repository_full_name}@{config.target_sha}"


def _validate_order(
    payload: Mapping[str, Any],
    config: OperatorLifecycleConfig,
    expected_status: str,
    expected_digest: str,
) -> WorkOrderOut:
    try:
        order = WorkOrderOut.model_validate(payload)
    except ValueError as error:
        raise OperatorLifecycleFailure("work_order_response_invalid") from error
    if (
        order.repository_full_name != config.repository_full_name
        or order.commit_sha != config.target_sha
        or order.manifest_name != config.manifest_name
        or order.manifest_version != config.manifest_version
        or order.manifest_digest != expected_digest
        or order.preferred_executor != config.worker_id
        or order.repository_write_allowed
        or order.network_policy.value != "worker_restricted"
        or order.status.value != expected_status
    ):
        raise OperatorLifecycleFailure("work_order_identity_mismatch")
    return order


def _wait_server(client: ExecutionClient, config: OperatorLifecycleConfig) -> None:
    def ready() -> bool:
        payload = client.health_ready()
        return payload.get("ok") is True

    _wait_until(
        ready,
        timeout=config.startup_timeout_seconds,
        interval=config.poll_interval_seconds,
        reason="server_readiness_timeout",
    )


def _wait_worker(client: ExecutionClient, config: OperatorLifecycleConfig) -> None:
    def ready() -> bool:
        payload = client.list_workers()
        items = payload.get("items")
        if not isinstance(items, list) or len(items) > _MAX_WORKERS:
            return False
        matches = [
            item
            for item in items
            if isinstance(item, Mapping) and item.get("worker_id") == config.worker_id
        ]
        if len(matches) != 1:
            return False
        item = matches[0]
        repositories = item.get("repository_full_names")
        worker_ready = (
            item.get("status") == "online"
            and item.get("activity_state") == "active"
            and item.get("active_run_count") == 0
            and repositories == [config.repository_full_name]
        )
        if not worker_ready:
            return False
        readiness = client.repository_readiness(
            repository_full_name=config.repository_full_name,
            manifest_name=config.manifest_name,
            manifest_version=config.manifest_version,
            preferred_executor=config.worker_id,
        )
        return (
            readiness.get("selected_worker_id") == config.worker_id
            and readiness.get("ready_worker_count") == 1
            and readiness.get("eligible_worker_count") == 1
        )

    _wait_until(
        ready,
        timeout=config.startup_timeout_seconds,
        interval=config.poll_interval_seconds,
        reason="worker_readiness_timeout",
    )


def _wait_terminal_run(
    client: ExecutionClient,
    config: OperatorLifecycleConfig,
    worker: OwnedProcess,
    work_order_id: int,
) -> ExecutionRunOut:
    def terminal() -> ExecutionRunOut | None:
        if not worker.running():
            raise OperatorLifecycleFailure("worker_process_exited")
        runs = client.list_runs(work_order_id)
        if len(runs) > 1:
            raise OperatorLifecycleFailure("unexpected_run_count")
        if not runs:
            return None
        try:
            run = ExecutionRunOut.model_validate(runs[0])
        except ValueError as error:
            raise OperatorLifecycleFailure("run_response_invalid") from error
        return run if run.status.value in _TERMINAL else None

    return cast(
        ExecutionRunOut,
        _wait_until(
            terminal,
            timeout=config.terminal_timeout_seconds,
            interval=config.poll_interval_seconds,
            reason="run_terminal_timeout",
        ),
    )


def _source_is_unchanged(
    config: OperatorLifecycleConfig, preflight: PreflightResult
) -> bool:
    try:
        return source_snapshot(config) == preflight.source
    except OperatorLifecycleFailure:
        return False


def _worker_source_empty(layout: RuntimeLayout) -> bool:
    try:
        return not any(layout.worker_source.iterdir())
    except OSError:
        return False


def _verify_local_fresh(  # noqa: PLR0911, PLR0912 - verification is explicit
    config: OperatorLifecycleConfig,
    layout: RuntimeLayout,
    run: ExecutionRunOut,
    evidence: ExecutionEvidence,
) -> bool:
    limits = EvidenceLimits(
        maximum_artifact_count=config.maximum_artifact_count,
        maximum_artifact_bytes=config.maximum_artifact_bytes,
        maximum_total_bytes=config.maximum_total_evidence_bytes,
    )
    if run.evidence_retention_expires_at is None:
        return False
    store = EvidenceStore(
        root=layout.retained_evidence,
        run_directory=layout.retained_evidence / f"run-{run.id}",
        worker_id=config.worker_id,
        run_id=run.id,
        created_at=evidence.started_at,
        retention_expires_at=run.evidence_retention_expires_at,
        limits=limits,
    )
    try:
        store.verify_ownership()
        if (
            store.result.is_symlink()
            or store.result.stat().st_size > config.maximum_artifact_bytes
        ):
            return False
        payload = json.loads(store.result.read_bytes().decode("utf-8"))
        if not isinstance(payload, dict) or set(payload) != {
            "evidence",
            "result_summary",
            "reuse_identity",
            "reuse_identity_hash",
        }:
            return False
        if ExecutionEvidence.model_validate(payload["evidence"]) != evidence:
            return False
        total = 0
        for record in run.artifact_metadata:
            artifact = store.run_directory.joinpath(*record.relative_path.split("/"))
            if artifact.is_symlink() or not artifact.is_file():
                return False
            if artifact.stat().st_size != record.size_bytes:
                return False
            if record.size_bytes > config.maximum_artifact_bytes:
                return False
            data = artifact.read_bytes()
            total += len(data)
            if (
                len(data) != record.size_bytes
                or len(data) > config.maximum_artifact_bytes
                or total > config.maximum_total_evidence_bytes
                or hashlib.sha256(data).hexdigest() != record.sha256
            ):
                return False
        store.verify_ownership()
    except (
        OSError,
        UnicodeDecodeError,
        json.JSONDecodeError,
        ValueError,
        RuntimeError,
    ):
        return False
    if run.reuse_identity is None or run.reuse_identity_hash is None:
        return config.mode == "fresh-only"
    if (
        run.evidence_retention_expires_at is None
        or run.source_evidence_fingerprint is not None
    ):
        return False
    try:
        candidate = ReuseCandidate(
            source_run_id=run.id,
            expected_source_worker_id=config.worker_id,
            expected_source_evidence_fingerprint=evidence.fingerprint,
            reuse_identity=run.reuse_identity,
            reuse_identity_hash=run.reuse_identity_hash,
            source_created_at=evidence.started_at,
            retention_expires_at=run.evidence_retention_expires_at,
            artifacts=run.artifact_metadata,
        )
        verification = verify_reuse_candidate(
            evidence_root=layout.retained_evidence,
            worker_id=config.worker_id,
            candidate=candidate,
            now=dt.datetime.now(dt.UTC),
            limits=limits,
        )
    except (OSError, ValueError, RuntimeError):
        return False
    return verification.verified


def _verify_run(  # noqa: PLR0913 - trust inputs stay explicit
    *,
    client: ExecutionClient,
    config: OperatorLifecycleConfig,
    layout: RuntimeLayout,
    preflight: PreflightResult,
    order: WorkOrderOut,
    run: ExecutionRunOut,
    phase: Literal["fresh", "reuse"],
    source: RunSummary | None,
) -> RunSummary:
    if (
        run.work_order_id != order.id
        or run.worker_id != config.worker_id
        or run.status.value != "succeeded"
    ):
        terminal_reason = run.terminal_reason or "terminal_reason_unavailable"
        raise OperatorLifecycleFailure(
            f"{phase}_run_{run.status.value}:{terminal_reason}"
        )
    try:
        evidence = ExecutionEvidence.model_validate(client.get_run_evidence(run.id))
        route = RouteProvenanceOut.model_validate(client.get_work_order_route(order.id))
    except (ExecutionClientError, ValueError) as error:
        raise OperatorLifecycleFailure(f"{phase}_evidence_invalid") from error
    route_verified = (
        route.selected_worker_id == config.worker_id
        and route.routing_policy.value == config.routing_policy
        and route.explicit_pin_applied
        and route.quota_reservation_state.value in {"not_required", "consumed"}
    )
    evidence_verified = (
        evidence.work_order_id == order.id
        and evidence.run_id == run.id
        and evidence.repository_full_name == config.repository_full_name
        and evidence.tested_sha == config.target_sha
        and evidence.manifest_name == config.manifest_name
        and evidence.manifest_version == config.manifest_version
        and evidence.manifest_digest == preflight.manifest_digest
        and evidence.worker_id == config.worker_id
        and evidence.terminal_status == "succeeded"
        and evidence.source_cleanup_status == "succeeded"
        and evidence.artifacts == run.artifact_metadata
        and run.route_provenance == route
    )
    unchanged = _source_is_unchanged(config, preflight) and _worker_source_empty(layout)
    if phase == "fresh":
        local_verified = _verify_local_fresh(config, layout, run, evidence)
        decision_ok = run.reuse_decision.value == "fresh"
        source_ok = run.reused_from_run_id is None
        expected_steps = tuple(
            step_id for step_id, _required in preflight.manifest_steps
        )
        required_steps = {
            step_id for step_id, required in preflight.manifest_steps if required
        }
        evidence_verified = (
            evidence_verified
            and tuple(step.step_id for step in evidence.steps) == expected_steps
            and all(
                step.status == "succeeded"
                for step in evidence.steps
                if step.step_id in required_steps
            )
        )
    else:
        local_verified = source is not None and source.local_evidence_verified
        decision_ok = run.reuse_decision.value == "reused"
        source_ok = (
            source is not None
            and run.reused_from_run_id == source.run_id
            and run.source_evidence_fingerprint == source.evidence_fingerprint
            and run.evidence_retention_expires_at
            == dt.datetime.fromisoformat(
                source.evidence_retention_expires_at.replace("Z", "+00:00")
            )
            if source is not None and source.evidence_retention_expires_at
            else False
        )
        evidence_verified = (
            evidence_verified and not evidence.steps and not evidence.artifacts
        )
    verification_checks = (
        ("route", route_verified),
        ("evidence", evidence_verified),
        ("retained_evidence", local_verified),
        ("source_cleanup", unchanged),
        ("reuse_decision", decision_ok),
        ("source_link", source_ok),
    )
    failed_check = next(
        (name for name, passed in verification_checks if not passed), None
    )
    if failed_check is not None:
        raise OperatorLifecycleFailure(f"{phase}_verification_failed:{failed_check}")
    return RunSummary(
        work_order_id=order.id,
        run_id=run.id,
        phase=phase,
        worker_id=run.worker_id,
        status=run.status.value,
        reuse_decision=run.reuse_decision.value,
        reused_from_run_id=run.reused_from_run_id,
        evidence_fingerprint=evidence.fingerprint,
        evidence_retention_expires_at=(
            run.evidence_retention_expires_at.isoformat().replace("+00:00", "Z")
            if run.evidence_retention_expires_at
            else None
        ),
        step_count=len(evidence.steps),
        artifact_count=len(evidence.artifacts),
        route_verified=route_verified,
        evidence_verified=evidence_verified,
        local_evidence_verified=local_verified,
        source_checkout_unchanged=unchanged,
        steps=[
            StepSummary(
                step_id=step.step_id,
                status=step.status,
                duration_seconds=step.duration_seconds,
            )
            for step in evidence.steps
        ],
        artifacts=[
            ArtifactSummary(
                kind=artifact.kind,
                relative_path=artifact.relative_path,
                size_bytes=artifact.size_bytes,
                sha256=artifact.sha256,
            )
            for artifact in evidence.artifacts
        ],
    )


def _execute_phase(  # noqa: PLR0913 - lifecycle inputs stay explicit
    *,
    client: ExecutionClient,
    config: OperatorLifecycleConfig,
    layout: RuntimeLayout,
    preflight: PreflightResult,
    approval: ApprovalCallback,
    phase: Literal["fresh", "reuse"],
    source: RunSummary | None,
    worker: OwnedProcess,
    report: OperatorLifecycleReport,
) -> RunSummary:
    if phase == "reuse":
        _record_phase(report, "reuse_approval_required")
        if not approval(phase, _approval_identity(config, phase)):
            raise OperatorLifecycleFailure("reuse_approval_denied")
        report.operator_action_count += 1
    order = _validate_order(
        client.create_work_order(_work_order_payload(config, phase=phase)),
        config,
        "pending_approval",
        preflight.manifest_digest,
    )
    _record_phase(report, f"{phase}_created")
    if phase == "fresh":
        _record_phase(report, "fresh_approval_required")
        if not approval(phase, _approval_identity(config, phase)):
            raise OperatorLifecycleFailure("fresh_approval_denied")
        report.operator_action_count += 1
    _validate_order(
        client.approve_work_order(order.id),
        config,
        "approved",
        preflight.manifest_digest,
    )
    if phase == "fresh":
        report.fresh_approved = True
    else:
        report.reuse_approved = True
    _record_phase(report, f"{phase}_approved")
    _validate_order(
        client.queue_work_order(order.id),
        config,
        "queued",
        preflight.manifest_digest,
    )
    _record_phase(report, f"{phase}_queued")
    if phase == "fresh":
        _record_phase(report, "fresh_running")
    run = _wait_terminal_run(client, config, worker, order.id)
    terminal_order = _validate_order(
        client.get_work_order(order.id),
        config,
        run.status.value,
        preflight.manifest_digest,
    )
    if run.status.value == "succeeded":
        _record_phase(report, f"{phase}_succeeded")
    summary = _verify_run(
        client=client,
        config=config,
        layout=layout,
        preflight=preflight,
        order=terminal_order,
        run=run,
        phase=phase,
        source=source,
    )
    _record_phase(report, f"{phase}_verified")
    return summary


def _active_lease_count(database: Path) -> int:
    try:
        connection = sqlite3.connect(
            f"file:{database.as_posix()}?mode=ro", uri=True, timeout=2.0
        )
        try:
            row = connection.execute("SELECT COUNT(*) FROM execution_leases").fetchone()
        finally:
            connection.close()
    except (OSError, sqlite3.Error) as error:
        raise OperatorLifecycleFailure("lease_verification_failed") from error
    if row is None or not isinstance(row[0], int) or row[0] < 0:
        raise OperatorLifecycleFailure("lease_verification_failed")
    return row[0]


def _worker_active_count(client: ExecutionClient, worker_id: str) -> int:
    payload = client.list_workers()
    items = payload.get("items")
    if not isinstance(items, list):
        raise OperatorLifecycleFailure("worker_cleanup_verification_failed")
    matches = [
        item
        for item in items
        if isinstance(item, Mapping) and item.get("worker_id") == worker_id
    ]
    if len(matches) != 1 or not isinstance(matches[0].get("active_run_count"), int):
        raise OperatorLifecycleFailure("worker_cleanup_verification_failed")
    return int(matches[0]["active_run_count"])


def _assert_control_plane_clean(
    report: OperatorLifecycleReport,
    client: ExecutionClient,
    config: OperatorLifecycleConfig,
    layout: RuntimeLayout,
) -> None:
    report.active_lease_count = _active_lease_count(layout.database)
    report.worker_active_run_count = _worker_active_count(client, config.worker_id)
    if report.active_lease_count != 0 or report.worker_active_run_count != 0:
        raise OperatorLifecycleFailure("terminal_cleanup_incomplete")


def _stop_owned(processes: list[OwnedProcess], timeout: float) -> bool:
    verified = True
    for process in reversed(processes):
        try:
            verified = process.stop(timeout=timeout) and verified
        except OperatorLifecycleFailure:
            verified = False
    return verified


def run_validation_lifecycle(  # noqa: PLR0915 - fail-closed phases stay visible
    config: OperatorLifecycleConfig, *, approval: ApprovalCallback
) -> OperatorLifecycleReport:
    """Run one new lifecycle; failures after creation preserve and report runtime."""

    preflight = run_preflight(config)
    layout, runtime_summary = create_runtime(config, preflight)
    report = OperatorLifecycleReport(
        runtime=runtime_summary,
        phases=["preflight_passed", "runtime_created"],
        preflight_checks=list(PREFLIGHT_CHECKS),
        preflight_passed=True,
    )
    processes: list[OwnedProcess] = []
    failure: OperatorLifecycleFailure | None = None
    token = os.environ.get("SWITCHBOARD_ADMIN_TOKEN", "")
    try:
        if not token.strip():
            raise OperatorLifecycleFailure("admin_token_missing")
        server = launch_server(config, layout, runtime_summary, token)
        processes.append(server)
        with ExecutionClient(
            f"http://{config.host}:{config.port}",
            config.worker_id,
            token,
            timeout=config.http_timeout_seconds,
        ) as client:

            _wait_server(client, config)
            report.server_ready = True
            _record_phase(report, "server_healthy")
            worker = launch_worker(config, layout, runtime_summary, token)
            processes.append(worker)
            _wait_worker(client, config)
            report.worker_ready = True
            _record_phase(report, "worker_online")
            fresh = _execute_phase(
                client=client,
                config=config,
                layout=layout,
                preflight=preflight,
                approval=approval,
                phase="fresh",
                source=None,
                worker=worker,
                report=report,
            )
            report.runs.append(fresh)
            _assert_control_plane_clean(report, client, config, layout)
            if config.mode == "fresh-then-exact-reuse":
                reuse = _execute_phase(
                    client=client,
                    config=config,
                    layout=layout,
                    preflight=preflight,
                    approval=approval,
                    phase="reuse",
                    source=fresh,
                    worker=worker,
                    report=report,
                )
                report.runs.append(reuse)
                report.avoided_deterministic_step_count = fresh.step_count
            _assert_control_plane_clean(report, client, config, layout)
    except OperatorLifecycleFailure as error:
        failure = error
    except KeyboardInterrupt:
        failure = OperatorLifecycleFailure("operator_interrupted")
    except (ExecutionClientError, OSError, ValueError, sqlite3.Error) as error:
        failure = OperatorLifecycleFailure("operator_lifecycle_failure")
        failure.__cause__ = error
    finally:
        _record_phase(report, "shutdown_started")
        report.owned_processes_stopped = _stop_owned(
            processes, config.shutdown_timeout_seconds
        )
        report.port_released = port_is_released(config.host, config.port)
        report.canonical_checkout_unchanged = _source_is_unchanged(config, preflight)
        if not report.owned_processes_stopped and failure is None:
            failure = OperatorLifecycleFailure("owned_process_cleanup_unproven")
        if not report.port_released and failure is None:
            failure = OperatorLifecycleFailure("loopback_port_not_released")
        if not report.canonical_checkout_unchanged and failure is None:
            failure = OperatorLifecycleFailure("source_checkout_changed")
        if (
            report.owned_processes_stopped
            and report.port_released
            and report.canonical_checkout_unchanged
        ):
            _record_phase(report, "cleanup_verified")
        if failure is None:
            _record_phase(report, "completed")
        report.outcome = "failed" if failure else "succeeded"
        report.reason = failure.reason if failure else "lifecycle_verified"
        report.failed_runtime_preserved = failure is not None
        report.completed_at = utc_now_text()
        write_report(layout, report, maximum_bytes=config.report_maximum_bytes)
    if failure is not None:
        raise failure
    return report


def inspect_validation_runtime(root: Path) -> OperatorLifecycleReport:
    """Read a marker and optional report without starting or mutating anything."""

    layout, summary = inspect_runtime(root)
    report_path = layout.reports / REPORT_JSON_NAME
    if (
        not report_path.is_file()
        or report_path.is_symlink()
        or report_path.stat().st_size > 1024 * 1024
    ):
        return OperatorLifecycleReport(
            outcome="inspected", reason="runtime_marker_verified", runtime=summary
        )
    try:
        payload = json.loads(report_path.read_bytes().decode("utf-8"))
        if not isinstance(payload, dict) or payload.get("runtime") != {
            "schema_version": summary.schema_version,
            "runtime_id": summary.runtime_id,
            "repository_full_name": summary.repository_full_name,
            "target_sha": summary.target_sha,
            "manifest_name": summary.manifest_name,
            "manifest_version": summary.manifest_version,
            "manifest_digest": summary.manifest_digest,
            "mode": summary.mode,
            "command_identity": summary.command_identity,
            "created_at": summary.created_at,
        }:
            raise ValueError
        runs = []
        for item in payload.pop("runs"):
            steps = [StepSummary(**step) for step in item.pop("steps")]
            artifacts = [
                ArtifactSummary(**artifact) for artifact in item.pop("artifacts")
            ]
            runs.append(RunSummary(**item, steps=steps, artifacts=artifacts))
        runtime_payload = payload.pop("runtime")
        _ = runtime_payload
        report = OperatorLifecycleReport(**payload)
        report.runtime = summary
        report.runs = runs
        report.as_dict()
        return report
    except (
        OSError,
        UnicodeDecodeError,
        json.JSONDecodeError,
        TypeError,
        ValueError,
        KeyError,
    ) as error:
        raise OperatorLifecycleFailure("runtime_report_invalid") from error


__all__ = ["ApprovalCallback", "inspect_validation_runtime", "run_validation_lifecycle"]
