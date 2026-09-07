# ruff: noqa: PLR2004
"""Progress observes execution without becoming approval or retained proof."""

from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import pytest

from client.python.execution_operator import lifecycle, progress
from client.python.execution_operator.config import OperatorLifecycleConfig
from client.python.execution_operator.models import OperatorLifecycleFailure
from client.python.execution_operator.preflight import PreflightResult, SourceSnapshot
from client.python.execution_operator.progress import ProgressEvent, ProgressPublisher
from client.python.execution_operator.report_contract import success_phases
from client.python.execution_operator.runtime import inspect_runtime
from client.python.tests.execution_operator_test_support import make_operator_report
from server.execution.enums import ExecutionRunStatus
from server.execution.registry import get_trusted_manifest


def _config(tmp_path: Path, mode: str) -> OperatorLifecycleConfig:
    return OperatorLifecycleConfig.from_mapping(
        {
            "schema_version": 1,
            "repository_full_name": "Nobodyworld/dev-agent-switchboard",
            "canonical_checkout": str(tmp_path / "canonical"),
            "target_sha": "a" * 40,
            "manifest_name": "worker-smoke",
            "manifest_version": "1",
            "mode": mode,
            "runtime_root": str(tmp_path / "runtime"),
            "worker_id": "operator-test-worker",
            "worker_display_name": "Operator test worker",
            "port": 18765,
        }
    )


def _run_payload(order_id: int, status: str) -> dict[str, object]:
    timestamp = "2026-09-07T00:00:00Z"
    return {
        "id": order_id * 2,
        "work_order_id": order_id,
        "worker_id": "operator-test-worker",
        "attempt_number": 1,
        "status": status,
        **dict.fromkeys(
            (
                "queued_at",
                "assigned_at",
                "lease_expires_at",
                "last_heartbeat_at",
                "created_at",
                "updated_at",
            ),
            timestamp,
        ),
        **dict.fromkeys(
            (
                "started_at",
                "finished_at",
                "result_summary",
                "terminal_reason",
                "cleanup_status",
                "evidence_metadata",
                "reuse_identity",
                "reuse_identity_hash",
                "reused_from_run_id",
                "source_evidence_fingerprint",
                "reuse_reason",
                "evidence_retention_expires_at",
            )
        ),
        "artifact_metadata": [],
        "reuse_decision": "fresh",
        "route_provenance": {
            "schema_version": 1,
            "decision_timestamp": timestamp,
            "routing_policy": "first_available",
            "selected_worker_id": "operator-test-worker",
            "reason": "routing_selected",
            "explicit_pin_applied": True,
            "eligible_candidate_count": 1,
            "required_quota_units": 0,
            "reserved_quota_units": 0,
            "quota_reservation_state": "not_required",
        },
    }


class _FakeClient:
    def __init__(self) -> None:
        self.orders: list[str] = []
        self.states = ["assigned", "assigned", "running", "succeeded"]
        self.observed: list[str] = []
        self.polls: dict[int, int] = {}

    def __enter__(self) -> _FakeClient:
        return self

    def __exit__(self, *_args: object) -> None:
        pass

    def create_work_order(self, payload: dict[str, object]) -> dict[str, object]:
        phase = payload["resource_metadata"]["operator_lifecycle_phase"]
        self.orders.append(phase)
        return {"id": len(self.orders)}

    def approve_work_order(self, order_id: int) -> dict[str, object]:
        return {"id": order_id}

    def queue_work_order(self, order_id: int) -> dict[str, object]:
        return {"id": order_id}

    def get_work_order(self, order_id: int) -> dict[str, object]:
        return {"id": order_id}

    def list_runs(self, order_id: int) -> list[dict[str, object]]:
        position = self.polls.get(order_id, 0)
        self.polls[order_id] = position + 1
        state = self.states[min(position, len(self.states) - 1)]
        self.observed.append(state)
        return [_run_payload(order_id, state)] if state else []


class _FakeProcess:
    def __init__(self) -> None:
        self.stopped = False

    def running(self) -> bool:
        return not self.stopped

    def stop(self, *, timeout: float) -> bool:
        assert timeout > 0
        self.stopped = True
        return True


