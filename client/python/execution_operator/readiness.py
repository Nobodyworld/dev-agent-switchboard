"""Bounded public readiness facts, never execution approval or retained proof."""

from __future__ import annotations

import dataclasses
import json
import math
from dataclasses import dataclass
from typing import Any

from .config import OperatorLifecycleConfig
from .models import OperatorLifecycleFailure
from .preflight import (
    PREFLIGHT_FAILURE_REASONS,
    READINESS_CHECKS,
    PreflightCheck,
    assess_preflight,
    safe_readiness_identity,
)

_MAXIMUM_BYTES = 16 * 1024
_MAXIMUM_TIMEOUT_SECONDS = 86400


def _safe_number(value: object) -> int | float | None:
    if (
        not isinstance(value, (int, float))
        or isinstance(value, bool)
        or not 1 <= value <= _MAXIMUM_TIMEOUT_SECONDS
        or not math.isfinite(value)
    ):
        return None
    return value


@dataclass(frozen=True, slots=True)
class ReadinessIdentity:
    repository_full_name: str | None = None
    target_sha: str | None = None
    manifest_name: str | None = None
    manifest_version: str | None = None
    expected_manifest_digest: str | None = None
    verified_manifest_digest: str | None = None
    mode: str | None = None
    worker_id: str | None = None


@dataclass(frozen=True, slots=True)
class ReadinessTimeouts:
    configured_worker_seconds: int | None = None
    configured_terminal_seconds: int | float | None = None
    required_manifest_seconds: int | None = None
    required_maximum_step_seconds: int | None = None


@dataclass(frozen=True, slots=True)
class ValidationReadinessResult:
    """One point-in-time observation; execution always reruns the checks."""

    ready: bool
    reason: str
    checks: tuple[PreflightCheck, ...]
    identity: ReadinessIdentity
    timeouts: ReadinessTimeouts

    def as_dict(self) -> dict[str, Any]:
        self._validate()
        return {
            "schema_version": 1,
            "kind": "validation_readiness",
            "ready": self.ready,
            "reason": self.reason,
            "point_in_time_only": True,
            "approval_granted": False,
            "checks": [
                {
                    "name": item.name,
                    "checked": item.status != "not_checked",
                    "status": item.status,
                    "reason": item.reason,
                }
                for item in self.checks
            ],
            "identity": dataclasses.asdict(self.identity),
            "timeouts": dataclasses.asdict(self.timeouts),
        }

    def as_json_bytes(self, *, maximum_bytes: int = _MAXIMUM_BYTES) -> bytes:
        encoded = json.dumps(
            self.as_dict(), sort_keys=True, separators=(",", ":"), ensure_ascii=True
        ).encode("utf-8")
        return _bounded(encoded, maximum_bytes)

    def as_text(self, *, maximum_bytes: int = _MAXIMUM_BYTES) -> bytes:
        payload = self.as_dict()
        lines = [
            "Switchboard validation readiness",
            f"ready: {self.ready}",
            f"reason: {self.reason}",
            "point-in-time observation only; execution reruns all checks",
            "approval: not granted",
        ]
        lines.extend(
            f"{item.name}: {item.status}"
            + (f" ({item.reason})" if item.reason is not None else "")
            for item in self.checks
        )
        for group in ("identity", "timeouts"):
            lines.extend(
                f"{key}: {value}"
                for key, value in payload[group].items()
                if value is not None
            )
        return _bounded(("\n".join(lines) + "\n").encode("utf-8"), maximum_bytes)

    def _validate(self) -> None:
        if (
            type(self.ready) is not bool
            or not isinstance(self.reason, str)
            or self.reason not in PREFLIGHT_FAILURE_REASONS | {"ready"}
            or not isinstance(self.identity, ReadinessIdentity)
            or not isinstance(self.timeouts, ReadinessTimeouts)
            or not isinstance(self.checks, tuple)
            or len(self.checks) != len(READINESS_CHECKS)
        ):
            raise OperatorLifecycleFailure("readiness_report_invalid")
        failed = False
        for expected, item in zip(READINESS_CHECKS, self.checks, strict=True):
            if not isinstance(item, PreflightCheck) or item.name != expected:
                raise OperatorLifecycleFailure("readiness_report_invalid")
            if failed:
                valid = item.status == "not_checked" and item.reason is None
            elif item.status == "fail":
                valid = item.reason == self.reason and self.reason != "ready"
                failed = True
            else:
                valid = item.status == "pass" and item.reason is None
            if not valid:
                raise OperatorLifecycleFailure("readiness_report_invalid")
        if self.ready != (not failed) or self.ready != (self.reason == "ready"):
            raise OperatorLifecycleFailure("readiness_report_invalid")
        _validate_identity(self.identity)
        _validate_timeouts(self.timeouts)
        if self.ready and (
            any(
                value is None
                for field, value in dataclasses.asdict(self.identity).items()
                if field != "expected_manifest_digest"
            )
            or any(
                value is None for value in dataclasses.asdict(self.timeouts).values()
            )
        ):
            raise OperatorLifecycleFailure("readiness_report_invalid")
        if self.ready:
            _validate_ready_facts(self.identity, self.timeouts)


