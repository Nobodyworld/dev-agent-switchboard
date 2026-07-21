# Every subprocess below uses a known executable discovered from a fixed name.
# ruff: noqa: S603
"""Bounded host capability discovery for worker registration."""

from __future__ import annotations

import platform
import shutil
import subprocess
from typing import Any

from .config import WorkerConfig

_BROWSER_EXECUTABLES = {
    "chromium": ("chromium", "chromium-browser"),
    "chrome": ("google-chrome", "chrome"),
    "edge": ("msedge",),
    "firefox": ("firefox",),
}


def _available(executable_names: tuple[str, ...]) -> bool:
    return any(shutil.which(name) is not None for name in executable_names)


def _node_version() -> str | None:
    """Read a fixed tool version without invoking a shell or repository code."""

    node_path = shutil.which("node")
    if node_path is None:
        return None
    try:
        completed = subprocess.run(
            [node_path, "--version"],
            check=False,
            shell=False,
            capture_output=True,
            text=True,
            timeout=2,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if completed.returncode != 0:
        return None
    value = (completed.stdout or completed.stderr).strip().splitlines()
    if not value:
        return None
    return value[0][:64]


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
    git_available = shutil.which("git") is not None

    return {
        "worker_id": config.worker_id,
        "display_name": config.display_name,
        "operating_system": platform.system().lower() or "unknown",
        "architecture": platform.machine().lower() or "unknown",
        "python_version": platform.python_version(),
        "node_version": node_version,
        "docker_available": shutil.which("docker") is not None,
        "browsers": browsers,
        "gpu_available": False,
        "unity_available": False,
        "desktop_available": False,
        "capabilities": {
            "git_available": git_available,
            "node_available": node_version is not None,
            "repository_registry_count": len(config.repositories),
            "worker_root_configured": True,
        },
        "max_concurrency": config.max_concurrency,
        "network_policy_capability": config.network_policy_capability,
        "repository_write_capability": False,
        "status": "online",
    }


__all__ = ["discover_worker_registration"]
