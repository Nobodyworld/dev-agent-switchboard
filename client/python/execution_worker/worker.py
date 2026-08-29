"""Outbound-only single-concurrency worker orchestration."""

from __future__ import annotations

import datetime as dt
import hashlib
import importlib.metadata
import json
import platform
import re
import threading
import time
from collections.abc import Mapping
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any, Literal

from server.execution.capabilities import (
    normalize_runtime_version,
    runtime_version_matches,
)
from server.execution.evidence import (
    ArtifactRecord,
    DependencyLockHash,
    EnvironmentIdentity,
    EvidenceReuseIdentity,
    EvidenceReuseProvenance,
    ExecutionEvidence,
    ExecutionEvidenceDraft,
    StepEvidence,
    TerminalStatus,
    ToolIdentity,
    compute_result_contract_hash,
    compute_reuse_identity_hash,
    finalize_evidence,
)
from server.execution.registry import TrustedManifest, TrustedStep, get_trusted_manifest
from server.execution.text_policy import contains_absolute_local_path

from .capabilities import discover_worker_registration
from .client import ExecutionClient, ExecutionOwnershipLostError
from .config import WorkerConfig
from .containment import ContainmentCleanupError
from .evidence import (
    EvidenceLimits,
    EvidenceStore,
    create_evidence_store,
    hash_declared_file,
    prune_expired_evidence,
    verify_reuse_candidate,
)
from .models import AssignedWorkOrder, Checkout, ExecutionRun, ReuseLookup, SafeManifest
from .runner import (
    CancellationToken,
    OverallDeadlineExceededError,
    StepResult,
    run_step,
)
from .worktree import (
    DisposableWorktree,
    LocalCommitUnavailableError,
    create_worktree,
)

_SERVER_TERMINAL_STATUSES = {"succeeded", "failed", "timed_out", "cancelled"}
RESULT_SUMMARY_LIMIT = 8000
LOCAL_DATABASE_URI_MARKER = "[LOCAL_DATABASE_URI]"
_LOCAL_SQLITE_EXPRESSION = re.compile(
    r"(?i)(?<![A-Za-z0-9+.-])sqlite(?:\+aiosqlite)?:///\{[^{}\r\n]*\}"
)
_LOCAL_SQLITE_URI = re.compile(
    r"(?i)(?<![A-Za-z0-9+.-])sqlite(?:\+aiosqlite)?:///[^\s<>\"']*"
)
STEP_EVIDENCE_SUMMARY_LIMIT = 4096
_ENVIRONMENT_TOOLS = ("ruff", "black", "mypy", "pytest", "coverage", "bandit")
ReuseDecisionValue = Literal["fresh", "reused", "unavailable"]


def _sanitize_remote_text(value: str) -> str:
    """Remove local path/URI shapes while retained evidence stays unchanged."""

    without_expressions = _LOCAL_SQLITE_EXPRESSION.sub(
        LOCAL_DATABASE_URI_MARKER,
        value,
    )
    without_local_databases = _LOCAL_SQLITE_URI.sub(
        LOCAL_DATABASE_URI_MARKER,
        without_expressions,
    )
    normalized = without_local_databases.replace("\\", "[BACKSLASH]")
    return "[LOCAL_PATH]" if contains_absolute_local_path(normalized) else normalized


def _allowed_inherited_environment_keys(manifest: TrustedManifest) -> frozenset[str]:
    """Return only the reviewed inherited environment keys for a manifest.

    Worker configuration narrows what this host is willing to provide; the
    manifest policy narrows what trusted target code is allowed to receive.
    A malformed persisted policy therefore fails closed to an empty set.
    """

    policy_keys = manifest.environment_policy.get("allowed_inherited_keys")
    if not isinstance(policy_keys, list) or not all(
        isinstance(key, str) for key in policy_keys
    ):
        return frozenset()
    return frozenset(policy_keys)


def _step_result_contract(
    manifest: TrustedManifest, step_id: str
) -> Mapping[str, object] | None:
    """Select one closed source-controlled result descriptor or fail closed."""

    contract = manifest.result_contract
    if contract is None:
        return None
    steps = contract.get("steps")
    if not isinstance(steps, list):
        raise ValueError("trusted manifest result contract steps are invalid")
    matches: list[Mapping[str, object]] = []
    for item in steps:
        if not isinstance(item, Mapping) or set(item) != {"id", "result_contract"}:
            raise ValueError("trusted manifest result contract step is invalid")
        if not isinstance(item["id"], str) or not isinstance(
            item["result_contract"], Mapping
        ):
            raise ValueError("trusted manifest result contract step is invalid")
        if item["id"] == step_id:
            matches.append(item["result_contract"])
    if len(matches) > 1:
        raise ValueError("trusted manifest result contract step is ambiguous")
    return matches[0] if matches else None


