"""Compatibility shim exposing the CLI entrypoint as a top-level module."""

# TODO - Replace wildcard re-export with explicit bindings for clarity and mypy support.
from client.python.switchboard_cli import *  # noqa: F401,F403
