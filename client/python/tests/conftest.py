"""Test helpers for the Switchboard client package."""

from __future__ import annotations

import importlib
import sys
from pathlib import Path

# Ensure the real client module is loaded before tests that patch ``sys.modules``
# with lightweight stand-ins. This keeps attribute imports consistent across the
# suite regardless of module import order.
PROJECT_ROOT = Path(__file__).resolve().parents[3]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

client_module = importlib.import_module("client.python.switchboard_client")
cli_module = importlib.import_module("client.python.switchboard_cli")

sys.modules["switchboard_client"] = client_module
sys.modules["switchboard_cli"] = cli_module
