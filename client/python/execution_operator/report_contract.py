"""Strict serialized report shape and recorded lifecycle consistency.

This validates recorded facts, not the current processes, source, or artifacts.
Historical reports are never rewritten or upgraded by these checks.
"""

from __future__ import annotations

import datetime as dt
import re
from typing import Any

PREFLIGHT_CHECKS = (
    "canonical_repository",
    "clean_source",
    "target_commit",
    "source_snapshot",
    "manifest_contract",
    "python_runtime",
    "git_runtime",
    "worker_capabilities",
    "root_safety",
    "loopback_port",
    "process_token",
    "report_policy",
)
_FRESH_PHASES = (
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
)
_REUSE_PHASES = (
    "reuse_approval_required",
    "reuse_created",
    "reuse_approved",
    "reuse_queued",
    "reuse_succeeded",
    "reuse_verified",
)
_SHUTDOWN_PHASES = ("shutdown_started", "cleanup_verified", "completed")
LIFECYCLE_PHASES = (*_FRESH_PHASES, *_REUSE_PHASES, *_SHUTDOWN_PHASES)
_REPORT_VERSION = 2
_MAX_RUNS = 2
_MAX_ITEMS = 128
_TIMESTAMP = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?Z$")
_REASON = re.compile(r"^[a-z0-9][a-z0-9_.:-]{0,127}$")
_REPORT_FLAGS = (
    "preflight_passed",
    "server_ready",
    "worker_ready",
    "fresh_approved",
    "reuse_approved",
    "owned_processes_stopped",
    "port_released",
    "canonical_checkout_unchanged",
    "failed_runtime_preserved",
)
_RUN_FLAGS = (
    "route_verified",
    "evidence_verified",
    "local_evidence_verified",
    "source_checkout_unchanged",
)
_REPORT_SHAPE: dict[str, tuple[type[object], ...]] = {
    **dict.fromkeys(_REPORT_FLAGS, (bool,)),
    "schema_version": (int,),
    "outcome": (str,),
    "reason": (str,),
    "runtime": (dict, type(None)),
    "phases": (list,),
    "preflight_checks": (list,),
    "runs": (list,),
    "active_lease_count": (int, type(None)),
    "worker_active_run_count": (int, type(None)),
    "operator_action_count": (int,),
    "avoided_deterministic_step_count": (int,),
    "completed_at": (str, type(None)),
}
REPORT_FIELDS = frozenset(_REPORT_SHAPE)
_RUNTIME_SHAPE: dict[str, tuple[type[object], ...]] = {
    "schema_version": (int,),
    **dict.fromkeys(
        (
            "runtime_id",
            "repository_full_name",
            "target_sha",
            "manifest_name",
            "manifest_version",
            "manifest_digest",
            "mode",
            "command_identity",
            "created_at",
        ),
        (str,),
    ),
}
_RUN_SHAPE: dict[str, tuple[type[object], ...]] = {
    **dict.fromkeys(_RUN_FLAGS, (bool,)),
    **dict.fromkeys(
        (
            "schema_version",
            "work_order_id",
            "run_id",
            "source_run_id",
            "required_quota_units",
            "reserved_quota_units",
            "eligible_candidate_count",
            "step_count",
            "artifact_count",
            "artifact_total_bytes",
        ),
        (int,),
    ),
    **dict.fromkeys(
        (
            "phase",
            "worker_id",
            "status",
            "reuse_decision",
            "reuse_identity_hash",
            "evidence_fingerprint",
            "evidence_retention_expires_at",
            "routing_policy",
            "route_reason",
            "quota_reservation_state",
        ),
        (str,),
    ),
    "reused_from_run_id": (int, type(None)),
    "steps": (list,),
    "artifacts": (list,),
}


class ReportContractError(ValueError):
    """A report has invalid types or contradicts its recorded lifecycle."""


def _require(condition: bool) -> None:
    if not condition:
        raise ReportContractError("report_contract_invalid")


def _shape(
    value: object, fields: dict[str, tuple[type[object], ...]]
) -> dict[str, Any]:
    _require(isinstance(value, dict))
    assert isinstance(value, dict)
    _require(set(value) == set(fields))
    for name, types in fields.items():
        _require(type(value[name]) in types)
    return value


def _collection(value: list[Any]) -> None:
    _require(len(value) <= _MAX_ITEMS)


def validate_report_shape(payload: object) -> None:
    """Reject coercions, missing/unknown fields, and malformed nested records."""

    report = _shape(payload, _REPORT_SHAPE)
    for name in ("phases", "preflight_checks"):
        _collection(report[name])
        _require(all(type(item) is str for item in report[name]))
    _require(len(report["runs"]) <= _MAX_RUNS)
    if report["runtime"] is not None:
        _shape(report["runtime"], _RUNTIME_SHAPE)
    for value in report["runs"]:
        run = _shape(value, _RUN_SHAPE)
        _collection(run["steps"])
        _collection(run["artifacts"])
        for step in run["steps"]:
            _shape(
                step,
                {
                    "step_id": (str,),
                    "status": (str,),
                    "duration_seconds": (int, float),
                },
            )
        for artifact in run["artifacts"]:
            _shape(
                artifact,
                {
                    "kind": (str,),
                    "relative_path": (str,),
                    "size_bytes": (int,),
                    "sha256": (str,),
                },
            )


