"""Outbound-only orchestration for one checkout run at a time."""

from __future__ import annotations

import json
import time
from dataclasses import dataclass

from server.execution.registry import get_trusted_manifest

from .capabilities import discover_worker_registration
from .client import ExecutionClient, ExecutionOwnershipLostError
from .config import WorkerConfig
from .models import AssignedWorkOrder, Checkout, SafeManifest
from .runner import run_step
from .worktree import create_worktree


@dataclass(slots=True)
class LocalWorker:
    config: WorkerConfig
    client: ExecutionClient

    def start(self) -> None:
        self.client.register_worker(discover_worker_registration(self.config))

    def poll_once(self) -> bool:
        checkout = Checkout.from_payload(self.client.checkout())
        if checkout.run_id is None:
            return False
        assert checkout.work_order_id is not None
        order = AssignedWorkOrder.from_payload(
            self.client.get_work_order(checkout.work_order_id)
        )
        manifest = get_trusted_manifest(order.manifest_name, order.manifest_version)
        remote = SafeManifest.from_payload(
            self.client.get_manifest(order.manifest_name, order.manifest_version)
        )
        if (
            manifest is None
            or manifest.digest != order.manifest_digest
            or remote.digest != manifest.digest
        ):
            raise ValueError("trusted manifest digest mismatch")
        if (
            manifest.repository_write_policy.value != "read_only"
            or order.network_policy != self.config.network_policy_capability
        ):
            raise ValueError("work order policy is incompatible with worker")
        worktree = create_worktree(
            self.config.repository_path(order.repository_full_name),
            self.config.worker_root,
            order.commit_sha,
        )
        results = []
        terminal, reason, cleanup = "succeeded", None, "succeeded"
        deadline = time.monotonic() + min(
            order.timeout_seconds,
            manifest.timeout_seconds,
            int(self.config.execution_timeout_seconds),
        )
        try:
            self.client.heartbeat_run(checkout.run_id)
            for step in manifest.execution_steps:
                result = run_step(
                    step,
                    worktree.checkout,
                    worktree.run_directory / "logs",
                    self.config,
                    deadline,
                )
                results.append(result)
                self.client.heartbeat_run(checkout.run_id)
                if result.status != "succeeded" and step.required:
                    terminal = "timed_out" if result.status == "timed_out" else "failed"
                    reason = f"required_step_{result.status}:{step.id}"
                    break
        except ExecutionOwnershipLostError:
            raise
        finally:
            try:
                worktree.cleanup()
            except Exception as error:  # cleanup must be reported, never hidden
                cleanup = f"failed:{type(error).__name__}"
                if terminal == "succeeded":
                    terminal, reason = "failed", "cleanup_failed"
        summary = json.dumps(
            {
                "checked_out_sha": order.commit_sha,
                "steps": [
                    {
                        "id": r.step_id,
                        "status": r.status,
                        "exit_code": r.exit_code,
                        "duration_seconds": round(r.duration_seconds, 3),
                        "stdout": r.stdout_summary,
                        "stderr": r.stderr_summary,
                        "truncated": r.summaries_truncated,
                        "logs": [r.stdout_log, r.stderr_log],
                    }
                    for r in results
                ],
            },
            separators=(",", ":"),
        )
        self.client.complete_run(
            checkout.run_id,
            status=terminal,
            terminal_reason=reason,
            cleanup_status=cleanup,
            result_summary=summary[:8000],
            evidence_metadata={"checked_out_sha": order.commit_sha},
        )
        return True