def _scenario(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, mode: str = "fresh-only"
) -> SimpleNamespace:
    config = _config(tmp_path, mode)
    manifest = get_trusted_manifest("worker-smoke", "1")
    assert manifest is not None
    preflight = PreflightResult(
        SourceSnapshot("a" * 40, "b" * 40, "c" * 64),
        manifest.digest,
        tuple((step.id, step.required) for step in manifest.execution_steps),
        True,
    )
    client = _FakeClient()
    owned = [_FakeProcess(), _FakeProcess()]
    monkeypatch.setenv("SWITCHBOARD_ADMIN_TOKEN", "synthetic-process-value")
    monkeypatch.setattr(lifecycle, "run_preflight", lambda _config: preflight)
    monkeypatch.setattr(lifecycle, "ExecutionClient", lambda *_args, **_kwargs: client)
    monkeypatch.setattr(lifecycle, "launch_server", lambda *_args: owned[0])
    monkeypatch.setattr(lifecycle, "launch_worker", lambda *_args: owned[1])
    monkeypatch.setattr(lifecycle, "_wait_server", lambda *_args: None)
    monkeypatch.setattr(lifecycle, "_wait_worker", lambda *_args: None)
    monkeypatch.setattr(lifecycle, "_active_lease_count", lambda *_args: 0)
    monkeypatch.setattr(lifecycle, "_worker_active_count", lambda *_args: 0)
    monkeypatch.setattr(lifecycle, "_source_is_unchanged", lambda *_args: True)
    monkeypatch.setattr(lifecycle, "port_is_released", lambda *_args: True)
    monkeypatch.setattr(lifecycle.time, "sleep", lambda _seconds: None)
    monkeypatch.setattr(
        lifecycle,
        "_validate_order",
        lambda payload, *_args: SimpleNamespace(**payload),
    )

    def verify(**kwargs: object) -> object:
        _, runtime = inspect_runtime(config.runtime_root)
        runs = make_operator_report(runtime=runtime).runs
        return runs[0 if kwargs["phase"] == "fresh" else 1]

    monkeypatch.setattr(lifecycle, "_verify_run", verify)
    return SimpleNamespace(config=config, client=client, owned=owned)


@pytest.mark.parametrize("mode", ["fresh-only", "fresh-then-exact-reuse"])
def test_progress_observes_both_approval_boundaries_and_preserves_report(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, mode: str
) -> None:
    case = _scenario(tmp_path, monkeypatch, mode)
    events: list[ProgressEvent] = []
    decisions: list[str] = []

    def approve(phase: str, _identity: str) -> bool:
        assert events[-1].event == "approval_requested"
        assert events[-1].phase == phase
        assert case.client.orders == ["fresh"]
        decisions.append(phase)
        return True

    def observe(event: ProgressEvent) -> None:
        if event.event == "completed":
            stored = lifecycle.inspect_validation_runtime(case.config.runtime_root)
            assert stored.outcome == "succeeded"
        if event.event == "run_observed":
            assert case.client.observed[-1] == event.run_status.value
        if event.event == "cleanup_verified":
            assert all(process.stopped for process in case.owned)
        events.append(event)

    report = lifecycle.run_validation_lifecycle(
        case.config, approval=approve, observer=observe
    )
    expected = make_operator_report(runtime=report.runtime)
    assert (
        report.as_dict()
        == replace(expected, completed_at=report.completed_at).as_dict()
    )
    assert report.phases == list(success_phases(mode))
    assert report.as_dict()["schema_version"] == 2
    assert lifecycle.inspect_validation_runtime(case.config.runtime_root).as_dict() == (
        report.as_dict()
    )
    expected_phases = ["fresh"] if mode == "fresh-only" else ["fresh", "reuse"]
    assert decisions == expected_phases
    assert [event.sequence for event in events] == list(range(1, len(events) + 1))
    assert [event.event for event in events[:7]] == [
        "preflight_started",
        "preflight_passed",
        "runtime_created",
        "server_started",
        "server_ready",
        "worker_started",
        "worker_ready",
    ]
    for phase in expected_phases:
        phase_events = [event for event in events if event.phase == phase]
        kinds = [event.event for event in phase_events]
        assert kinds.index("approval_requested") < kinds.index("approval_accepted")
        assert kinds.index("approval_accepted") < kinds.index("work_order_approved")
        assert kinds.index("work_order_queued") < kinds.index("run_observed")
        assert [
            event.run_status.value for event in phase_events if event.run_status
        ] == ["assigned", "running", "succeeded"]
        assert kinds[-2:] == ["evidence_verification_started", "evidence_verified"]
    assert [event.event for event in events[-3:]] == [
        "shutdown_started",
        "cleanup_verified",
        "completed",
    ]
    encoded = json.dumps([event.as_dict() for event in events])
    for prohibited in (
        str(tmp_path),
        "synthetic-process-value",
        "operator-test-worker",
        "Nobodyworld",
        "argv",
        "environment",
    ):
        assert prohibited not in encoded
    assert len(encoded.encode()) < progress.MAX_PROGRESS_EVENTS * 256


