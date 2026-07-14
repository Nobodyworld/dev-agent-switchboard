"""Bounded host capability discovery for worker registration."""

from __future__ import annotations

import platform
import shutil
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
    node_available = shutil.which("node") is not None
    git_available = shutil.which("git") is not None

    return {
        "worker_id": config.worker_id,
        "display_name": config.display_name,
        "operating_system": platform.system().lower() or "unknown",
        "architecture": platform.machine().lower() or "unknown",
        "python_version": platform.python_version(),
        "node_version": None,
        "docker_available": shutil.which("docker") is not None,
        "browsers": browsers,
        "gpu_available": False,
        "unity_available": False,
        "desktop_available": False,
        "capabilities": {
            "git_available": git_available,
            "node_available": node_available,
            "repository_registry_count": len(config.repositories),
            "worker_root_configured": True,
        },
        "max_concurrency": config.max_concurrency,
        "network_policy_capability": "worker_restricted",
        "repository_write_capability": False,
        "status": "online",
    }


__all__ = ["discover_worker_registration"]