def _environment_identity(
    config: WorkerConfig,
    *,
    required_capabilities: tuple[Mapping[str, Any], ...],
) -> EnvironmentIdentity:
    """Capture result-affecting runtime versions in the local evidence identity."""

    tools: list[ToolIdentity] = []
    for name in _ENVIRONMENT_TOOLS:
        try:
            version = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            continue
        tools.append(ToolIdentity(name=name, version=version))
    runtime_names = {
        {
            "node_version": "node",
            "pnpm_version": "pnpm",
        }.get(str(name).lower(), str(name).lower())
        for requirements in required_capabilities
        for name in requirements
    }
    if runtime_names.intersection({"node", "pnpm"}):
        registration = discover_worker_registration(config)
        for name, field in (("node", "node_version"), ("pnpm", "pnpm_version")):
            registered_version = registration[field]
            runtime_version = normalize_runtime_version(
                registered_version if isinstance(registered_version, str) else None,
                allow_leading_v=name == "node",
            )
            if name in runtime_names and isinstance(runtime_version, str):
                tools.append(ToolIdentity(name=name, version=runtime_version))
    architecture = platform.machine() or "unknown"
    operating_system = platform.system().lower() or "unknown"
    python_version = platform.python_version()
    fingerprint_payload = {
        "architecture": architecture,
        "operating_system": operating_system,
        "python_version": python_version,
        "tools": [item.model_dump(mode="json") for item in tools],
    }
    encoded = json.dumps(fingerprint_payload, sort_keys=True, separators=(",", ":"))
    return EnvironmentIdentity(
        architecture=architecture,
        operating_system=operating_system,
        python_version=python_version,
        tools=tools,
        fingerprint=hashlib.sha256(encoded.encode("utf-8")).hexdigest(),
    )


def _step_evidence(
    results: list[StepResult], artifacts: list[ArtifactRecord]
) -> list[StepEvidence]:
    artifact_paths = {artifact.relative_path for artifact in artifacts}
    evidence: list[StepEvidence] = []
    for result in results:
        sanitized_summary = _sanitize_remote_text(
            "\n".join(
                item for item in (result.stdout_summary, result.stderr_summary) if item
            )
        )
        summary = sanitized_summary[:STEP_EVIDENCE_SUMMARY_LIMIT]
        paths = [
            f"logs/{result.stdout_log}",
            f"logs/{result.stderr_log}",
        ]
        evidence.append(
            StepEvidence(
                step_id=result.step_id,
                title=result.title,
                status=result.status,
                started_at=result.started_at,
                finished_at=result.finished_at,
                duration_seconds=result.duration_seconds,
                exit_code=result.exit_code,
                terminal_reason=result.terminal_reason,
                summary=summary,
                summary_truncated=(
                    result.summaries_truncated
                    or len(sanitized_summary) > STEP_EVIDENCE_SUMMARY_LIMIT
                ),
                log_artifact_paths=[path for path in paths if path in artifact_paths],
                parsed_result=result.parsed_result,
            )
        )
    return evidence


def _requirement_satisfied(
    actual: object,
    expected: object,
    *,
    capability: str,
) -> bool:
    if capability in {"python", "node", "pnpm"}:
        return runtime_version_matches(
            actual if isinstance(actual, str) else None,
            expected,
            normalize_leading_v=capability == "node",
        )
    if isinstance(expected, bool):
        return actual is expected
    if isinstance(expected, str):
        return actual == expected
    if isinstance(expected, list):
        return isinstance(actual, str) and actual in expected
    return False


def _cancellation_outcome(
    token: CancellationToken,
) -> tuple[TerminalStatus, str, bool]:
    """Return the authoritative terminal state for one cancelled run."""

    reason = token.reason
    if reason == "overall_timeout":
        return "timed_out", reason, False
    skip_completion = reason == "ownership_lost" or reason.startswith(
        "server_terminal:"
    )
    return "cancelled", reason, skip_completion


def _local_capabilities(config: WorkerConfig) -> dict[str, object]:
    registration = discover_worker_registration(config)
    capabilities = dict(registration["capabilities"])
    capabilities.update(
        {
            "operating_system": registration["operating_system"],
            "architecture": registration["architecture"],
            "python": registration["python_version"],
            "node": registration["node_version"],
            "pnpm": registration["pnpm_version"],
            "docker": registration["docker_available"],
            "gpu": registration["gpu_available"],
            "unity": registration["unity_available"],
            "desktop": registration["desktop_available"],
            "browsers": registration["browsers"],
            "repository_write": False,
        }
    )
    return capabilities


def _validate_capabilities(
    requirements: Mapping[str, Any], config: WorkerConfig
) -> None:
    capabilities = _local_capabilities(config)
    aliases = {
        "python_version": "python",
        "node_version": "node",
        "pnpm_version": "pnpm",
        "docker_available": "docker",
        "gpu_available": "gpu",
        "unity_available": "unity",
        "desktop_available": "desktop",
    }
    for name, expected in requirements.items():
        key = aliases.get(name, name)
        if key not in capabilities or not _requirement_satisfied(
            capabilities[key], expected, capability=key
        ):
            raise ValueError(f"unsupported required capability: {name}")


