"""Strict compact evidence contracts and deterministic fingerprinting."""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import re
from collections.abc import Mapping
from pathlib import PurePosixPath
from typing import Any, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from .text_policy import validate_no_absolute_local_paths

ParserKind = Literal[
    "pytest",
    "coverage",
    "pytest-coverage",
    "security-audit",
    "dependency-audit",
]
TerminalStatus = Literal["succeeded", "failed", "timed_out", "cancelled"]
RedactionState = Literal["none", "redacted"]

EVIDENCE_SCHEMA_VERSION = 1
ARTIFACT_SCHEMA_VERSION = 1
REUSE_IDENTITY_SCHEMA_VERSION = 1
REUSE_POLICY_VERSION = 1
MAX_EVIDENCE_STEPS = 64
MAX_EVIDENCE_ARTIFACTS = 128
MAX_EVIDENCE_PATH_LENGTH = 512
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_COMMIT_SHA = re.compile(r"^[0-9a-f]{40}$")
_IDENTIFIER = re.compile(r"^[a-z0-9][a-z0-9_.-]*$")
_REPOSITORY = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
_WINDOWS_DEVICES = {
    "aux",
    "clock$",
    "con",
    "nul",
    "prn",
    *(f"com{number}" for number in range(1, 10)),
    *(f"lpt{number}" for number in range(1, 10)),
}


class EvidenceModel(BaseModel):
    """Deny unknown fields and non-finite numbers in all evidence records."""

    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)

    @model_validator(mode="before")
    @classmethod
    def reject_absolute_local_paths(cls, value: object) -> object:
        """Reject local path disclosure anywhere in compact evidence text."""

        return validate_no_absolute_local_paths(value)


def validate_relative_path(value: str) -> str:
    """Return one normalized safe POSIX path or reject traversal/escaping forms."""

    if (
        not value
        or len(value) > MAX_EVIDENCE_PATH_LENGTH
        or "\x00" in value
        or "\\" in value
    ):
        raise ValueError("evidence path must be a bounded relative POSIX path")
    if ":" in value or value.startswith(("/", "//")):
        raise ValueError("evidence path must not be absolute or device-shaped")
    path = PurePosixPath(value)
    if path.is_absolute() or path.as_posix() != value:
        raise ValueError("evidence path must be normalized")
    if any(part in {"", ".", ".."} for part in path.parts):
        raise ValueError("evidence path must not traverse")
    if any(part.rstrip(". ").lower() in _WINDOWS_DEVICES for part in path.parts):
        raise ValueError("evidence path must not name a device")
    return value


def _aware_utc(value: dt.datetime) -> dt.datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("evidence timestamps must be timezone-aware")
    return value.astimezone(dt.UTC)


class ToolIdentity(EvidenceModel):
    """Bounded executable/tool identity without a local executable path."""

    name: str = Field(min_length=1, max_length=64, pattern=r"^[A-Za-z0-9_.+-]+$")
    version: str = Field(min_length=1, max_length=128)


class EnvironmentIdentity(EvidenceModel):
    """Safe worker environment identity used by compact evidence."""

    schema_version: Literal[1] = 1
    operating_system: str = Field(min_length=1, max_length=64)
    architecture: str = Field(min_length=1, max_length=64)
    python_version: str = Field(min_length=1, max_length=64)
    tools: list[ToolIdentity] = Field(default_factory=list, max_length=32)
    fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")


class ParsedTestCounts(EvidenceModel):
    """Normalized bounded test result counts."""

    passed: int = Field(default=0, ge=0, le=10_000_000)
    failed: int = Field(default=0, ge=0, le=10_000_000)
    skipped: int = Field(default=0, ge=0, le=10_000_000)
    errors: int = Field(default=0, ge=0, le=10_000_000)
    xfailed: int = Field(default=0, ge=0, le=10_000_000)
    xpassed: int = Field(default=0, ge=0, le=10_000_000)
    total: int = Field(ge=0, le=10_000_000)

    @model_validator(mode="after")
    def validate_total(self) -> Self:
        expected = (
            self.passed
            + self.failed
            + self.skipped
            + self.errors
            + self.xfailed
            + self.xpassed
        )
        if self.total != expected:
            raise ValueError("test total must equal normalized result counts")
        return self