def _timestamp(value: str) -> dt.datetime:
    _require(_TIMESTAMP.fullmatch(value) is not None)
    try:
        return dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise ReportContractError("report_contract_invalid") from error


def success_phases(mode: str) -> tuple[str, ...]:
    _require(mode in {"fresh-only", "fresh-then-exact-reuse"})
    reuse = _REUSE_PHASES if mode == "fresh-then-exact-reuse" else ()
    return (*_FRESH_PHASES, *reuse, *_SHUTDOWN_PHASES)


def _validate_runs(report: dict[str, Any]) -> None:
    runs = report["runs"]
    phases = report["phases"]
    if not runs:
        _require(report["avoided_deterministic_step_count"] == 0)
        return
    _require(report["runtime"] is not None and report["fresh_approved"])
    _require(runs[0]["phase"] == "fresh" and "fresh_verified" in phases)
    _require(runs[0]["step_count"] > 0)
    for run in runs:
        _require(len({item["step_id"] for item in run["steps"]}) == len(run["steps"]))
        _require(
            len({item["relative_path"] for item in run["artifacts"]})
            == len(run["artifacts"])
        )
    if len(runs) == 1:
        _require(report["avoided_deterministic_step_count"] == 0)
        return
    fresh, reuse = runs
    _require(report["runtime"]["mode"] == "fresh-then-exact-reuse")
    _require(report["reuse_approved"] and "reuse_verified" in phases)
    _require(reuse["phase"] == "reuse")
    _require(reuse["run_id"] != fresh["run_id"])
    _require(reuse["work_order_id"] != fresh["work_order_id"])
    _require(reuse["source_run_id"] == reuse["reused_from_run_id"] == fresh["run_id"])
    for name in ("worker_id", "reuse_identity_hash", "evidence_retention_expires_at"):
        _require(fresh[name] == reuse[name])
    _require(reuse["step_count"] == reuse["artifact_count"] == 0)
    _require(report["avoided_deterministic_step_count"] == fresh["step_count"])


def _validate_success(report: dict[str, Any]) -> None:
    runtime = report["runtime"]
    _require(runtime is not None)
    _require(tuple(report["phases"]) == success_phases(runtime["mode"]))
    reuse = runtime["mode"] == "fresh-then-exact-reuse"
    _require(len(report["runs"]) == 1 + int(reuse))
    _require(report["reason"] == "lifecycle_verified")
    _require(report["completed_at"] is not None)
    _require(
        report["preflight_passed"] and report["server_ready"] and report["worker_ready"]
    )
    _require(report["fresh_approved"] and report["reuse_approved"] == reuse)
    _require(report["operator_action_count"] == 1 + int(reuse))
    _require(report["active_lease_count"] == report["worker_active_run_count"] == 0)
    _require(not report["failed_runtime_preserved"])
    completed = _timestamp(report["completed_at"])
    for run in report["runs"]:
        _require(_timestamp(run["evidence_retention_expires_at"]) > completed)


def validate_report_state(report: dict[str, Any]) -> None:
    """Require coherent partial failures and complete proof for success."""

    _require(report["schema_version"] == _REPORT_VERSION)
    _require(report["outcome"] in {"succeeded", "failed", "inspected"})
    _require(_REASON.fullmatch(report["reason"]) is not None)
    phases = report["phases"]
    _require(all(phase in LIFECYCLE_PHASES for phase in phases))
    positions = [LIFECYCLE_PHASES.index(phase) for phase in phases]
    _require(positions == sorted(set(positions)))
    for name in (
        "active_lease_count",
        "worker_active_run_count",
        "operator_action_count",
        "avoided_deterministic_step_count",
    ):
        _require(report[name] is None or report[name] >= 0)
    for field, phase in (
        ("preflight_passed", "preflight_passed"),
        ("server_ready", "server_healthy"),
        ("worker_ready", "worker_online"),
        ("fresh_approved", "fresh_approved"),
        ("reuse_approved", "reuse_approved"),
    ):
        _require(report[field] == (phase in phases))
    checks = PREFLIGHT_CHECKS if report["preflight_passed"] else ()
    _require(tuple(report["preflight_checks"]) == checks)
    approved = int(report["fresh_approved"]) + int(report["reuse_approved"])
    _require(
        approved <= report["operator_action_count"] <= min(approved + 1, _MAX_RUNS)
    )
    _require(not report["reuse_approved"] or report["fresh_approved"])
    runtime = report["runtime"]
    if runtime is not None:
        created = _timestamp(runtime["created_at"])
        allowed = success_phases(runtime["mode"])
        _require(all(phase in allowed for phase in phases))
        if report["completed_at"] is not None:
            _require(_timestamp(report["completed_at"]) >= created)
        if runtime["mode"] == "fresh-only":
            _require(
                not report["reuse_approved"] and report["operator_action_count"] <= 1
            )
    else:
        _require(not phases and not report["runs"] and report["completed_at"] is None)
    if "cleanup_verified" in phases:
        _require(
            report["owned_processes_stopped"]
            and report["port_released"]
            and report["canonical_checkout_unchanged"]
        )
    _validate_runs(report)
    if report["outcome"] == "succeeded":
        _validate_success(report)
    else:
        _require("completed" not in phases and report["reason"] != "lifecycle_verified")
        if report["completed_at"] is not None:
            _require(
                "shutdown_started" in phases and report["failed_runtime_preserved"]
            )
        if report["outcome"] == "inspected":
            _require(
                not phases and not report["runs"] and report["completed_at"] is None
            )