@pytest.mark.parametrize("phase", ["fresh", "reuse"])
def test_denial_progress_never_grants_or_submits_unapproved_reuse(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, phase: str
) -> None:
    case = _scenario(tmp_path, monkeypatch, "fresh-then-exact-reuse")
    events: list[ProgressEvent] = []
    with pytest.raises(OperatorLifecycleFailure, match=f"{phase}_approval_denied"):
        lifecycle.run_validation_lifecycle(
            case.config,
            approval=lambda current, _identity: current != phase,
            observer=events.append,
        )
    assert case.client.orders == ["fresh"]
    phase_events = [event.event for event in events if event.phase == phase]
    assert phase_events[-2:] == ["approval_requested", "approval_denied"]
    assert "work_order_approved" not in phase_events
    assert "completed" not in [event.event for event in events]
    assert events[-1].event == "failed"
    assert all(process.stopped for process in case.owned)
    stored = lifecycle.inspect_validation_runtime(case.config.runtime_root)
    assert stored.failed_runtime_preserved and stored.outcome == "failed"


@pytest.mark.parametrize(
    "error_type", [OSError, RuntimeError, KeyboardInterrupt, SystemExit]
)
@pytest.mark.parametrize("allow", [True, False])
def test_observer_failure_cannot_change_approval_or_suppress_cleanup(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    error_type: type[BaseException],
    *,
    allow: bool,
) -> None:
    case = _scenario(tmp_path, monkeypatch)
    calls: list[str] = []
    decisions: list[str] = []

    def broken(event: ProgressEvent) -> None:
        calls.append(event.event)
        if event.event == "approval_requested":
            raise error_type("private output details")

    def approval(phase: str, _identity: str) -> bool:
        decisions.append(phase)
        return allow

    if allow:
        report = lifecycle.run_validation_lifecycle(
            case.config, approval=approval, observer=broken
        )
        assert report.outcome == "succeeded"
    else:
        with pytest.raises(OperatorLifecycleFailure, match="fresh_approval_denied"):
            lifecycle.run_validation_lifecycle(
                case.config, approval=approval, observer=broken
            )
    assert decisions == ["fresh"]
    assert calls[-1] == "approval_requested"
    assert all(process.stopped for process in case.owned)
    stored = lifecycle.inspect_validation_runtime(case.config.runtime_root)
    assert stored.fresh_approved is allow
    assert stored.outcome == ("succeeded" if allow else "failed")


@pytest.mark.parametrize("event_kind", ["shutdown_started", "cleanup_verified"])
def test_observer_interrupt_during_shutdown_cannot_bypass_owned_cleanup(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, event_kind: str
) -> None:
    case = _scenario(tmp_path, monkeypatch)
    calls: list[str] = []

    def interrupted(event: ProgressEvent) -> None:
        calls.append(event.event)
        if event.event == event_kind:
            raise KeyboardInterrupt

    report = lifecycle.run_validation_lifecycle(
        case.config, approval=lambda *_args: True, observer=interrupted
    )
    assert calls[-1] == event_kind
    assert all(process.stopped for process in case.owned)
    assert report.owned_processes_stopped and report.port_released
    assert lifecycle.inspect_validation_runtime(case.config.runtime_root).as_dict() == (
        report.as_dict()
    )