def _validate_manifest(
    *,
    manifest: TrustedManifest | None,
    remote: SafeManifest,
    order: AssignedWorkOrder,
    config: WorkerConfig,
) -> TrustedManifest:
    """Prove the safe remote contract matches one executable local definition."""

    if manifest is None:
        raise ValueError("trusted manifest does not exist locally")
    if not manifest.execution_steps:
        raise ValueError("trusted manifest has no executable steps")
    if (
        manifest.name != order.manifest_name
        or manifest.version != order.manifest_version
        or manifest.digest != order.manifest_digest
        or remote.name != manifest.name
        or remote.version != manifest.version
        or remote.digest != manifest.digest
        or remote.timeout_seconds != manifest.timeout_seconds
        or remote.schema_version != manifest.schema_version
        or remote.description != manifest.description
        or remote.trusted_registry_source != manifest.registry_source
        or remote.network_policy != manifest.network_policy.value
        or remote.repository_write_policy != manifest.repository_write_policy.value
        or dict(remote.required_capabilities) != manifest.required_capabilities
        or [dict(item) for item in remote.fixed_step_metadata]
        != manifest.fixed_step_metadata
        or dict(remote.environment_policy) != manifest.environment_policy
        or [dict(item) for item in remote.artifact_declarations]
        != manifest.artifact_declarations
    ):
        raise ValueError("trusted manifest metadata mismatch")
    if manifest.repository_write_policy.value != "read_only":
        raise ValueError("trusted manifest permits repository writes")
    unsupported_parameters = set(order.manifest_parameters) - set(
        manifest.allowed_parameters
    )
    if unsupported_parameters:
        raise ValueError("work order contains unsupported manifest parameters")
    if order.network_policy != config.network_policy_capability:
        raise ValueError("work order network policy is incompatible with worker")
    if manifest.network_policy.value != config.network_policy_capability:
        raise ValueError("manifest network policy is incompatible with worker")
    if (
        order.timeout_seconds > config.execution_timeout_seconds
        or manifest.timeout_seconds > config.execution_timeout_seconds
    ):
        raise ValueError("execution timeout exceeds local policy")
    for step in manifest.execution_steps:
        if (
            step.timeout_seconds > config.maximum_step_timeout_seconds
            or step.output_summary_limit > config.output_summary_limit
        ):
            raise ValueError("trusted step limit exceeds local policy")
    _validate_capabilities(manifest.required_capabilities, config)
    _validate_capabilities(order.required_capabilities, config)
    return manifest


def _profile_evidence_policy(
    manifest: TrustedManifest,
    config: WorkerConfig,
) -> tuple[int, EvidenceLimits]:
    """Return the stricter of local and reviewed profile evidence ceilings.

    Legacy manifests do not carry a factory result contract, so their evidence
    behavior remains byte-for-byte compatible with the existing local worker
    configuration.  A factory profile's contract is source-controlled and
    digest-bound, but it is still parsed defensively here before it can govern
    retained evidence.
    """

    local_limits = EvidenceLimits(
        maximum_artifact_count=config.maximum_artifact_count,
        maximum_artifact_bytes=config.maximum_artifact_bytes,
        maximum_total_bytes=config.maximum_total_evidence_bytes,
    )
    if manifest.result_contract is None:
        return config.evidence_retention_days, local_limits

    contract = manifest.result_contract
    if set(contract) != {"resource_limits", "schema_version", "steps"}:
        raise ValueError("trusted manifest result contract is invalid")
    resource_limits = contract.get("resource_limits")
    if not isinstance(resource_limits, Mapping) or set(resource_limits) != {
        "maximum_artifact_bytes",
        "maximum_artifact_count",
        "maximum_total_artifact_bytes",
        "retention_days",
    }:
        raise ValueError("trusted manifest resource limits are invalid")

    values: dict[str, int] = {}
    for name, value in resource_limits.items():
        if not isinstance(value, int) or isinstance(value, bool) or value < 1:
            raise ValueError("trusted manifest resource limit is invalid")
        values[name] = value
    if values["maximum_total_artifact_bytes"] < values["maximum_artifact_bytes"]:
        raise ValueError("trusted manifest total evidence limit is invalid")

    return (
        min(config.evidence_retention_days, values["retention_days"]),
        EvidenceLimits(
            maximum_artifact_count=min(
                config.maximum_artifact_count,
                values["maximum_artifact_count"],
            ),
            maximum_artifact_bytes=min(
                config.maximum_artifact_bytes,
                values["maximum_artifact_bytes"],
            ),
            maximum_total_bytes=min(
                config.maximum_total_evidence_bytes,
                values["maximum_total_artifact_bytes"],
            ),
        ),
    )


@dataclass(slots=True)
class _RunMonitor:
    worker: LocalWorker
    run_id: int
    deadline: float
    token: CancellationToken
    _stop: threading.Event = field(default_factory=threading.Event)
    _thread: threading.Thread | None = None

    def tick(self) -> None:
        if time.monotonic() >= self.deadline:
            self.token.cancel("overall_timeout")
            return
        try:
            self.worker.client.heartbeat_worker(status="busy")
        except OSError:
            # Worker liveness is independent from the owned run lease. A single
            # bounded transport failure must not suppress run renewal.
            pass
        try:
            run = ExecutionRun.from_payload(
                self.worker.client.heartbeat_run(self.run_id)
            )
        except ExecutionOwnershipLostError:
            self.token.cancel("ownership_lost")
            return
        except ValueError:
            # Invalid control-plane data must fail closed, including requests'
            # JSONDecodeError, which also inherits from OSError.
            self.token.cancel("invalid_run_heartbeat")
            return
        except OSError:
            # Retry only at the next scheduled monitor tick.
            return
        if run.id != self.run_id:
            self.token.cancel("invalid_run_heartbeat")
            return
        if run.status in _SERVER_TERMINAL_STATUSES:
            self.token.cancel(f"server_terminal:{run.status}")

    def start(self) -> None:
        self.tick()
        if self.token.cancelled:
            return
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def _run(self) -> None:
        while not self._stop.wait(self.worker.config.heartbeat_interval_seconds):
            self.tick()
            if self.token.cancelled:
                return

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=self.worker.config.heartbeat_interval_seconds + 1)


