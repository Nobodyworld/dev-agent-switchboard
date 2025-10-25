"""Test package for the Switchboard server."""

from __future__ import annotations

import pytest

pytest.importorskip(
    "sqlalchemy",
    reason=(
        "SQLAlchemy is not available in the offline test environment; "
        "server tests skipped."
    ),
)
pytest.importorskip(
    "fastapi",
    reason=(
        "FastAPI is not available in the offline test environment; "
        "server tests skipped."
    ),
)