def _validate_timeouts(timeouts: ReadinessTimeouts) -> None:
    for name, value in dataclasses.asdict(timeouts).items():
        if value is not None and (
            _safe_number(value) is None
            or (name != "configured_terminal_seconds" and type(value) is not int)
        ):
            raise OperatorLifecycleFailure("readiness_report_invalid")


def _validate_ready_facts(
    identity: ReadinessIdentity, timeouts: ReadinessTimeouts
) -> None:
    worker = timeouts.configured_worker_seconds
    terminal = timeouts.configured_terminal_seconds
    manifest = timeouts.required_manifest_seconds
    step = timeouts.required_maximum_step_seconds
    if (
        worker is None
        or terminal is None
        or manifest is None
        or step is None
        or worker < max(manifest, step)
        or terminal < manifest
        or (
            identity.expected_manifest_digest is not None
            and identity.expected_manifest_digest != identity.verified_manifest_digest
        )
    ):
        raise OperatorLifecycleFailure("readiness_report_invalid")


def _validate_identity(identity: ReadinessIdentity) -> None:
    for field, value in dataclasses.asdict(identity).items():
        if field == "mode":
            continue
        if value is not None and safe_readiness_identity(field, value) != value:
            raise OperatorLifecycleFailure("readiness_report_invalid")
    if identity.mode not in {None, "fresh-only", "fresh-then-exact-reuse"}:
        raise OperatorLifecycleFailure("readiness_report_invalid")


def _bounded(encoded: bytes, maximum_bytes: int) -> bytes:
    if type(maximum_bytes) is not int or len(encoded) > min(
        maximum_bytes, _MAXIMUM_BYTES
    ):
        raise OperatorLifecycleFailure("readiness_report_size_limit_exceeded")
    return encoded


def configuration_readiness_failure(
    _reason: str = "invalid_configuration",
) -> ValidationReadinessResult:
    """Do not carry configuration parser messages or source values into output."""

    return ValidationReadinessResult(
        ready=False,
        reason="invalid_configuration",
        checks=(
            PreflightCheck("configuration", "fail", "invalid_configuration"),
            *(PreflightCheck(name, "not_checked") for name in READINESS_CHECKS[1:]),
        ),
        identity=ReadinessIdentity(),
        timeouts=ReadinessTimeouts(),
    )


def inspect_validation_readiness(
    config: OperatorLifecycleConfig,
) -> ValidationReadinessResult:
    """Read the execution checks without creating or reserving runtime state."""

    assessment = assess_preflight(config)
    if assessment.reason == "invalid_configuration":
        return configuration_readiness_failure()
    result = assessment.result
    return ValidationReadinessResult(
        ready=result is not None,
        reason=assessment.reason,
        checks=assessment.checks,
        identity=ReadinessIdentity(
            repository_full_name=safe_readiness_identity(
                "repository_full_name", config.repository_full_name
            ),
            target_sha=safe_readiness_identity("target_sha", config.target_sha),
            manifest_name=safe_readiness_identity(
                "manifest_name", config.manifest_name
            ),
            manifest_version=safe_readiness_identity(
                "manifest_version", config.manifest_version
            ),
            expected_manifest_digest=safe_readiness_identity(
                "expected_manifest_digest", config.expected_manifest_digest
            ),
            verified_manifest_digest=result.manifest_digest if result else None,
            mode=config.mode,
            worker_id=safe_readiness_identity("worker_id", config.worker_id),
        ),
        timeouts=ReadinessTimeouts(
            configured_worker_seconds=config.work_order_timeout_seconds,
            configured_terminal_seconds=_safe_number(config.terminal_timeout_seconds),
            required_manifest_seconds=assessment.manifest_timeout_seconds,
            required_maximum_step_seconds=assessment.maximum_step_timeout_seconds,
        ),
    )


__all__ = [
    "ReadinessIdentity",
    "ReadinessTimeouts",
    "ValidationReadinessResult",
    "configuration_readiness_failure",
    "inspect_validation_readiness",
]
