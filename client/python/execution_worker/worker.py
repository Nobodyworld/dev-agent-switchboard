"""Outbound-only single-concurrency worker orchestration."""

from __future__ import annotations

import json
import threading
import time
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

from server.execution.registry import TrustedManifest, get_trusted_manifest

from .capabilities import discover_worker_registration
from .client import ExecutionClient, ExecutionOwnershipLostError
from .config import WorkerConfig
from .models import AssignedWorkOrder, Checkout, ExecutionRun, SafeManifest
from .runner import (
    CancellationToken,
    OverallDeadlineExceededError,
    StepResult,
    run_step,
)
from .worktree import DisposableWorktree, create_worktree

_SERVER_TERMINAL_STATUSES = {"succeeded", "failed", "timed_out", "cancelled"}


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
            self.worker.client.heartbeat_run(self.run_id)
            run = ExecutionRun.from_payload(self.worker.client.get_run(self.run_id))
        except ExecutionOwnershipLostError:
            self.token.cancel("ownership_lost")
            return
        except (OSError, ValueError):
            # An unavailable control plane will naturally expire the server lease;
            # do not pretend local connectivity proves cancellation or ownership.
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

    def _begin_run(self, run_id: int) -> bool:
        with self._state_lock:
            if self._shutdown.is_set() or self._active_run_id is not None:
                return False
            if run_id in self._executed_run_ids:
                raise RuntimeError("local execution run was already attempted")
            self._executed_run_ids.add(run_id)
            self._active_run_id = run_id
            return True

    def _end_run(self, run_id: int) -> None:
        with self._state_lock:
            if self._active_run_id == run_id:
                self._active_run_id = None

    @staticmethod
    def _summary(order: AssignedWorkOrder, results: list[StepResult]) -> str:
        return json.dumps(
            {
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
            },
            separators=(",", ":"),
        )[:8000]

    @staticmethod
    def _write_run_record(
        worktree: DisposableWorktree,
        *,
        terminal: str,
        reason: str | None,
        cleanup: str,
        summary: str,
    ) -> None:
        record = worktree.run_directory / "result.json"
        record.write_text(
            json.dumps(
                {
                    "cleanup_status": cleanup,
                    "result_summary": json.loads(summary),
                    "terminal_reason": reason,
                    "terminal_status": terminal,
                },
                separators=(",", ":"),
            ),
            encoding="utf-8",
        )

    def poll_once(self) -> bool:  # noqa: PLR0912, PLR0915 - lifecycle state machine
        """Checkout and process at most one run; never execute while draining."""

        if self.shutting_down:
            return False
        checkout = Checkout.from_payload(self.client.checkout())
        if checkout.run_id is None:
            return False
        assert checkout.work_order_id is not None
        if not self._begin_run(checkout.run_id):
            return False
        worktree: DisposableWorktree | None = None
        monitor: _RunMonitor | None = None
        results: list[StepResult] = []
        terminal: str = "failed"
        reason: str | None = "worker_initialization_failed"
        cleanup: str = "not_started"
        skip_completion = False
        order: AssignedWorkOrder | None = None
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
                reason = token.reason
                skip_completion = reason == "ownership_lost" or reason.startswith(
                    "server_terminal:"
                )
                terminal = "timed_out" if reason == "overall_timeout" else "cancelled"
            elif self._shutdown.is_set():
                token.cancel("worker_shutdown")
                terminal, reason = "cancelled", token.reason
            else:
                worktree = create_worktree(
                    self.config.repository_path(order.repository_full_name),
                    self.config.worker_root,
                    order.commit_sha,
                    worker_id=self.config.worker_id,
                    execution_run_id=checkout.run_id,
                )
                terminal, reason, cleanup = "succeeded", None, "pending"
                for step in manifest.execution_steps:
                    if self._shutdown.is_set():
                        token.cancel("worker_shutdown")
                    try:
                        result = run_step(
                            step,
                            worktree.checkout,
                            worktree.logs,
                            self.config,
                            deadline,
                            cancellation=token,
                        )
                    except OverallDeadlineExceededError as error:
                        terminal, reason = "timed_out", str(error)
                        break
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
                    reason = token.reason
                    if reason == "overall_timeout":
                        terminal = "timed_out"
                    elif reason == "ownership_lost" or reason.startswith(
                        "server_terminal:"
                    ):
                        terminal = "cancelled"
                        skip_completion = True
                    else:
                        terminal = "cancelled"
        except ExecutionOwnershipLostError:
            skip_completion, terminal, reason = True, "cancelled", "ownership_lost"
        except Exception as error:  # terminal outcome must stay truthful and bounded
            terminal, reason = "failed", f"worker_error:{type(error).__name__}"
        finally:
            if monitor is not None:
                monitor.stop()
            with self._state_lock:
                self._active_token = None
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
                    self._write_run_record(
                        worktree,
                        terminal=terminal,
                        reason=reason,
                        cleanup=cleanup,
                        summary=summary,
                    )
            self._end_run(checkout.run_id)
        if skip_completion:
            return True
        if order is None:
            summary = json.dumps({"steps": []})
        else:
            summary = self._summary(order, results)
        try:
            self.client.complete_run(
                checkout.run_id,
                status=terminal,
                terminal_reason=reason,
                cleanup_status=cleanup,
                result_summary=summary,
                evidence_metadata={
                    "checked_out_sha": order.commit_sha if order else None,
                    "local_record": "result.json" if worktree else None,
                },
            )
        except ExecutionOwnershipLostError:
            pass
        return True


__all__ = ["LocalWorker"]
