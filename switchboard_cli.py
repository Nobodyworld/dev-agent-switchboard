"""Compatibility shim exposing the CLI entrypoint as a top-level module."""

from client.python.switchboard_cli import (
    HEARTBEAT_SHUTDOWN_TIMEOUT,
    HeartbeatLoop,
    build_parser,
    format_task,
    main,
    process_task,
    run_command,
)

__all__ = [
    "HEARTBEAT_SHUTDOWN_TIMEOUT",
    "HeartbeatLoop",
    "build_parser",
    "format_task",
    "main",
    "process_task",
    "run_command",
]
