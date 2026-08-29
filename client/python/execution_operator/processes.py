"""Direct owned-child launch and containment for server and worker processes."""

from __future__ import annotations

import json
import os
import socket
import stat
import subprocess
import sys
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path

from client.python.execution_worker.containment import (
    ContainmentCleanupError,
    ContainmentLaunchError,
    StrictHostProcess,
    launch_strict_host,
)

from .config import OperatorLifecycleConfig
from .models import OperatorLifecycleFailure, RuntimeSummary
from .preflight import assert_no_reparse_ancestry, path_is_reparse
from .runtime import (
    RuntimeLayout,
    touch_owned_stop,
    verify_runtime_ownership,
)

_MAX_PRIVATE_PROCESS_OUTPUT = 64 * 1024
_SWITCHBOARD_REPOSITORY = "nobodyworld/dev-agent-switchboard"
_CONTROL_PLANE_FILES = (
    "scripts/operator_server.py",
    "scripts/local_worker.py",
    "server/__init__.py",
    "client/python/execution_worker/__init__.py",
)


def _contains(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
    except ValueError:
        return False
    return True


def _control_plane_source_root(config: OperatorLifecycleConfig) -> Path:
    source = Path(__file__)
    if not source.is_absolute():
        source = Path(os.path.abspath(source))
    assert_no_reparse_ancestry(source, "control_plane_source_reparse_ancestry")
    try:
        root = source.parents[3]
        resolved = root.resolve(strict=True)
    except (IndexError, OSError) as error:
        raise OperatorLifecycleFailure("control_plane_source_invalid") from error
    assert_no_reparse_ancestry(root, "control_plane_source_reparse_ancestry")
    for relative in _CONTROL_PLANE_FILES:
        expected = root.joinpath(*relative.split("/"))
        assert_no_reparse_ancestry(expected, "control_plane_source_reparse_ancestry")
        try:
            metadata = expected.lstat()
        except OSError as error:
            raise OperatorLifecycleFailure("control_plane_source_invalid") from error
        if not stat.S_ISREG(metadata.st_mode) or path_is_reparse(expected):
            raise OperatorLifecycleFailure("control_plane_source_invalid")
    target = config.canonical_checkout.resolve(strict=True)
    if config.repository_full_name.casefold() != _SWITCHBOARD_REPOSITORY and (
        _contains(target, resolved) or _contains(resolved, target)
    ):
        raise OperatorLifecycleFailure("control_plane_target_overlap")
    return resolved


def _minimal_environment(
    layout: RuntimeLayout,
    token: str,
    control_plane_root: Path,
) -> dict[str, str]:
    environment = {
        key: os.environ[key]
        for key in ("PATH", "PATHEXT", "SYSTEMROOT", "WINDIR", "HOME", "USERPROFILE")
        if key in os.environ
    }
    environment.update(
        {
            "PYTHONPATH": str(control_plane_root),
            "PYTHONUTF8": "1",
            "PYTHONDONTWRITEBYTECODE": "1",
            "TEMP": str(layout.temporary),
            "TMP": str(layout.temporary_alt),
            "SWITCHBOARD_ADMIN_TOKEN": token,
        }
    )
    return environment


def _write_private_json(
    layout: RuntimeLayout,
    expected: RuntimeSummary,
    path: Path,
    payload: dict[str, object],
) -> None:
    try:
        verify_runtime_ownership(layout, expected, destination=path)
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(descriptor, "w", encoding="utf-8", closefd=True) as handle:
            json.dump(payload, handle, sort_keys=True, separators=(",", ":"))
            handle.flush()
            os.fsync(handle.fileno())
    except OSError as error:
        raise OperatorLifecycleFailure("private_configuration_write_failed") from error


def _write_private_bytes(
    layout: RuntimeLayout, expected: RuntimeSummary, path: Path, payload: bytes
) -> None:
    try:
        verify_runtime_ownership(layout, expected, destination=path)
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(descriptor, "wb", closefd=True) as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
    except OSError as error:
        raise OperatorLifecycleFailure("private_diagnostic_write_failed") from error


def _record_process(
    layout: RuntimeLayout, summary: RuntimeSummary, kind: str, pid: int
) -> None:
    _write_private_json(
        layout,
        summary,
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
    expected_runtime: RuntimeSummary
    stop_file: Path
    _redacted_token: bytes = field(repr=False)
    _output: bytearray = field(default_factory=bytearray, repr=False)
    _output_truncated: bool = False
    _reader: threading.Thread | None = field(default=None, repr=False)

    def start_reader(self) -> None:
        stdout = self.host.process.stdout
        if stdout is None:
            raise OperatorLifecycleFailure("owned_process_output_unavailable")

        def drain() -> None:
            while chunk := stdout.read(4096):
                remaining = _MAX_PRIVATE_PROCESS_OUTPUT - len(self._output)
                if remaining > 0:
                    self._output.extend(chunk[:remaining])
                if len(chunk) > remaining:
                    self._output_truncated = True

        self._reader = threading.Thread(target=drain, daemon=True)
        self._reader.start()

    def _persist_output(self, *, timeout: float) -> None:
        if self._reader is not None:
            self._reader.join(timeout=timeout)
            if self._reader.is_alive():
                raise OperatorLifecycleFailure("owned_process_output_unproven")
        output = bytes(self._output)
        if self._redacted_token:
            output = output.replace(self._redacted_token, b"[REDACTED]")
        if self._output_truncated:
            output += b"\n[OUTPUT TRUNCATED]\n"
        _write_private_bytes(
            self.layout,
            self.expected_runtime,
            self.layout.process_records / f"{self.kind}.log",
            output,
        )

    def running(self) -> bool:
        return self.host.process.poll() is None

    def stop(self, *, timeout: float) -> bool:
        verify_runtime_ownership(self.layout, self.expected_runtime)
        touch_owned_stop(self.layout, self.expected_runtime, self.stop_file)
        deadline = time.monotonic() + timeout
        while self.host.process.poll() is None and time.monotonic() < deadline:
            time.sleep(0.05)
        if self.host.process.poll() is None:
            verify_runtime_ownership(self.layout, self.expected_runtime)
            try:
                self.host.terminate(grace_seconds=min(timeout, 5.0))
            except ContainmentCleanupError as error:
                raise OperatorLifecycleFailure(
                    "owned_process_cleanup_unproven"
                ) from error
        verify_runtime_ownership(self.layout, self.expected_runtime)
        try:
            outcome = self.host.finalize_after_exit(grace_seconds=min(timeout, 5.0))
        except ContainmentCleanupError as error:
            raise OperatorLifecycleFailure("owned_process_cleanup_unproven") from error
        if not outcome.cleanup_verified:
            raise OperatorLifecycleFailure("owned_process_cleanup_unproven")
        self._persist_output(timeout=min(timeout, 5.0))
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
    token: str,
) -> OwnedProcess:
    verify_runtime_ownership(layout, summary)
    try:
        host = launch_strict_host(
            argv=argv,
            cwd=cwd,
            environment=environment,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
        )
    except (ContainmentLaunchError, OSError) as error:
        raise OperatorLifecycleFailure(f"{kind}_launch_failed") from error
    try:
        _record_process(layout, summary, kind, host.process.pid)
    except Exception:
        verify_runtime_ownership(layout, summary)
        try:
            host.terminate(grace_seconds=2.0)
        except ContainmentCleanupError:
            pass
        raise
    owned = OwnedProcess(
        kind=kind,
        host=host,
        layout=layout,
        expected_runtime=summary,
        stop_file=stop_file,
        _redacted_token=token.encode("utf-8"),
    )
    owned.start_reader()
    return owned


def launch_server(
    config: OperatorLifecycleConfig,
    layout: RuntimeLayout,
    summary: RuntimeSummary,
    token: str,
) -> OwnedProcess:
    assert_port_bindable(config.host, config.port)
    control_plane_root = _control_plane_source_root(config)
    environment = _minimal_environment(layout, token, control_plane_root)
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
        cwd=control_plane_root,
        environment=environment,
        layout=layout,
        summary=summary,
        stop_file=layout.stop_server,
        token=token,
    )


def launch_worker(
    config: OperatorLifecycleConfig,
    layout: RuntimeLayout,
    summary: RuntimeSummary,
    token: str,
) -> OwnedProcess:
    control_plane_root = _control_plane_source_root(config)
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
        "heartbeat_interval_seconds": 15.0,
    }
    _write_private_json(layout, summary, layout.worker_config, worker_payload)
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
        cwd=control_plane_root,
        environment=_minimal_environment(layout, token, control_plane_root),
        layout=layout,
        summary=summary,
        stop_file=layout.stop_worker,
        token=token,
    )


__all__ = [
    "OwnedProcess",
    "assert_port_bindable",
    "launch_server",
    "launch_worker",
    "port_is_released",
]