def test_broken_reuse_progress_still_requires_the_second_approval(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    case = _scenario(tmp_path, monkeypatch, "fresh-then-exact-reuse")
    decisions: list[str] = []

    def interrupted(event: ProgressEvent) -> None:
        if event.event == "approval_requested" and event.phase == "reuse":
            raise KeyboardInterrupt

    def approval(phase: str, _identity: str) -> bool:
        decisions.append(phase)
        return phase == "fresh"

    with pytest.raises(OperatorLifecycleFailure, match="reuse_approval_denied"):
        lifecycle.run_validation_lifecycle(
            case.config, approval=approval, observer=interrupted
        )
    assert decisions == ["fresh", "reuse"]
    assert case.client.orders == ["fresh"]
    assert all(process.stopped for process in case.owned)


@pytest.mark.parametrize(
    ("field", "value"), [("work_order_id", 99), ("worker_id", "other-worker")]
)
def test_foreign_run_identity_is_not_reported_as_observed_progress(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, field: str, value: object
) -> None:
    case = _scenario(tmp_path, monkeypatch)
    payload = {**_run_payload(1, "running"), field: value}
    monkeypatch.setattr(case.client, "list_runs", lambda _order_id: [payload])
    events: list[ProgressEvent] = []
    with pytest.raises(OperatorLifecycleFailure, match="run_identity_mismatch"):
        lifecycle.run_validation_lifecycle(
            case.config, approval=lambda *_args: True, observer=events.append
        )
    assert "run_observed" not in [event.event for event in events]
    assert all(process.stopped for process in case.owned)


def test_queued_order_does_not_fabricate_running_or_evidence_progress(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    case = _scenario(tmp_path, monkeypatch)
    case.client.states = [""]
    ticks = iter([0.0, 1.0, case.config.terminal_timeout_seconds + 1.0])
    monkeypatch.setattr(lifecycle.time, "monotonic", lambda: next(ticks))
    events: list[ProgressEvent] = []
    with pytest.raises(OperatorLifecycleFailure, match="run_terminal_timeout"):
        lifecycle.run_validation_lifecycle(
            case.config, approval=lambda *_args: True, observer=events.append
        )
    kinds = [event.event for event in events]
    assert "work_order_queued" in kinds
    assert "run_observed" not in kinds
    assert "evidence_verified" not in kinds
    assert "completed" not in kinds
    assert all(process.stopped for process in case.owned)


@pytest.mark.parametrize("reason", ["report", "evidence", "cleanup"])
def test_failed_proof_cannot_emit_verified_completion(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, reason: str
) -> None:
    case = _scenario(tmp_path, monkeypatch)
    events: list[ProgressEvent] = []

    def fail(*_args: object, **_kwargs: object) -> None:
        raise OperatorLifecycleFailure("synthetic_verification_failure")

    if reason == "report":
        monkeypatch.setattr(lifecycle, "write_report", fail)
    elif reason == "evidence":
        monkeypatch.setattr(lifecycle, "_verify_run", fail)
    else:
        monkeypatch.setattr(lifecycle, "port_is_released", lambda *_args: False)
    with pytest.raises(OperatorLifecycleFailure):
        lifecycle.run_validation_lifecycle(
            case.config, approval=lambda *_args: True, observer=events.append
        )
    kinds = [event.event for event in events]
    assert "completed" not in kinds
    assert kinds[-1] == "failed"
    assert all(process.stopped for process in case.owned)
    if reason == "evidence":
        assert "evidence_verified" not in kinds
    if reason == "cleanup":
        assert "cleanup_verified" not in kinds


def test_preflight_failure_emits_no_creation_or_completion(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    case = _scenario(tmp_path, monkeypatch)
    events: list[ProgressEvent] = []

    def fail(_config: object) -> None:
        raise OperatorLifecycleFailure("source_checkout_dirty")

    monkeypatch.setattr(lifecycle, "run_preflight", fail)
    with pytest.raises(OperatorLifecycleFailure, match="source_checkout_dirty"):
        lifecycle.run_validation_lifecycle(
            case.config, approval=lambda *_args: True, observer=events.append
        )
    assert [event.event for event in events] == ["preflight_started", "failed"]
    assert not case.config.runtime_root.exists()


def test_progress_deduplicates_caps_and_rejects_unreviewed_values(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    events: list[ProgressEvent] = []
    publisher = ProgressPublisher(events.append)
    monkeypatch.setattr(progress, "MAX_PROGRESS_EVENTS", 3)
    for _ in range(100):
        publisher.emit("preflight_started")
        publisher.emit("preflight_passed")
        publisher.emit("runtime_created")
        publisher.emit("server_started")
    assert len(events) == 3
    with pytest.raises(ValueError, match="progress_event_invalid"):
        replace(events[0], event="unreviewed-private-text")
    with pytest.raises(ValueError, match="progress_event_invalid"):
        replace(events[0], sequence=True)
    with pytest.raises(ValueError, match="progress_event_invalid"):
        replace(events[0], phase="fresh")
    with pytest.raises(ValueError, match="progress_event_invalid"):
        ProgressEvent(1, "run_observed", "fresh", "unreviewed-private-text")
    assert (
        ProgressEvent(1, "run_observed", "fresh", ExecutionRunStatus.RUNNING).as_dict()[
            "run_status"
        ]
        == "running"
    )
