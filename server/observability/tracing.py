"""Tracing utilities that degrade gracefully when OpenTelemetry is absent."""

from __future__ import annotations

import os
from collections.abc import Iterator
from contextlib import contextmanager, suppress
from typing import Any

try:  # pragma: no cover - optional dependency may be missing
    from opentelemetry import trace  # type: ignore
except Exception:  # pragma: no cover - tracing optional
    trace = None  # type: ignore[assignment]


def _tracing_enabled() -> bool:
    return os.getenv("SWITCHBOARD_ENABLE_TRACING", "").lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


@contextmanager
def span(name: str, **attributes: Any) -> Iterator[Any]:
    """Context manager that starts a tracing span when tracing is enabled."""

    if trace is None or not _tracing_enabled():
        yield None
        return
    tracer = trace.get_tracer("switchboard.observability")
    with tracer.start_as_current_span(name) as active_span:
        for key, value in attributes.items():
            if value is None:
                continue
            with suppress(Exception):  # pragma: no cover - attribute issues
                active_span.set_attribute(key, value)
        yield active_span


__all__ = ["span"]
