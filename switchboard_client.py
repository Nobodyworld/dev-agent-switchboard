"""Compatibility shim exposing the client library as a top-level module."""

from client.python.switchboard_client import DEFAULT_REQUEST_TIMEOUT, SwitchboardClient

__all__ = ["DEFAULT_REQUEST_TIMEOUT", "SwitchboardClient"]