class ParsedCoverage(EvidenceModel):
    """Measured coverage information parsed from trusted tool output."""

    measured_percent: float = Field(ge=0, le=100)
    covered_lines: int | None = Field(default=None, ge=0, le=1_000_000_000)
    total_lines: int | None = Field(default=None, ge=0, le=1_000_000_000)

    @model_validator(mode="after")
    def validate_line_pair(self) -> Self:
        if (self.covered_lines is None) != (self.total_lines is None):
            raise ValueError("coverage line counts must be supplied together")
        if (
            self.covered_lines is not None
            and self.total_lines is not None
            and self.covered_lines > self.total_lines
        ):
            raise ValueError("covered lines must not exceed total lines")
        return self


class AuditSummary(EvidenceModel):
    """Normalized security or dependency-audit result."""

    kind: Literal["security", "dependency"]
    status: Literal["passed", "failed"]
    tool: str = Field(min_length=1, max_length=64, pattern=r"^[A-Za-z0-9_.+-]+$")
    findings: int = Field(ge=0, le=10_000_000)


class ParsedResult(EvidenceModel):
    """Truthful parser outcome selected only by a trusted manifest step."""

    schema_version: Literal[1] = 1
    parser: ParserKind
    status: Literal["parsed", "parser_failed"]
    tests: ParsedTestCounts | None = None
    coverage: ParsedCoverage | None = None
    audit: AuditSummary | None = None
    failure_reason: str | None = Field(default=None, max_length=256)

    @model_validator(mode="after")
    def validate_shape(self) -> Self:
        values = (self.tests, self.coverage, self.audit)
        if self.status == "parser_failed":
            if any(value is not None for value in values) or not self.failure_reason:
                raise ValueError("parser failure must not fabricate parsed results")
            return self
        if self.failure_reason is not None or not any(
            value is not None for value in values
        ):
            raise ValueError("parsed result must contain declared structured data")
        if self.parser == "pytest" and (self.tests is None or any(values[1:])):
            raise ValueError("pytest parser result shape is invalid")
        if self.parser == "coverage" and (
            self.coverage is None or self.tests is not None or self.audit is not None
        ):
            raise ValueError("coverage parser result shape is invalid")
        if self.parser == "pytest-coverage" and (
            self.tests is None or self.coverage is None or self.audit is not None
        ):
            raise ValueError("pytest-coverage parser result shape is invalid")
        if self.parser in {"security-audit", "dependency-audit"} and (
            self.audit is None or self.tests is not None or self.coverage is not None
        ):
            raise ValueError("audit parser result shape is invalid")
        return self


class ArtifactRecord(EvidenceModel):
    """Verified retained local artifact metadata; bytes remain worker-local."""

    schema_version: Literal[1] = 1
    kind: str = Field(min_length=1, max_length=64, pattern=r"^[a-z0-9][a-z0-9-]*$")
    relative_path: str
    size_bytes: int = Field(ge=0, le=1_099_511_627_776)
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    media_type: str = Field(
        min_length=3,
        max_length=128,
        pattern=r"^[A-Za-z0-9][A-Za-z0-9!#$&^_.+/-]*$",
    )
    retention_expires_at: dt.datetime
    redaction_state: RedactionState
    produced_by_step: str | None = Field(
        default=None, min_length=1, max_length=80, pattern=r"^[a-z0-9][a-z0-9_.-]*$"
    )

    _path = field_validator("relative_path")(validate_relative_path)
    _expiry = field_validator("retention_expires_at")(_aware_utc)


class DependencyLockHash(EvidenceModel):
    """Hash of a trusted manifest-declared dependency-lock input."""

    relative_path: str
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")

    _path = field_validator("relative_path")(validate_relative_path)


