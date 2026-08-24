# Every subprocess below uses a known executable discovered from a fixed name.
# ruff: noqa: S603
"""Bounded host capability discovery for worker registration."""

from __future__ import annotations

import os
import platform
import re
import shutil
import signal
import subprocess
import threading
from pathlib import Path
from typing import Any

from .config import WorkerConfig
from .containment import (
    ContainmentCleanupError,
    ContainmentLaunchError,
    StrictHostProcess,
    launch_strict_host,
    strict_containment_supported,
)

_BROWSER_EXECUTABLES = {
    "chromium": ("chromium", "chromium-browser"),
    "chrome": ("google-chrome", "chrome"),
    "edge": ("msedge",),
    "firefox": ("firefox",),
}
_VERSION_TIMEOUT_SECONDS = 2.0
_VERSION_TERMINATION_TIMEOUT_SECONDS = 0.5
_VERSION_OUTPUT_LIMIT_BYTES = 256
_VERSION_READ_CHUNK_BYTES = 64
_MAX_VERSION_LENGTH = 64
_SEMVER = re.compile(r"^(?:v)?(?P<major>\d+)\.(?P<minor>\d+)\.(?P<patch>\d+)$")
_PROBE_ENVIRONMENT_KEYS = (
    "PATH",
    "PATHEXT",
    "SYSTEMROOT",
    "WINDIR",
)


def _available(executable_names: tuple[str, ...]) -> bool:
    return any(shutil.which(name) is not None for name in executable_names)


def _probe_environment() -> dict[str, str]:
    """Return the minimal non-secret environment needed for fixed tool probes."""

    return {
        key: os.environ[key] for key in _PROBE_ENVIRONMENT_KEYS if key in os.environ
    }


def _probe_cwd() -> Path:
    """Return a neutral filesystem root, never the worker's source checkout."""

    return Path(os.path.abspath(os.sep))


def _terminate_probe(
    process: subprocess.Popen[bytes], strict_host: StrictHostProcess | None = None
) -> None:
    """Bound one fixed discovery process and its ordinary descendants."""

    if strict_host is not None:
        strict_host.terminate(grace_seconds=_VERSION_TERMINATION_TIMEOUT_SECONDS)
        return
    if not isinstance(getattr(process, "pid", None), int):  # test-double guard
        process.kill()
        return
    if os.name == "nt":
        subprocess.run(
            ["taskkill", "/PID", str(process.pid), "/T", "/F"],  # noqa: S607
            shell=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        )
        return
    kill_process_group = getattr(os, "killpg", None)
    if not callable(kill_process_group):
        return
    try:
        kill_process_group(process.pid, getattr(signal, "SIGKILL", signal.SIGTERM))
    except ProcessLookupError:
        return


def _reap_probe_descendants_after_exit(process: subprocess.Popen[bytes]) -> bool:
    """Reject a version probe that left an ordinary process-group descendant."""

    if not isinstance(getattr(process, "pid", None), int):
        return False
    if os.name == "nt":
        terminated = subprocess.run(
            ["taskkill", "/PID", str(process.pid), "/T", "/F"],  # noqa: S607
            shell=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        )
        return terminated.returncode == 0
    kill_process_group = getattr(os, "killpg", None)
    if not callable(kill_process_group):
        return True
    try:
        kill_process_group(process.pid, 0)
    except ProcessLookupError:
        return False
    except OSError:
        return True
    _terminate_probe(process)
    return True


def _launch_version_probe(
    executable_path: str,
) -> tuple[subprocess.Popen[bytes], StrictHostProcess | None] | None:
    """Start a fixed ``--version`` argv under strict containment when available."""

    environment = _probe_environment()
    if strict_containment_supported():
        try:
            strict_host = launch_strict_host(
                argv=(executable_path, "--version"),
                cwd=_probe_cwd(),
                environment=environment,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
            )
        except ContainmentLaunchError:
            return None
        return strict_host.process, strict_host
    try:
        process = subprocess.Popen(
            [executable_path, "--version"],
            shell=False,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            env=environment,
            start_new_session=os.name != "nt",
        )
    except OSError:
        return None
    return process, None


