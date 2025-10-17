"""Prometheus metrics instrumentation helpers."""

from __future__ import annotations

import logging
import os
from typing import Optional
from weakref import WeakSet

from fastapi import FastAPI

_INSTRUMENTED_APPS: "WeakSet[FastAPI]" = WeakSet()

__all__ = ["setup_metrics"]


def _truthy_env(name: str) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return False
    return raw.lower() in {"1", "true", "yes", "on"}


def setup_metrics(app: FastAPI, endpoint: Optional[str] = None) -> bool:
    """Register Prometheus metrics when enabled.

    Returns ``True`` if instrumentation is activated. When disabled or when the
    optional dependency is missing the function returns ``False`` without
    raising.
    """

    if app in _INSTRUMENTED_APPS:
        return True

    if not _truthy_env("SWITCHBOARD_ENABLE_METRICS"):
        return False

    try:
        from prometheus_fastapi_instrumentator import Instrumentator
    except Exception:  # pragma: no cover - optional dependency
        logging.getLogger(__name__).warning(
            "Metrics requested but prometheus-fastapi-instrumentator is unavailable."
        )
        return False

    metrics_endpoint = endpoint or os.getenv("SWITCHBOARD_METRICS_PATH", "/metrics")
    Instrumentator().instrument(app).expose(
        app,
        endpoint=metrics_endpoint,
        include_in_schema=False,
        should_gzip=True,
    )
    _INSTRUMENTED_APPS.add(app)
    return True
