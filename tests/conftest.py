"""Test configuration ensuring the project root is importable."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


def pytest_addoption(parser: pytest.Parser) -> None:
    """Register asyncio configuration keys when pytest-asyncio is unavailable."""

    parser.addini(
        "asyncio_default_fixture_loop_scope",
        "Default scope for asyncio fixtures when pytest-asyncio is optional.",
        default="function",
    )
