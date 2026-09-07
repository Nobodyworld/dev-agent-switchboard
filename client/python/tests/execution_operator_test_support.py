"""Coherent recorded reports for operator contract regressions."""

from __future__ import annotations

import datetime as dt
from dataclasses import replace

from client.python.execution_operator.models import (
    OperatorLifecycleReport,
    RunSummary,
    RuntimeSummary,
    StepSummary,
)
from client.python.execution_operator.report_contract import (
    PREFLIGHT_CHECKS,
    success_phases,
)


def make_operator_report(
    *,
    runtime: RuntimeSummary | None = None,
    runs: list[RunSummary] | None = None,
    mode: str = "fresh-only",
) -> OperatorLifecycleReport:
    """Build a complete schema-2 fixture, not a partial success placeholder."""

    runtime = runtime or RuntimeSummary(
        schema_version=1,
        runtime_id="5c75a6df-cd63-4b86-9eca-38408a4a6650",
        repository_full_name="Nobodyworld/dev-agent-switchboard",
        target_sha="a" * 40,
        manifest_name="worker-smoke",
        manifest_version="1",
        manifest_digest="b" * 64,
        mode=mode,
        command_identity="validation-lifecycle@1",
        created_at="2026-08-28T00:00:00Z",
    )
    created = dt.datetime.fromisoformat(runtime.created_at.replace("Z", "+00:00"))
    expires = (created + dt.timedelta(days=14)).isoformat().replace("+00:00", "Z")
    fresh = RunSummary(
        schema_version=1,
        work_order_id=1,
        run_id=2,
        source_run_id=2,
        phase="fresh",
        worker_id="operator-test-worker",
        status="succeeded",
        reuse_decision="fresh",
        reused_from_run_id=None,
        reuse_identity_hash="a" * 64,
        evidence_fingerprint="b" * 64,
        evidence_retention_expires_at=expires,
        routing_policy="first_available",
        route_reason="routing_selected",
        required_quota_units=0,
        reserved_quota_units=0,
        quota_reservation_state="not_required",
        eligible_candidate_count=1,
        step_count=1,
        artifact_count=0,
        artifact_total_bytes=0,
        route_verified=True,
        evidence_verified=True,
        local_evidence_verified=True,
        source_checkout_unchanged=True,
        steps=[StepSummary("python-version", "succeeded", 0.1)],
    )
    reuse = runtime.mode == "fresh-then-exact-reuse"
    if runs is None:
        runs = [fresh]
        if reuse:
            runs.append(
                replace(
                    fresh,
                    work_order_id=3,
                    run_id=4,
                    phase="reuse",
                    reuse_decision="reused",
                    reused_from_run_id=fresh.run_id,
                    evidence_fingerprint="c" * 64,
                    step_count=0,
                    steps=[],
                )
            )
    return OperatorLifecycleReport(
        outcome="succeeded",
        reason="lifecycle_verified",
        runtime=runtime,
        phases=list(success_phases(runtime.mode)),
        preflight_checks=list(PREFLIGHT_CHECKS),
        preflight_passed=True,
        server_ready=True,
        worker_ready=True,
        fresh_approved=True,
        reuse_approved=reuse,
        runs=runs,
        active_lease_count=0,
        worker_active_run_count=0,
        owned_processes_stopped=True,
        port_released=True,
        canonical_checkout_unchanged=True,
        operator_action_count=1 + int(reuse),
        avoided_deterministic_step_count=runs[0].step_count if reuse and runs else 0,
        completed_at=(created + dt.timedelta(seconds=1))
        .isoformat()
        .replace("+00:00", "Z"),
    )
