"""Utilities for working with time providers and UTC-aware timestamps."""

from __future__ import annotations

import datetime as dt
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from contextvars import ContextVar, Token

UTC = dt.timezone.utc

TimeProvider = Callable[[], dt.datetime]


def _default_time_provider() -> dt.datetime:
    return dt.datetime.now(UTC)


_TIME_PROVIDER: ContextVar[TimeProvider] = ContextVar(
    "switchboard_time_provider", default=_default_time_provider
)

__all__ = [
    "override_time_provider",
    "reset_time_provider",
    "set_time_provider",
    "utcnow",
    "utcnow_naive",
]


def _normalize(value: dt.datetime) -> dt.datetime:
    """Ensure the provided datetime is timezone-aware in UTC."""

    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _wrap_provider(provider: TimeProvider) -> TimeProvider:
    def _inner() -> dt.datetime:
        value = provider()
        if not isinstance(value, dt.datetime):
            raise TypeError("provider must return datetime instances")
        return _normalize(value)

    return _inner


def set_time_provider(provider: TimeProvider) -> Token[TimeProvider]:
    """Set the active time provider and return a token to restore it later."""

    if not callable(provider):  # pragma: no cover - defensive guard
        raise TypeError("provider must be callable")
    wrapped = _wrap_provider(provider)
    return _TIME_PROVIDER.set(wrapped)


@contextmanager
def override_time_provider(provider: TimeProvider) -> Iterator[None]:
    """Temporarily override the time provider within a context."""

    token = set_time_provider(provider)
    try:
        yield
    finally:
        _TIME_PROVIDER.reset(token)


def reset_time_provider(token: Token[TimeProvider]) -> None:
    """Restore the previous time provider using ``token``."""

    _TIME_PROVIDER.reset(token)


def utcnow() -> dt.datetime:
    """Return the current timezone-aware UTC timestamp."""

    return _TIME_PROVIDER.get()()


def utcnow_naive() -> dt.datetime:
    """Return the current UTC timestamp without timezone information."""

    return utcnow().replace(tzinfo=None)
