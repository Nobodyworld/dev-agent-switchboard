"""Regression tests for compatibility shims exposed at the repository root."""

from __future__ import annotations

import importlib
import sys


def _reload_module(name: str):
    sys.modules.pop(name, None)
    return importlib.import_module(name)


def test_switchboard_client_shim_reexports_library() -> None:
    shim = _reload_module("switchboard_client")
    impl = importlib.import_module("client.python.switchboard_client")

    assert shim.SwitchboardClient is impl.SwitchboardClient
    assert shim.DEFAULT_REQUEST_TIMEOUT == impl.DEFAULT_REQUEST_TIMEOUT


def test_switchboard_cli_shim_reexports_cli_module() -> None:
    shim = _reload_module("switchboard_cli")
    impl = importlib.import_module("client.python.switchboard_cli")

    # Spot-check several attributes to ensure the shim mirrors the package.
    for attribute in [
        "HEARTBEAT_SHUTDOWN_TIMEOUT",
        "HeartbeatLoop",
        "process_task",
        "run_command",
    ]:
        assert getattr(shim, attribute) is getattr(impl, attribute)