def _tool_version(  # noqa: PLR0911, PLR0912 - each failure boundary is fail-closed
    executable_name: str, *, allow_node_prefix: bool = False
) -> str | None:
    """Read one fixed runtime version with bounded time and retained output."""

    executable_path = shutil.which(executable_name)
    if executable_path is None:
        return None
    launched = _launch_version_probe(executable_path)
    if launched is None:
        return None
    process, strict_host = launched

    output = bytearray()
    output_limit_reached = threading.Event()

    def read_output() -> None:
        stdout = process.stdout
        if stdout is None:  # pragma: no cover - guarded by the Popen contract
            return
        try:
            while True:
                remaining = _VERSION_OUTPUT_LIMIT_BYTES + 1 - len(output)
                if remaining <= 0:
                    output_limit_reached.set()
                    return
                chunk = stdout.read(min(_VERSION_READ_CHUNK_BYTES, remaining))
                if not chunk:
                    return
                output.extend(chunk)
                if len(output) > _VERSION_OUTPUT_LIMIT_BYTES:
                    output_limit_reached.set()
                    return
        except OSError:
            return

    reader = threading.Thread(target=read_output, daemon=True)
    reader.start()
    reader.join(timeout=_VERSION_TIMEOUT_SECONDS)
    if reader.is_alive() or output_limit_reached.is_set():
        try:
            _terminate_probe(process, strict_host)
        except (ContainmentCleanupError, OSError):
            pass
    try:
        process.wait(timeout=_VERSION_TERMINATION_TIMEOUT_SECONDS)
    except (OSError, subprocess.TimeoutExpired):
        try:
            _terminate_probe(process, strict_host)
            process.wait(timeout=_VERSION_TERMINATION_TIMEOUT_SECONDS)
        except (ContainmentCleanupError, OSError, subprocess.TimeoutExpired):
            return None
    reader.join(timeout=_VERSION_TERMINATION_TIMEOUT_SECONDS)
    if reader.is_alive() or output_limit_reached.is_set() or process.returncode != 0:
        if strict_host is not None:
            try:
                strict_host.finalize_after_exit(
                    grace_seconds=_VERSION_TERMINATION_TIMEOUT_SECONDS
                )
            except ContainmentCleanupError:
                pass
        return None
    if strict_host is not None:
        try:
            outcome = strict_host.finalize_after_exit(
                grace_seconds=_VERSION_TERMINATION_TIMEOUT_SECONDS
            )
        except ContainmentCleanupError:
            return None
        if not outcome.cleanup_verified or outcome.had_descendants:
            return None
        return _parse_version_output(output, allow_node_prefix=allow_node_prefix)
    if _reap_probe_descendants_after_exit(process):
        return None
    return _parse_version_output(output, allow_node_prefix=allow_node_prefix)


def _parse_version_output(output: bytearray, *, allow_node_prefix: bool) -> str | None:
    """Validate one bounded version line after process containment quiesces."""

    value = output.decode("utf-8", errors="replace").strip().splitlines()
    if not value:
        return None
    first_line = value[0].strip()
    if len(first_line) > _MAX_VERSION_LENGTH:
        return None
    match = _SEMVER.fullmatch(first_line)
    if match is None:
        return None
    if first_line.startswith(("v", "V")) and not allow_node_prefix:
        return None
    return ".".join(match.group(name) for name in ("major", "minor", "patch"))


def _node_version() -> str | None:
    """Read the fixed Node runtime version without invoking a shell."""

    return _tool_version("node", allow_node_prefix=True)


def _pnpm_version() -> str | None:
    """Read the fixed pnpm version without invoking a shell."""

    return _tool_version("pnpm")


def discover_worker_registration(config: WorkerConfig) -> dict[str, Any]:
    """Return a bounded, read-only registration payload.

    Discovery only inspects platform metadata and executable availability. It does
    not execute repository code, inspect arbitrary environment variables, or
    claim process-level sandboxing.
    """

    browsers = [
        browser
        for browser, executable_names in _BROWSER_EXECUTABLES.items()
        if _available(executable_names)
    ]
    node_version = _node_version()
    pnpm_version = _pnpm_version()
    git_available = shutil.which("git") is not None

    return {
        "worker_id": config.worker_id,
        "display_name": config.display_name,
        "operating_system": platform.system().lower() or "unknown",
        "architecture": platform.machine().lower() or "unknown",
        "python_version": platform.python_version(),
        "node_version": node_version,
        "pnpm_version": pnpm_version,
        "docker_available": shutil.which("docker") is not None,
        "browsers": browsers,
        "gpu_available": False,
        "unity_available": False,
        "desktop_available": False,
        "capabilities": {
            "git_available": git_available,
            "node_available": node_version is not None,
            "pnpm_available": pnpm_version is not None,
            "repository_registry_count": len(config.repositories),
            "worker_root_configured": True,
        },
        "repository_full_names": sorted(config.repositories),
        "max_concurrency": config.max_concurrency,
        "network_policy_capability": config.network_policy_capability,
        "repository_write_capability": False,
        "status": "online",
    }


__all__ = ["discover_worker_registration"]
