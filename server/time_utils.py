"""Shared timezone-aware UTC helpers for the Switchboard server."""

from __future__ import annotations

import datetime as dt

UTC = dt.timezone.utc


def utcnow() -> dt.datetime:
    """Return the current timezone-aware UTC timestamp."""

    return dt.datetime.now(UTC)


def utcnow_naive() -> dt.datetime:
    """Return the current UTC timestamp without timezone information."""

    return utcnow().replace(tzinfo=None)
