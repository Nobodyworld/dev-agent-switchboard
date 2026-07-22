"""Outbound-only single-concurrency worker orchestration."""

from __future__ import annotations

import datetime as dt
import hashlib
import importlib.metadata
import json
import platform
import threading
import time
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from server.execution.evidence import (
    ArtifactRecord,
    DependencyLockHash,
    EnvironmentIdentity,
    ExecutionEvidence,
    ExecutionEvidenceDraft,
    StepEvidence,
    TerminalStatus,
    ToolIdentity,
    finalize_evidence,
)
from server.execution.registry import TrustedManifest, TrustedStep, get_trusted_manifest

from .capabilities import discover_worker_registration
from .client import ExecutionClient, ExecutionOwnershipLostError
from .config import WorkerConfig
from .evidence import (
    EvidenceLimits,
    EvidenceStore,
    create_evidence_store,
    hash_declared_file,
    prune_expired_evidence,
)
from .models import AssignedWorkOrder, Checkout, ExecutionRun, SafeManifest
from .runner import (
    CancellationToken,
    OverallDeadlineExceededError,
    StepResult,
    run_step,
)
from .worktree import DisposableWorktree, create_worktree

_SERVER_TERMINAL_STATUSES = {"succeeded", "failed", "timed_out", "cancelled"}
RESULT_SUMMARY_LIMIT = 8000
STEP_EVIDENCE_SUMMARY_LIMIT = 4096
_ENVIRONMENT_TOOLS = ("ruff", "black", "mypy", "pytest", "coverage", "bandit")


def _environment_identity() -> EnvironmentIdentity:
    tools: list[ToolIdentity] = []
    for name in _ENVIRONMENT_TOOLS:
        try:
            version = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            continue
        tools.append(ToolIdentity(name=name, version=version))
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
        summary = "\n".join(
            item for item in (result.stdout_summary, result.stderr_summary) if item
        )[:STEP_EVIDENCE_SUMMARY_LIMIT]
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
                    or len(summary) >= STEP_EVIDENCE_SUMMARY_LIMIT
                ),
                log_artifact_paths=[path for path in paths if path in artifact_paths],
                parsed_result=result.parsed_result,
            )
        )
    return evidence


def _version_at_least(actual: str, minimum: str) -> bool:
    def numbers(value: str) -> tuple[int, ...]:
        return tuple(int(piece) for piece in value.split(".") if piece.isdigit())

    return numbers(actual) >= numbers(minimum)


def _requirement_satisfied(actual: object, expected: object) -> bool:
    if isinstance(expected, bool):
        return actual is expected
    if isinstance(expected, str):
        return actual == expected
    if isinstance(expected, list):
        return isinstance(actual, str) and actual in expected
    if isinstance(expected, Mapping) and set(expected) == {"minimum"}:
        minimum = expected["minimum"]
        return (
            isinstance(actual, str)
            and isinstance(minimum, str)
            and _version_at_least(actual, minimum)
        )
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
        "docker_available": "docker",
        "gpu_available": "gpu",
        "unity_available": "unity",
        "desktop_available": "desktop",
    }
    for name, expected in requirements.items():
        key = aliases.get(name, name)
        if key not in capabilities or not _requirement_satisfied(
            capabilities[key], expected
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
        return json.dumps(summary, ensure_ascii=False, separators=(",", ":"))

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
        self, run_id: int, created_at: dt.datetime
    ) -> EvidenceStore:
        return create_evidence_store(
            evidence_root=self.config.evidence_root,
            worker_root=self.config.worker_root,
            repository_roots=tuple(self.config.repositories.values()),
            worker_id=self.config.worker_id,
            run_id=run_id,
            created_at=created_at,
            retention_days=self.config.evidence_retention_days,
            limits=EvidenceLimits(
                maximum_artifact_count=self.config.maximum_artifact_count,
                maximum_artifact_bytes=self.config.maximum_artifact_bytes,
                maximum_total_bytes=self.config.maximum_total_evidence_bytes,
            ),
        )

    @staticmethod
    def _hash_dependency_locks(
        manifest: TrustedManifest, checkout: Path
    ) -> list[DependencyLockHash]:
        hashes: list[DependencyLockHash] = []
        for relative_path in manifest.dependency_lock_paths:
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
            environment=_environment_identity(),
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
        )
        return finalize_evidence(draft)

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
        terminal: TerminalStatus = "failed"
        reason: str | None = "worker_initialization_failed"
        cleanup: str = "not_started"
        skip_completion = False
        order: AssignedWorkOrder | None = None
        summary: dict[str, Any] = {"steps": []}
        evidence: ExecutionEvidence | None = None
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
                store = self._create_evidence_store(checkout.run_id, started_at)
                worktree = create_worktree(
                    self.config.repository_path(order.repository_full_name),
                    self.config.worker_root,
                    order.commit_sha,
                    worker_id=self.config.worker_id,
                    execution_run_id=checkout.run_id,
                )
                terminal, reason, cleanup = "succeeded", None, "pending"
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
                        )
                    except OverallDeadlineExceededError as error:
                        if token.cancelled:
                            terminal, reason, skip_completion = _cancellation_outcome(
                                token
                            )
                        else:
                            terminal, reason = "timed_out", str(error)
                        break
                    except Exception:
                        if token.cancelled:
                            terminal, reason, skip_completion = _cancellation_outcome(
                                token
                            )
                            break
                        raise
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
        except ExecutionOwnershipLostError:
            skip_completion, terminal, reason = True, "cancelled", "ownership_lost"
        except Exception as error:  # terminal outcome must stay truthful and bounded
            terminal, reason = "failed", f"worker_error:{type(error).__name__}"
        finally:
            if monitor is not None:
                monitor.stop()
            with self._state_lock:
                self._active_token = None
            if worktree is not None and manifest is not None:
                if manifest.dependency_lock_paths:
                    try:
                        dependency_locks = self._hash_dependency_locks(
                            manifest, worktree.checkout
                        )
                        dependency_lock_status = "succeeded"
                    except Exception as error:
                        dependency_lock_status = f"failed:{type(error).__name__}"
                        if terminal == "succeeded":
                            terminal, reason = "failed", "dependency_lock_hash_failed"
                if store is not None:
                    try:
                        declarations = tuple(
                            (step.id, artifact)
                            for step in attempted_steps
                            for artifact in step.artifacts
                        )
                        artifacts = store.finalize_artifacts(declarations)
                        artifact_status = "succeeded"
                    except Exception as error:
                        artifact_status = f"failed:{type(error).__name__}"
                        if terminal == "succeeded":
                            terminal, reason = "failed", "artifact_finalization_failed"
            if worktree is not None:
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
            ):
                try:
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
                    )
                    store.write_result(
                        {
                            "evidence": evidence.model_dump(mode="json"),
                            "result_summary": summary,
                        }
                    )
                except Exception as error:
                    record_failure = f"failed:{type(error).__name__}"
                    if terminal == "succeeded":
                        terminal, reason = "failed", "local_result_record_failed"
                    try:
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
            )
        except ExecutionOwnershipLostError:
            pass
        return True


__all__ = ["RESULT_SUMMARY_LIMIT", "LocalWorker"]