class EvidenceReuseIdentity(EvidenceModel):
    """Deterministic result-equivalence identity, excluding run provenance."""

    schema_version: Literal[1] = 1
    policy_version: Literal[1] = 1
    repository_full_name: str = Field(
        min_length=3,
        max_length=255,
        pattern=r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$",
    )
    tested_sha: str = Field(pattern=r"^[0-9a-f]{40}$")
    manifest_name: str = Field(
        min_length=1, max_length=128, pattern=r"^[a-z0-9][a-z0-9-]*$"
    )
    manifest_version: str = Field(min_length=1, max_length=64)
    manifest_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    worker_environment_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    dependency_lock_hashes: list[DependencyLockHash] = Field(
        default_factory=list, max_length=32
    )
    execution_policy_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    result_contract_hash: str = Field(pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def validate_canonical_identity(self) -> Self:
        paths = [item.relative_path for item in self.dependency_lock_hashes]
        if paths != sorted(paths) or len(paths) != len(set(paths)):
            raise ValueError(
                "dependency-lock identities must be unique and canonically sorted"
            )
        owner, name = self.repository_full_name.split("/", maxsplit=1)
        if owner in {".", ".."} or name in {".", ".."}:
            raise ValueError("invalid repository identity")
        return self


class EvidenceReuseProvenance(EvidenceModel):
    """Compact auditable outcome for fresh or locally verified execution."""

    schema_version: Literal[1] = 1
    decision: Literal["fresh", "reused", "unavailable"]
    reason: str = Field(min_length=1, max_length=64, pattern=r"^[a-z0-9][a-z0-9_.:-]*$")
    reuse_identity_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    source_run_id: int | None = Field(default=None, ge=1, le=9_223_372_036_854_775_807)
    source_evidence_fingerprint: str | None = Field(
        default=None, pattern=r"^[0-9a-f]{64}$"
    )

    @model_validator(mode="after")
    def validate_source_pair(self) -> Self:
        has_source = self.source_run_id is not None
        if has_source != (self.source_evidence_fingerprint is not None):
            raise ValueError("reuse source identity must be complete")
        if (self.decision == "reused") != has_source:
            raise ValueError("only reused evidence may contain source provenance")
        return self


class ReuseCandidate(EvidenceModel):
    """Server-derived source metadata safe for worker-local verification."""

    schema_version: Literal[1] = 1
    source_run_id: int = Field(ge=1, le=9_223_372_036_854_775_807)
    expected_source_worker_id: str = Field(min_length=1, max_length=128)
    expected_source_evidence_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    reuse_identity: EvidenceReuseIdentity
    reuse_identity_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    source_created_at: dt.datetime
    retention_expires_at: dt.datetime
    artifacts: list[ArtifactRecord] = Field(
        default_factory=list, max_length=MAX_EVIDENCE_ARTIFACTS
    )

    _created = field_validator("source_created_at")(_aware_utc)
    _retention = field_validator("retention_expires_at")(_aware_utc)

    @model_validator(mode="after")
    def validate_candidate(self) -> Self:
        if self.retention_expires_at <= self.source_created_at:
            raise ValueError("reuse candidate retention must follow creation")
        if self.reuse_identity_hash != compute_reuse_identity_hash(self.reuse_identity):
            raise ValueError("reuse candidate identity hash mismatch")
        if len({item.relative_path for item in self.artifacts}) != len(self.artifacts):
            raise ValueError("reuse candidate artifact paths must be unique")
        if any(
            item.retention_expires_at != self.retention_expires_at
            for item in self.artifacts
        ):
            raise ValueError("reuse candidate artifact retention is inconsistent")
        return self


class StepEvidence(EvidenceModel):
    """Compact identity and outcome for one reviewed validation step."""

    schema_version: Literal[1] = 1
    step_id: str = Field(min_length=1, max_length=80, pattern=r"^[a-z0-9][a-z0-9_.-]*$")
    title: str = Field(min_length=1, max_length=160)
    status: TerminalStatus
    started_at: dt.datetime
    finished_at: dt.datetime
    duration_seconds: float = Field(ge=0, le=86_400)
    exit_code: int | None = Field(default=None, ge=-2_147_483_648, le=2_147_483_647)
    terminal_reason: str | None = Field(default=None, max_length=256)
    summary: str = Field(default="", max_length=4096)
    summary_truncated: bool = False
    log_artifact_paths: list[str] = Field(default_factory=list, max_length=2)
    parsed_result: ParsedResult | None = None

    _started = field_validator("started_at")(_aware_utc)
    _finished = field_validator("finished_at")(_aware_utc)

    @field_validator("log_artifact_paths")
    @classmethod
    def validate_log_paths(cls, value: list[str]) -> list[str]:
        return [validate_relative_path(item) for item in value]

    @model_validator(mode="after")
    def validate_timing(self) -> Self:
        if self.finished_at < self.started_at:
            raise ValueError("step finish must not precede start")
        return self


class ExecutionEvidenceDraft(EvidenceModel):
    """Canonical fingerprint inputs for one complete execution."""

    schema_version: Literal[1] = 1
    work_order_id: int = Field(ge=1, le=9_223_372_036_854_775_807)
    run_id: int = Field(ge=1, le=9_223_372_036_854_775_807)
    repository_full_name: str = Field(min_length=3, max_length=255)
    tested_sha: str = Field(pattern=r"^[0-9a-f]{40}$")
    manifest_name: str = Field(
        min_length=1, max_length=128, pattern=r"^[a-z0-9][a-z0-9-]*$"
    )
    manifest_version: str = Field(min_length=1, max_length=64)
    manifest_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    worker_id: str = Field(min_length=1, max_length=128)
    environment: EnvironmentIdentity
    dependency_lock_hashes: list[DependencyLockHash] = Field(
        default_factory=list, max_length=32
    )
    started_at: dt.datetime
    finished_at: dt.datetime
    duration_seconds: float = Field(ge=0, le=86_400)
    terminal_status: TerminalStatus
    terminal_reason: str | None = Field(default=None, max_length=256)
    failing_step: str | None = Field(
        default=None, min_length=1, max_length=80, pattern=r"^[a-z0-9][a-z0-9_.-]*$"
    )
    steps: list[StepEvidence] = Field(
        default_factory=list, max_length=MAX_EVIDENCE_STEPS
    )
    artifacts: list[ArtifactRecord] = Field(
        default_factory=list, max_length=MAX_EVIDENCE_ARTIFACTS
    )
    dependency_lock_status: str = Field(min_length=1, max_length=64)
    artifact_finalization_status: str = Field(min_length=1, max_length=64)
    source_cleanup_status: str = Field(min_length=1, max_length=64)
    local_record_status: str = Field(min_length=1, max_length=64)
    reuse_provenance: EvidenceReuseProvenance | None = None

    _started = field_validator("started_at")(_aware_utc)
    _finished = field_validator("finished_at")(_aware_utc)

    @field_validator("repository_full_name")
    @classmethod
    def validate_repository(cls, value: str) -> str:
        if not _REPOSITORY.fullmatch(value):
            raise ValueError("invalid repository identity")
        owner, name = value.split("/", maxsplit=1)
        if owner in {".", ".."} or name in {".", ".."}:
            raise ValueError("invalid repository identity")
        return value

    @model_validator(mode="after")
    def validate_document(self) -> Self:
        if self.finished_at < self.started_at:
            raise ValueError("execution finish must not precede start")
        if len({step.step_id for step in self.steps}) != len(self.steps):
            raise ValueError("step evidence identities must be unique")
        if len({item.relative_path for item in self.artifacts}) != len(self.artifacts):
            raise ValueError("artifact paths must be unique")
        artifact_paths = {item.relative_path for item in self.artifacts}
        if any(
            path not in artifact_paths
            for step in self.steps
            for path in step.log_artifact_paths
        ):
            raise ValueError("step log references must resolve to artifact records")
        if self.failing_step is not None and self.failing_step not in {
            step.step_id for step in self.steps
        }:
            raise ValueError("failing step must name recorded step evidence")
        return self


class ExecutionEvidence(ExecutionEvidenceDraft):
    """Validated complete evidence with its canonical SHA-256 fingerprint."""

    fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def validate_fingerprint(self) -> Self:
        if self.fingerprint != compute_evidence_fingerprint(self):
            raise ValueError("evidence fingerprint does not match canonical inputs")
        return self


def canonical_evidence_json(
    evidence: ExecutionEvidenceDraft | ExecutionEvidence,
) -> str:
    """Serialize canonical fingerprint inputs with the fingerprint omitted."""

    payload = evidence.model_dump(mode="json", exclude={"fingerprint"})
    # Preserve validation of evidence created before reuse provenance existed.
    if payload.get("reuse_provenance") is None:
        payload.pop("reuse_provenance", None)
    return json.dumps(
        payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    )


def compute_evidence_fingerprint(
    evidence: ExecutionEvidenceDraft | ExecutionEvidence,
) -> str:
    """Return SHA-256 over UTF-8 canonical evidence JSON."""

    canonical = canonical_evidence_json(evidence)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def finalize_evidence(evidence: ExecutionEvidenceDraft) -> ExecutionEvidence:
    """Insert the canonical fingerprint and validate the complete document again."""

    payload = evidence.model_dump(mode="json")
    payload["fingerprint"] = compute_evidence_fingerprint(evidence)
    return ExecutionEvidence.model_validate(payload)


def canonical_reuse_identity_json(identity: EvidenceReuseIdentity) -> str:
    """Serialize the complete deterministic reuse identity canonically."""

    return json.dumps(
        identity.model_dump(mode="json"),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )


def compute_reuse_identity_hash(identity: EvidenceReuseIdentity) -> str:
    """Return SHA-256 over the canonical deterministic reuse identity."""

    return hashlib.sha256(
        canonical_reuse_identity_json(identity).encode("utf-8")
    ).hexdigest()


def canonical_payload_hash(payload: Mapping[str, Any]) -> str:
    """Hash one server-owned JSON policy payload with stable ordering."""

    validate_no_absolute_local_paths(payload)
    encoded = json.dumps(
        payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    )
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def compute_execution_policy_hash(  # noqa: PLR0913 - identity inputs are explicit
    *,
    manifest_parameters: Mapping[str, Any],
    required_capabilities: Mapping[str, Any],
    permitted_paths: list[str] | tuple[str, ...],
    expected_artifact_kinds: list[str] | tuple[str, ...],
    timeout_seconds: int,
    network_policy: str,
    repository_write_allowed: bool,
) -> str:
    """Hash every caller-visible result-affecting execution policy input."""

    return canonical_payload_hash(
        {
            "expected_artifact_kinds": sorted(expected_artifact_kinds),
            "manifest_parameters": dict(manifest_parameters),
            "network_policy": network_policy,
            "permitted_paths": sorted(permitted_paths),
            "repository_write_allowed": repository_write_allowed,
            "required_capabilities": dict(required_capabilities),
            "schema_version": 1,
            "timeout_seconds": timeout_seconds,
        }
    )


def compute_result_contract_hash(
    *,
    fixed_step_metadata: list[dict[str, Any]],
    artifact_declarations: list[dict[str, Any]],
    dependency_lock_paths: list[str] | tuple[str, ...],
) -> str:
    """Hash parser/artifact/lock declarations independently of run values."""

    normalized_paths = [validate_relative_path(path) for path in dependency_lock_paths]
    return canonical_payload_hash(
        {
            "artifact_declarations": artifact_declarations,
            "dependency_lock_paths": sorted(normalized_paths),
            "fixed_step_metadata": fixed_step_metadata,
            "schema_version": 1,
        }
    )


__all__ = [
    "ARTIFACT_SCHEMA_VERSION",
    "EVIDENCE_SCHEMA_VERSION",
    "REUSE_IDENTITY_SCHEMA_VERSION",
    "REUSE_POLICY_VERSION",
    "ArtifactRecord",
    "AuditSummary",
    "DependencyLockHash",
    "EnvironmentIdentity",
    "EvidenceReuseIdentity",
    "EvidenceReuseProvenance",
    "ExecutionEvidence",
    "ExecutionEvidenceDraft",
    "ParsedCoverage",
    "ParsedResult",
    "ParsedTestCounts",
    "ReuseCandidate",
    "StepEvidence",
    "ToolIdentity",
    "canonical_evidence_json",
    "canonical_payload_hash",
    "canonical_reuse_identity_json",
    "compute_evidence_fingerprint",
    "compute_execution_policy_hash",
    "compute_result_contract_hash",
    "compute_reuse_identity_hash",
    "finalize_evidence",
    "validate_relative_path",
]
