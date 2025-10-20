"""Prometheus metrics instrumentation helpers."""

from __future__ import annotations

import logging
import os
from typing import TYPE_CHECKING, Any
from weakref import WeakKeyDictionary, WeakSet

from fastapi import FastAPI

_INSTRUMENTED_APPS: WeakSet[FastAPI] = WeakSet()
_APP_INSTRUMENTATORS: WeakKeyDictionary[FastAPI, object] = WeakKeyDictionary()

__all__ = ["setup_metrics"]


try:  # pragma: no cover - optional dependency may be absent
    from prometheus_fastapi_instrumentator import Instrumentator  # type: ignore
except Exception:  # pragma: no cover - optional dependency
    Instrumentator = None  # type: ignore[assignment]

if TYPE_CHECKING:  # pragma: no cover - optional dependency type hints
    from prometheus_client import CollectorRegistry  # type: ignore
else:  # pragma: no cover - fallback typing alias when dependency missing
    CollectorRegistry = Any  # type: ignore[assignment]


def _truthy_env(name: str) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return False
    return raw.lower() in {"1", "true", "yes", "on"}


def setup_metrics(
    app: FastAPI,
    endpoint: str | None = None,
    *,
    registry: CollectorRegistry | None = None,
    instrumentator: Instrumentator | None = None,
) -> bool:
    """Register Prometheus metrics when enabled.

    Returns ``True`` if instrumentation is activated. When disabled or when the
    optional dependency is missing the function returns ``False`` without
    raising.
    """

    if app in _INSTRUMENTED_APPS:
        # Ensure cached instrumentators remain associated for observability hooks
        if app not in _APP_INSTRUMENTATORS and instrumentator is not None:
            _APP_INSTRUMENTATORS[app] = instrumentator
        return True

    if not _truthy_env("SWITCHBOARD_ENABLE_METRICS"):
        return False

    if Instrumentator is None:
        logging.getLogger(__name__).warning(
            "Metrics requested but prometheus-fastapi-instrumentator is unavailable."
        )
        return False

    metrics_endpoint = endpoint or os.getenv("SWITCHBOARD_METRICS_PATH", "/metrics")
    instrumentator_instance = instrumentator or Instrumentator(registry=registry)
    instrumentator_instance.instrument(app).expose(
        app,
        endpoint=metrics_endpoint,
        include_in_schema=False,
        should_gzip=True,
    )
    _INSTRUMENTED_APPS.add(app)
    _APP_INSTRUMENTATORS[app] = instrumentator_instance
    return True
