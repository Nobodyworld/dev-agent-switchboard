"""Direct owned-child launch and containment for server and worker processes."""

from __future__ import annotations

import json
import os
import socket
import sys
import time
from dataclasses import dataclass
from pathlib import Path

from client.python.execution_worker.containment import (
    ContainmentCleanupError,
    ContainmentLaunchError,
    StrictHostProcess,
    launch_strict_host,
)

from .config import OperatorLifecycleConfig
from .models import OperatorLifecycleFailure, RuntimeSummary
from .runtime import RuntimeLayout, inspect_runtime, touch_owned_stop


def _minimal_environment(
    config: OperatorLifecycleConfig,
    layout: RuntimeLayout,
    token: str,
) -> dict[str, str]:
    environment = {
        key: os.environ[key]
        for key in ("PATH", "PATHEXT", "SYSTEMROOT", "WINDIR", "HOME", "USERPROFILE")
        if key in os.environ
    }
    environment.update(
        {
            "PYTHONPATH": str(config.canonical_checkout),
            "PYTHONUTF8": "1",
            "PYTHONDONTWRITEBYTECODE": "1",
            "TEMP": str(layout.temporary),
            "TMP": str(layout.temporary),
            "SWITCHBOARD_ADMIN_TOKEN": token,
        }
    )
    return environment


def _write_private_json(path: Path, payload: dict[str, object]) -> None:
    try:
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(descriptor, "w", encoding="utf-8", closefd=True) as handle:
            json.dump(payload, handle, sort_keys=True, separators=(",", ":"))
            handle.flush()
            os.fsync(handle.fileno())
    except OSError as error:
        raise OperatorLifecycleFailure("private_configuration_write_failed") from error


def _record_process(
    layout: RuntimeLayout, summary: RuntimeSummary, kind: str, pid: int
) -> None:
    inspect_runtime(layout.root)
    _write_private_json(
        layout.process_records / f"{kind}.json",
        {
            "schema_version": 1,
            "runtime_id": summary.runtime_id,
            "kind": kind,
            "host_pid": pid,
        },
    )


def assert_port_bindable(host: str, port: int) -> None:
    family = socket.AF_INET6 if host == "::1" else socket.AF_INET
    address = (host, port, 0, 0) if family == socket.AF_INET6 else (host, port)
    try:
        with socket.socket(family, socket.SOCK_STREAM) as listener:
            listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 0)
            listener.bind(address)
    except OSError as error:
        raise OperatorLifecycleFailure("loopback_port_occupied") from error


def port_is_released(host: str, port: int) -> bool:
    try:
        assert_port_bindable(host, port)
    except OperatorLifecycleFailure:
        return False
    return True


@dataclass(slots=True)
class OwnedProcess:
    kind: str
    host: StrictHostProcess
    layout: RuntimeLayout
    stop_file: Path

    def running(self) -> bool:
        return self.host.process.poll() is None

    def stop(self, *, timeout: float) -> bool:
        inspect_runtime(self.layout.root)
        touch_owned_stop(self.layout, self.stop_file)
        deadline = time.monotonic() + timeout
        while self.host.process.poll() is None and time.monotonic() < deadline:
            time.sleep(0.05)
        if self.host.process.poll() is None:
            try:
                self.host.terminate(grace_seconds=min(timeout, 5.0))
            except ContainmentCleanupError as error:
                raise OperatorLifecycleFailure(
                    "owned_process_cleanup_unproven"
                ) from error
        try:
            outcome = self.host.finalize_after_exit(grace_seconds=min(timeout, 5.0))
        except ContainmentCleanupError as error:
            raise OperatorLifecycleFailure("owned_process_cleanup_unproven") from error
        if not outcome.cleanup_verified:
            raise OperatorLifecycleFailure("owned_process_cleanup_unproven")
        return True


def _launch(  # noqa: PLR0913 - containment inputs stay explicit
    *,
    kind: str,
    argv: tuple[str, ...],
    cwd: Path,
    environment: dict[str, str],
    layout: RuntimeLayout,
    summary: RuntimeSummary,
    stop_file: Path,
) -> OwnedProcess:
    inspect_runtime(layout.root)
    try:
        host = launch_strict_host(
            argv=argv,
            cwd=cwd,
            environment=environment,
            stdout=-3,
            stderr=-3,
        )
    except (ContainmentLaunchError, OSError) as error:
        raise OperatorLifecycleFailure(f"{kind}_launch_failed") from error
    try:
        _record_process(layout, summary, kind, host.process.pid)
    except Exception:
        try:
            host.terminate(grace_seconds=2.0)
        except ContainmentCleanupError:
            pass
        raise
    return OwnedProcess(kind=kind, host=host, layout=layout, stop_file=stop_file)


def launch_server(
    config: OperatorLifecycleConfig,
    layout: RuntimeLayout,
    summary: RuntimeSummary,
    token: str,
) -> OwnedProcess:
    assert_port_bindable(config.host, config.port)
    environment = _minimal_environment(config, layout, token)
    environment.update(
        {
            "DATABASE_URL": f"sqlite+aiosqlite:///{layout.database.as_posix()}",
            "STORAGE_ROOT": str(layout.server_storage),
            "FILES_ROOT": str(layout.file_storage),
        }
    )
    return _launch(
        kind="server",
        argv=(
            sys.executable,
            "-m",
            "scripts.operator_server",
            "--host",
            config.host,
            "--port",
            str(config.port),
            "--stop-file",
            str(layout.stop_server),
        ),
        cwd=config.canonical_checkout,
        environment=environment,
        layout=layout,
        summary=summary,
        stop_file=layout.stop_server,
    )


def launch_worker(
    config: OperatorLifecycleConfig,
    layout: RuntimeLayout,
    summary: RuntimeSummary,
    token: str,
) -> OwnedProcess:
    worker_payload: dict[str, object] = {
        "base_url": f"http://{config.host}:{config.port}",
        "worker_id": config.worker_id,
        "display_name": config.worker_display_name,
        "worker_root": str(layout.worker_source),
        "repositories": {config.repository_full_name: str(config.canonical_checkout)},
        "evidence_root": str(layout.retained_evidence),
        "max_concurrency": 1,
        "network_policy_capability": "worker_restricted",
        "execution_timeout_seconds": config.work_order_timeout_seconds,
        "default_step_timeout_seconds": min(60, config.work_order_timeout_seconds),
        "maximum_step_timeout_seconds": config.work_order_timeout_seconds,
        "evidence_retention_days": config.evidence_retention_days,
        "maximum_artifact_count": config.maximum_artifact_count,
        "maximum_artifact_bytes": config.maximum_artifact_bytes,
        "maximum_total_evidence_bytes": config.maximum_total_evidence_bytes,
        "poll_interval_seconds": config.poll_interval_seconds,
        "heartbeat_interval_seconds": max(
            1.0, min(15.0, config.poll_interval_seconds * 4)
        ),
    }
    _write_private_json(layout.worker_config, worker_payload)
    return _launch(
        kind="worker",
        argv=(
            sys.executable,
            "-m",
            "scripts.local_worker",
            "--config",
            str(layout.worker_config),
            "--stop-file",
            str(layout.stop_worker),
        ),
        cwd=config.canonical_checkout,
        environment=_minimal_environment(config, layout, token),
        layout=layout,
        summary=summary,
        stop_file=layout.stop_worker,
    )


__all__ = [
    "OwnedProcess",
    "assert_port_bindable",
    "launch_server",
    "launch_worker",
    "port_is_released",
]
