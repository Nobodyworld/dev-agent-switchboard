"""Logging instrumentation helpers.

This module centralizes request ID propagation and opt-in structured logging
configuration. It is intentionally lightweight so it can be imported from
``server.app`` without side effects when disabled via environment variables.
"""

from __future__ import annotations

import json
import logging
import os
import uuid
from contextvars import ContextVar
from logging.config import dictConfig, fileConfig
from weakref import WeakSet

from fastapi import FastAPI, Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp

try:  # pragma: no cover - optional dependency may be absent
    from pythonjsonlogger.json import JsonFormatter  # type: ignore
except Exception:  # pragma: no cover - optional dependency
    try:
        from pythonjsonlogger import jsonlogger as _legacy_jsonlogger  # type: ignore
    except Exception:  # pragma: no cover - optional dependency
        JsonFormatter = None  # type: ignore[assignment]
    else:
        JsonFormatter = _legacy_jsonlogger.JsonFormatter  # type: ignore[assignment]

_INSTRUMENTED_APPS: WeakSet[FastAPI] = WeakSet()
_REQUEST_ID_CTX: ContextVar[str] = ContextVar("switchboard_request_id", default="-")
_TRACE_ID_CTX: ContextVar[str] = ContextVar("switchboard_trace_id", default="-")


class _LoggingState:
    def __init__(self) -> None:
        self.configured = False
        self.initialized = False
        self.request_filter_installed = False


_STATE = _LoggingState()

DEFAULT_REQUEST_ID_HEADER = "X-Request-ID"
STRUCTURED_LOG_FORMAT = (
    "%(asctime)s %(levelname)s %(name)s %(message)s %(request_id)s %(trace_id)s"
)

TRACE_ID_LENGTH = 32
TRACEPARENT_PART_MIN = 2
TRACE_ID_ALPHABET = "0123456789abcdef"


def _extract_trace_id(raw_header: str | None) -> str:
    """Return a 32-character trace identifier."""

    if not raw_header:
        return uuid.uuid4().hex
    parts = [part for part in raw_header.split("-") if part]
    if len(parts) >= TRACEPARENT_PART_MIN and len(parts[1]) == TRACE_ID_LENGTH:
        return parts[1]
    candidate = raw_header.strip()
    if len(candidate) == TRACE_ID_LENGTH and all(
        char in TRACE_ID_ALPHABET for char in candidate.lower()
    ):
        return candidate
    return uuid.uuid4().hex


def _truthy_env(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.lower() in {"1", "true", "yes", "on"}


class RequestIdMiddleware(BaseHTTPMiddleware):
    """Attach a request ID to incoming requests and responses."""

    def __init__(
        self, app: ASGIApp, header_name: str = DEFAULT_REQUEST_ID_HEADER
    ) -> None:
        super().__init__(app)
        self.header_name = header_name

    async def dispatch(self, request: Request, call_next):  # type: ignore[override]
        request_id = request.headers.get(self.header_name) or str(uuid.uuid4())
        request_token = _REQUEST_ID_CTX.set(request_id)
        trace_id = _extract_trace_id(request.headers.get("traceparent"))
        trace_token = _TRACE_ID_CTX.set(trace_id)
        try:
            request.state.request_id = request_id
            response = await call_next(request)
        finally:
            _REQUEST_ID_CTX.reset(request_token)
            _TRACE_ID_CTX.reset(trace_token)
        response.headers.setdefault(self.header_name, request_id)
        response.headers.setdefault("X-Trace-ID", trace_id)
        return response


class RequestIdFilter(logging.Filter):
    """Inject the request ID contextvar into log records."""

    def filter(self, record: logging.LogRecord) -> bool:  # pragma: no cover - trivial
        record.request_id = _REQUEST_ID_CTX.get("-")
        record.trace_id = _TRACE_ID_CTX.get("-")
        return True


def configure_logging() -> bool:
    """Configure logging for structured output if requested.

    Returns ``True`` when any configuration action was applied. The function is
    idempotent and safe to call multiple times.
    """

    if _STATE.initialized and _STATE.configured:
        return True

    configured = False
    filter_installed = False
    dict_payload = os.getenv("SWITCHBOARD_LOGGING_DICT")
    if dict_payload:
        try:
            config = json.loads(dict_payload)
            dictConfig(config)
            configured = True
        except Exception:  # pragma: no cover - configuration errors logged below
            logging.getLogger(__name__).warning(
                "Failed to load logging dictConfig", exc_info=True
            )

    config_path = os.getenv("SWITCHBOARD_LOGGING_CONFIG")
    if config_path and os.path.exists(config_path):
        try:
            fileConfig(config_path, disable_existing_loggers=False)
            configured = True
        except (
            Exception
        ):  # pragma: no cover - configuration errors are surfaced via warnings
            logging.getLogger(__name__).warning(
                "Failed to load logging config from %s",
                config_path,
                exc_info=True,
            )

    if _truthy_env("SWITCHBOARD_ENABLE_STRUCTURED_LOGGING"):
        if JsonFormatter is None:
            logging.getLogger(__name__).warning(
                "Structured logging requested but python-json-logger is unavailable."
            )
        else:
            handler = logging.StreamHandler()
            formatter = JsonFormatter(STRUCTURED_LOG_FORMAT)
            handler.setFormatter(formatter)
            root = logging.getLogger()
            if not configured:
                root.handlers.clear()
            root.addHandler(handler)
            level_name = os.getenv("SWITCHBOARD_LOGGING_LEVEL", "INFO")
            root.setLevel(getattr(logging, level_name.upper(), logging.INFO))
            configured = True

    if not _STATE.request_filter_installed:
        logging.getLogger().addFilter(RequestIdFilter())
        _STATE.request_filter_installed = True
        filter_installed = True

    _STATE.configured = configured
    _STATE.initialized = True
    return configured or filter_installed


def setup_logging(app: FastAPI, header_name: str | None = None) -> bool:
    """Attach request ID middleware when enabled.

    The middleware is enabled by default but can be disabled via the
    ``SWITCHBOARD_ENABLE_REQUEST_ID`` environment variable. Returns ``True`` when
    the middleware is installed for the provided ``app``.
    """

    if app in _INSTRUMENTED_APPS:
        return True

    if not _truthy_env("SWITCHBOARD_ENABLE_REQUEST_ID", default=True):
        return False

    header = header_name or os.getenv(
        "SWITCHBOARD_REQUEST_ID_HEADER", DEFAULT_REQUEST_ID_HEADER
    )

    for middleware in app.user_middleware:
        if getattr(middleware, "cls", None) is RequestIdMiddleware:
            _INSTRUMENTED_APPS.add(app)
            return True

    app.add_middleware(RequestIdMiddleware, header_name=header)
    _INSTRUMENTED_APPS.add(app)
    return True


def get_request_id() -> str:
    """Return the current request ID for logging context."""

    return _REQUEST_ID_CTX.get("-")


def get_trace_id() -> str:
    """Return the current trace identifier for logging context."""

    return _TRACE_ID_CTX.get("-")