@dataclass(slots=True)
class LocalWorker:
    config: WorkerConfig
    client: ExecutionClient
    _shutdown: threading.Event = field(default_factory=threading.Event, init=False)
    _state_lock: threading.Lock = field(default_factory=threading.Lock, init=False)
    _executed_run_ids: set[int] = field(default_factory=set, init=False)
    _active_run_id: int | None = field(default=None, init=False)
    _active_token: CancellationToken | None = field(default=None, init=False)

    def start(self) -> None:
        prune = prune_expired_evidence(
            self.config.evidence_root,
            worker_id=self.config.worker_id,
            now=dt.datetime.now(dt.UTC),
        )
        if prune.failures:
            raise RuntimeError(f"evidence_retention_failed:{','.join(prune.failures)}")
        self.client.register_worker(discover_worker_registration(self.config))

    @property
    def shutting_down(self) -> bool:
        """Whether the operator has requested draining and no further checkout."""

        return self._shutdown.is_set()

    def request_shutdown(self) -> None:
        """Stop future checkout attempts and signal an active run to drain."""

        self._shutdown.set()
        with self._state_lock:
            if self._active_token is not None:
                self._active_token.cancel("worker_shutdown")

    def _begin_run(self, run_id: int) -> str | None:
        with self._state_lock:
            if self._shutdown.is_set():
                return "worker_shutdown_before_start"
            if self._active_run_id is not None:
                return "local_concurrency_rejected_after_checkout"
            if run_id in self._executed_run_ids:
                return "local_duplicate_execution_rejected_after_checkout"
            self._executed_run_ids.add(run_id)
            self._active_run_id = run_id
            return None

    def _end_run(self, run_id: int) -> None:
        with self._state_lock:
            if self._active_run_id == run_id:
                self._active_run_id = None

    @staticmethod
    def _serialize_summary(summary: Mapping[str, Any]) -> str:
        def normalize(value: Any) -> Any:
            if isinstance(value, str):
                return _sanitize_remote_text(value)
            if isinstance(value, Mapping):
                return {key: normalize(item) for key, item in value.items()}
            if isinstance(value, list):
                return [normalize(item) for item in value]
            return value

        return json.dumps(normalize(summary), ensure_ascii=False, separators=(",", ":"))

    @classmethod
    def _summary(
        cls, order: AssignedWorkOrder, results: list[StepResult]
    ) -> dict[str, Any]:
        """Build one bounded structured summary without slicing serialized JSON."""

        summary: dict[str, Any] = {
            "checked_out_sha": order.commit_sha,
            "steps": [
                {
                    "id": result.step_id,
                    "status": result.status,
                    "exit_code": result.exit_code,
                    "duration_seconds": round(result.duration_seconds, 3),
                    "stdout": result.stdout_summary,
                    "stderr": result.stderr_summary,
                    "truncated": result.summaries_truncated,
                    "logs": [
                        f"logs/{result.stdout_log}",
                        f"logs/{result.stderr_log}",
                    ],
                    "environment": result.environment_summary,
                    "terminal_reason": result.terminal_reason,
                }
                for result in results
            ],
        }
        if len(cls._serialize_summary(summary)) <= RESULT_SUMMARY_LIMIT:
            return summary

        summary["result_summary_truncated"] = True
        steps = summary["steps"]
        assert isinstance(steps, list)
        largest = max(
            (len(str(step[field])) for step in steps for field in ("stdout", "stderr")),
            default=0,
        )

        def compact(limit: int) -> None:
            for step, result in zip(steps, results, strict=True):
                assert isinstance(step, dict)
                stdout = result.stdout_summary
                stderr = result.stderr_summary
                step["stdout"] = stdout[:limit]
                step["stderr"] = stderr[:limit]
                step["truncated"] = (
                    result.summaries_truncated
                    or len(stdout) > limit
                    or len(stderr) > limit
                )

        low, high = 0, largest
        while low < high:
            candidate = (low + high + 1) // 2
            compact(candidate)
            if len(cls._serialize_summary(summary)) <= RESULT_SUMMARY_LIMIT:
                low = candidate
            else:
                high = candidate - 1
        compact(low)
        if len(cls._serialize_summary(summary)) > RESULT_SUMMARY_LIMIT:
            raise RuntimeError("required result metadata exceeds worker summary limit")
        return summary

    def _create_evidence_store(
        self,
        run_id: int,
        created_at: dt.datetime,
        manifest: TrustedManifest,
    ) -> EvidenceStore:
        retention_days, limits = _profile_evidence_policy(manifest, self.config)
        return create_evidence_store(
            evidence_root=self.config.evidence_root,
            worker_root=self.config.worker_root,
            repository_roots=tuple(self.config.repositories.values()),
            worker_id=self.config.worker_id,
            run_id=run_id,
            created_at=created_at,
            retention_days=retention_days,
            limits=limits,
        )

    @staticmethod
    def _hash_dependency_locks(
        manifest: TrustedManifest, checkout: Path
    ) -> list[DependencyLockHash]:
        hashes: list[DependencyLockHash] = []
        for relative_path in sorted(manifest.dependency_lock_paths):
            _size, digest = hash_declared_file(checkout, relative_path)
            hashes.append(
                DependencyLockHash(relative_path=relative_path, sha256=digest)
            )
        return hashes

    def _build_evidence(  # noqa: PLR0913 - canonical evidence inputs are explicit
        self,
        *,
        order: AssignedWorkOrder,
        run_id: int,
        manifest: TrustedManifest,
        started_at: dt.datetime,
        finished_at: dt.datetime,
        terminal: TerminalStatus,
        reason: str | None,
        results: list[StepResult],
        artifacts: list[ArtifactRecord],
        dependency_locks: list[DependencyLockHash],
        dependency_lock_status: str,
        artifact_status: str,
        cleanup: str,
        local_record_status: str,
        environment: EnvironmentIdentity,
        reuse_provenance: EvidenceReuseProvenance,
    ) -> ExecutionEvidence:
        failing_step = next(
            (result.step_id for result in results if result.status != "succeeded"),
            None,
        )
        draft = ExecutionEvidenceDraft(
            work_order_id=order.id,
            run_id=run_id,
            repository_full_name=order.repository_full_name,
            tested_sha=order.commit_sha.lower(),
            manifest_name=manifest.name,
            manifest_version=manifest.version,
            manifest_digest=manifest.digest,
            worker_id=self.config.worker_id,
            environment=environment,
            dependency_lock_hashes=dependency_locks,
            started_at=started_at,
            finished_at=finished_at,
            duration_seconds=max(0.0, (finished_at - started_at).total_seconds()),
            terminal_status=terminal,
            terminal_reason=reason,
            failing_step=failing_step,
            steps=_step_evidence(results, artifacts),
            artifacts=artifacts,
            dependency_lock_status=dependency_lock_status,
            artifact_finalization_status=artifact_status,
            source_cleanup_status=cleanup,
            local_record_status=local_record_status,
            reuse_provenance=reuse_provenance,
        )
        return finalize_evidence(draft)

    @staticmethod
    def _build_reuse_identity(
        *,
        order: AssignedWorkOrder,
        manifest: TrustedManifest,
        environment: EnvironmentIdentity,
        dependency_locks: list[DependencyLockHash],
    ) -> EvidenceReuseIdentity:
        """Build the exact current result identity from trusted local inputs."""

        return EvidenceReuseIdentity(
            repository_full_name=order.repository_full_name,
            tested_sha=order.commit_sha.lower(),
            manifest_name=manifest.name,
            manifest_version=manifest.version,
            manifest_digest=manifest.digest,
            worker_environment_fingerprint=environment.fingerprint,
            dependency_lock_hashes=sorted(
                dependency_locks, key=lambda item: item.relative_path
            ),
            execution_policy_hash=order.execution_policy_hash,
            result_contract_hash=compute_result_contract_hash(
                fixed_step_metadata=manifest.fixed_step_metadata,
                artifact_declarations=manifest.artifact_declarations,
                dependency_lock_paths=manifest.dependency_lock_paths,
                result_contract=manifest.result_contract,
            ),
        )

    def _complete_admission_rejection(self, run_id: int, reason: str) -> None:
        """Dispose one checked-out lease exactly once without local side effects."""

        try:
            self.client.complete_run(
                run_id,
                status="cancelled",
                terminal_reason=reason,
                cleanup_status="not_started",
                result_summary=self._serialize_summary({"steps": []}),
                evidence_metadata=None,
            )
        except ExecutionOwnershipLostError:
            # The lease has already been safely disposed elsewhere.
            pass

    def poll_once(self) -> bool:  # noqa: PLR0912, PLR0915 - lifecycle state machine
        """Checkout and process at most one run; never execute while draining."""

        if self.shutting_down:
            return False
        checkout = Checkout.from_payload(self.client.checkout())
        if checkout.run_id is None:
            return False
        assert checkout.work_order_id is not None
        admission_rejection = self._begin_run(checkout.run_id)
        if admission_rejection is not None:
            self._complete_admission_rejection(checkout.run_id, admission_rejection)
            return True
        worktree: DisposableWorktree | None = None
        store: EvidenceStore | None = None
        monitor: _RunMonitor | None = None
        manifest: TrustedManifest | None = None
        results: list[StepResult] = []
        attempted_steps: list[TrustedStep] = []
        artifacts: list[ArtifactRecord] = []
        dependency_locks: list[DependencyLockHash] = []
        dependency_lock_status = "not_declared"
        artifact_status = "not_started"
        source_quiescent = True
        source_integrity_verified = True
        terminal: TerminalStatus = "failed"
        reason: str | None = "worker_initialization_failed"
        cleanup: str = "not_started"
        skip_completion = False
        order: AssignedWorkOrder | None = None
        summary: dict[str, Any] = {"steps": []}
        evidence: ExecutionEvidence | None = None
        provenance: EvidenceReuseProvenance | None = None
        environment: EnvironmentIdentity | None = None
        reuse_identity: EvidenceReuseIdentity | None = None
        reuse_identity_hash: str | None = None
        reuse_decision: ReuseDecisionValue = "fresh"
        reuse_reason = "reuse_policy_never"
        lookup: ReuseLookup | None = None
        started_at = dt.datetime.now(dt.UTC)
        try:
            order = AssignedWorkOrder.from_payload(
                self.client.get_work_order(checkout.work_order_id)
            )
            manifest = _validate_manifest(
                manifest=get_trusted_manifest(
                    order.manifest_name, order.manifest_version
                ),
                remote=SafeManifest.from_payload(
                    self.client.get_manifest(
                        order.manifest_name, order.manifest_version
                    )
                ),
                order=order,
                config=self.config,
            )
            deadline = time.monotonic() + min(
                float(order.timeout_seconds),
                float(manifest.timeout_seconds),
                self.config.execution_timeout_seconds,
            )
            token = CancellationToken()
            with self._state_lock:
                self._active_token = token
            monitor = _RunMonitor(self, checkout.run_id, deadline, token)
            monitor.start()
            if token.cancelled:
                terminal, reason, skip_completion = _cancellation_outcome(token)
            elif self._shutdown.is_set():
                token.cancel("worker_shutdown")
                terminal, reason = "cancelled", token.reason
            else:
                started_at = dt.datetime.now(dt.UTC)
                environment = _environment_identity(
                    self.config,
                    required_capabilities=(
                        manifest.required_capabilities,
                        order.required_capabilities,
                    ),
                )
                store = self._create_evidence_store(
                    checkout.run_id,
                    started_at,
                    manifest,
                )
                worktree = create_worktree(
                    self.config.repository_path(order.repository_full_name),
                    self.config.worker_root,
                    order.commit_sha,
                    worker_id=self.config.worker_id,
                    execution_run_id=checkout.run_id,
                )
                worktree.verify_checkout_integrity()
                terminal, reason, cleanup = "succeeded", None, "pending"
                execute_fresh = True
                if order.reuse_policy != "never":
                    if manifest.dependency_lock_paths:
                        worktree.verify_checkout_integrity()
                        dependency_locks = self._hash_dependency_locks(
                            manifest, worktree.checkout
                        )
                        worktree.verify_checkout_integrity()
                        dependency_lock_status = "succeeded"
                    reuse_identity = self._build_reuse_identity(
                        order=order,
                        manifest=manifest,
                        environment=environment,
                        dependency_locks=dependency_locks,
                    )
                    reuse_identity_hash = compute_reuse_identity_hash(reuse_identity)
                    try:
                        lookup = ReuseLookup.from_payload(
                            self.client.resolve_reuse_candidate(
                                checkout.run_id,
                                reuse_identity=reuse_identity.model_dump(mode="json"),
                                reuse_identity_hash=reuse_identity_hash,
                            )
                        )
                        reuse_reason = lookup.reason
                    except ExecutionOwnershipLostError:
                        token.cancel("ownership_lost")
                    except (OSError, ValueError):
                        reuse_reason = "reuse_lookup_unavailable"
                    if token.cancelled:
                        terminal, reason, skip_completion = _cancellation_outcome(token)
                        execute_fresh = False
                    elif lookup is not None and lookup.candidate is not None:
                        verification = verify_reuse_candidate(
                            evidence_root=self.config.evidence_root,
                            worker_id=self.config.worker_id,
                            candidate=lookup.candidate,
                            now=dt.datetime.now(dt.UTC),
                            limits=store.limits,
                        )
                        reuse_reason = verification.reason
                        if verification.verified:
                            reuse_decision = "reused"
                            execute_fresh = False
                            terminal, reason = "succeeded", None
                        elif order.reuse_policy == "require_exact":
                            reuse_decision = "unavailable"
                            execute_fresh = False
                            terminal, reason = "failed", verification.reason
                    elif order.reuse_policy == "require_exact":
                        reuse_decision = "unavailable"
                        execute_fresh = False
                        terminal, reason = "failed", reuse_reason
                    else:
                        reuse_reason = (
                            lookup.reason if lookup is not None else reuse_reason
                        )

                if execute_fresh:
                    reuse_decision = "fresh"
                    for step in manifest.execution_steps:
                        attempted_steps.append(step)
                        if self._shutdown.is_set():
                            token.cancel("worker_shutdown")
                        try:
                            result = run_step(
                                step,
                                worktree.checkout,
                                store.logs,
                                self.config,
                                deadline,
                                cancellation=token,
                                allowed_inherited_environment_keys=(
                                    _allowed_inherited_environment_keys(manifest)
                                ),
                                result_contract=_step_result_contract(
                                    manifest, step.id
                                ),
                                strict_containment=manifest.result_contract is not None,
                                checkout_guard=worktree.verify_checkout_integrity,
                            )
                        except OverallDeadlineExceededError as error:
                            if token.cancelled:
                                terminal, reason, skip_completion = (
                                    _cancellation_outcome(token)
                                )
                            else:
                                terminal, reason = "timed_out", str(error)
                            break
                        except ContainmentCleanupError:
                            source_quiescent = False
                            terminal, reason = "failed", "descendant_cleanup_failed"
                            break
                        except Exception as error:
                            # Once a runner call has begun, an unexpected error
                            # cannot prove whether target children survived.  This
                            # deliberately drains the worker even for a pre-launch
                            # failure: false-positive quarantine is safer than
                            # recursive cleanup in a possibly live target context.
                            source_quiescent = False
                            if token.cancelled:
                                terminal, reason, skip_completion = (
                                    _cancellation_outcome(token)
                                )
                                break
                            terminal, reason = (
                                "failed",
                                f"worker_error:{type(error).__name__}",
                            )
                            break
                        if (
                            manifest.result_contract is not None
                            and result.parsed_result is not None
                            and result.parsed_result.status == "parser_failed"
                        ):
                            result = replace(
                                result,
                                status="failed",
                                terminal_reason="result_contract_parser_failed",
                            )
                        if result.terminal_reason == "descendant_cleanup_failed":
                            source_quiescent = False
                        results.append(result)
                        if result.status != "succeeded" and step.required:
                            terminal = (
                                "timed_out"
                                if result.status == "timed_out"
                                else result.status
                            )
                            reason = (
                                result.terminal_reason
                                or f"required_step_{result.status}:{step.id}"
                            )
                            break
                if token.cancelled:
                    terminal, reason, skip_completion = _cancellation_outcome(token)
        except ContainmentCleanupError:
            source_quiescent = False
            terminal, reason = "failed", "descendant_cleanup_failed"
        except ExecutionOwnershipLostError:
            skip_completion, terminal, reason = True, "cancelled", "ownership_lost"
        except LocalCommitUnavailableError:
            terminal, reason = "failed", "requested_sha_not_available_locally"
        except Exception as error:  # terminal outcome must stay truthful and bounded
            terminal, reason = "failed", f"worker_error:{type(error).__name__}"
            if order is not None and order.reuse_policy == "require_exact":
                reuse_decision = "unavailable"
                reuse_reason = "reuse_precondition_failed"
        finally:
            if monitor is not None:
                monitor.stop()
            with self._state_lock:
                self._active_token = None
            if not source_quiescent:
                # A strict host could still have a live target descendant. Do
                # not let this process accept a later work order in the same
                # security context.  An operator must investigate/terminate
                # the retained process or discard the worker host/VM; merely
                # restarting this Python process cannot prove an orphan is gone.
                self._shutdown.set()
            if worktree is not None and manifest is not None:
                if source_quiescent:
                    try:
                        worktree.verify_checkout_integrity()
                    except Exception:
                        source_integrity_verified = False
                        if terminal == "succeeded":
                            terminal, reason = "failed", "checkout_integrity_failed"
                else:
                    # This check invokes Git against a target-mutable checkout.
                    # Once child quiescence is unproven, retain every target-owned
                    # path and perform no further subprocess or filesystem I/O.
                    source_integrity_verified = False
                if not source_quiescent or not source_integrity_verified:
                    if manifest.dependency_lock_paths:
                        dependency_lock_status = (
                            "skipped:source_quiescence_failed"
                            if not source_quiescent
                            else "skipped:checkout_integrity_failed"
                        )
                    if store is not None:
                        artifact_status = (
                            "skipped:source_quiescence_failed"
                            if not source_quiescent
                            else "skipped:checkout_integrity_failed"
                        )
                elif (
                    manifest.dependency_lock_paths
                    and dependency_lock_status != "succeeded"
                ):
                    try:
                        worktree.verify_checkout_integrity()
                        dependency_locks = self._hash_dependency_locks(
                            manifest, worktree.checkout
                        )
                        worktree.verify_checkout_integrity()
                        dependency_lock_status = "succeeded"
                    except Exception as error:
                        dependency_lock_status = f"failed:{type(error).__name__}"
                        if terminal == "succeeded":
                            terminal, reason = "failed", "dependency_lock_hash_failed"
                if store is not None and source_quiescent and source_integrity_verified:
                    try:
                        declarations = tuple(
                            (step.id, artifact)
                            for step in attempted_steps
                            for artifact in step.artifacts
                        )
                        for _step_id, declaration in declarations:
                            worktree.verify_checkout_integrity()
                            store.capture_declared_artifact(
                                worktree.checkout, declaration
                            )
                        worktree.verify_checkout_integrity()
                        artifacts = store.finalize_artifacts(declarations)
                        artifact_status = "succeeded"
                    except Exception as error:
                        artifact_status = f"failed:{type(error).__name__}"
                        if terminal == "succeeded":
                            terminal, reason = "failed", "artifact_finalization_failed"
            if worktree is not None:
                # Do not recursively remove a path while process containment or
                # checkout identity is unproven.  A surviving target process (or
                # a replaced checkout) could otherwise race cleanup and turn a
                # truthful execution failure into an unsafe filesystem action.
                if not source_quiescent:
                    cleanup = "skipped:source_quiescence_failed"
                elif not source_integrity_verified:
                    cleanup = "skipped:checkout_integrity_failed"
                else:
                    try:
                        worktree.cleanup()
                        cleanup = "succeeded"
                    except (
                        Exception
                    ) as error:  # cleanup failure is part of the terminal result
                        cleanup = f"failed:{type(error).__name__}"
                        if terminal == "succeeded":
                            terminal, reason = "failed", "cleanup_failed"
            if order is not None:
                summary = self._summary(order, results)
            if (
                store is not None
                and order is not None
                and manifest is not None
                and worktree is not None
                and source_quiescent
                and source_integrity_verified
            ):
                try:
                    if environment is None:
                        environment = _environment_identity(
                            self.config,
                            required_capabilities=(
                                manifest.required_capabilities,
                                order.required_capabilities,
                            ),
                        )
                    if reuse_identity is None:
                        reuse_identity = self._build_reuse_identity(
                            order=order,
                            manifest=manifest,
                            environment=environment,
                            dependency_locks=dependency_locks,
                        )
                        reuse_identity_hash = compute_reuse_identity_hash(
                            reuse_identity
                        )
                    assert reuse_identity_hash is not None
                    provenance = EvidenceReuseProvenance(
                        decision=reuse_decision,
                        reason=reuse_reason,
                        reuse_identity_hash=reuse_identity_hash,
                        source_run_id=(
                            lookup.candidate.source_run_id
                            if reuse_decision == "reused"
                            and lookup is not None
                            and lookup.candidate is not None
                            else None
                        ),
                        source_evidence_fingerprint=(
                            lookup.candidate.expected_source_evidence_fingerprint
                            if reuse_decision == "reused"
                            and lookup is not None
                            and lookup.candidate is not None
                            else None
                        ),
                    )
                    finished_at = dt.datetime.now(dt.UTC)
                    evidence = self._build_evidence(
                        order=order,
                        run_id=checkout.run_id,
                        manifest=manifest,
                        started_at=started_at,
                        finished_at=finished_at,
                        terminal=terminal,
                        reason=reason,
                        results=results,
                        artifacts=artifacts,
                        dependency_locks=dependency_locks,
                        dependency_lock_status=dependency_lock_status,
                        artifact_status=artifact_status,
                        cleanup=cleanup,
                        local_record_status="succeeded",
                        environment=environment,
                        reuse_provenance=provenance,
                    )
                    store.write_result(
                        {
                            "evidence": evidence.model_dump(mode="json"),
                            "result_summary": summary,
                            "reuse_identity": reuse_identity.model_dump(mode="json"),
                            "reuse_identity_hash": reuse_identity_hash,
                        }
                    )
                except Exception as error:
                    record_failure = f"failed:{type(error).__name__}"
                    if terminal == "succeeded":
                        terminal, reason = "failed", "local_result_record_failed"
                    try:
                        if environment is None or provenance is None:
                            raise RuntimeError("reuse evidence inputs unavailable")
                        evidence = self._build_evidence(
                            order=order,
                            run_id=checkout.run_id,
                            manifest=manifest,
                            started_at=started_at,
                            finished_at=dt.datetime.now(dt.UTC),
                            terminal=terminal,
                            reason=reason,
                            results=results,
                            artifacts=artifacts,
                            dependency_locks=dependency_locks,
                            dependency_lock_status=dependency_lock_status,
                            artifact_status=artifact_status,
                            cleanup=cleanup,
                            local_record_status=record_failure,
                            environment=environment,
                            reuse_provenance=provenance,
                        )
                    except Exception:
                        evidence = None
                        cleanup = f"{cleanup};evidence_failed"[:64]
                        terminal, reason = "failed", "evidence_finalization_failed"
            self._end_run(checkout.run_id)
        if skip_completion:
            return True
        try:
            self.client.complete_run(
                checkout.run_id,
                status=terminal,
                terminal_reason=reason,
                cleanup_status=cleanup,
                result_summary=self._serialize_summary(summary),
                artifact_metadata=(
                    [item.model_dump(mode="json") for item in artifacts]
                    if evidence is not None
                    else []
                ),
                evidence_metadata=(
                    evidence.model_dump(mode="json") if evidence is not None else None
                ),
                reuse_decision=reuse_decision,
                reuse_reason=reuse_reason,
                reuse_identity=(
                    reuse_identity.model_dump(mode="json")
                    if reuse_identity is not None
                    else None
                ),
                reuse_identity_hash=reuse_identity_hash,
                evidence_retention_expires_at=(
                    store.retention_expires_at.isoformat().replace("+00:00", "Z")
                    if store is not None and evidence is not None
                    else None
                ),
            )
        except ExecutionOwnershipLostError:
            pass
        return True


__all__ = ["LOCAL_DATABASE_URI_MARKER", "RESULT_SUMMARY_LIMIT", "LocalWorker"]
