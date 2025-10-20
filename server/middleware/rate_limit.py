"""ASGI middleware that enforces a simple request rate limit."""

from __future__ import annotations

import asyncio
import time
from collections import defaultdict, deque
from collections.abc import Awaitable
from typing import Callable, cast

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import PlainTextResponse, Response
from starlette.status import HTTP_429_TOO_MANY_REQUESTS

from server.settings import RateLimitSettings

SettingsProvider = Callable[[], RateLimitSettings]
RateLimitMetricsCallback = Callable[[str | None, RateLimitSettings], None]


def _noop_metrics_callback(_: str | None, __: RateLimitSettings) -> None:
    return None


_STATE: dict[str, object] = {
    "middleware": None,
    "metrics_callback": _noop_metrics_callback,
}

__all__ = [
    "RateLimitMiddleware",
    "SettingsProvider",
    "get_current_rate_limit_middleware",
    "set_rate_limit_metrics_callback",
]


def get_current_rate_limit_middleware() -> RateLimitMiddleware | None:
    """Return the active rate limit middleware instance if available."""

    return cast(RateLimitMiddleware | None, _STATE["middleware"])


def set_rate_limit_metrics_callback(
    callback: RateLimitMetricsCallback | None,
) -> None:
    """Install a callback invoked whenever a request is throttled."""

    _STATE["metrics_callback"] = callback or _noop_metrics_callback


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Limit requests per client IP over a sliding time window."""

    def __init__(self, app, *, settings_provider: SettingsProvider) -> None:  # type: ignore[override]
        super().__init__(app)
        self._settings_provider = settings_provider
        self._lock = asyncio.Lock()
        self._buckets: dict[str, deque[float]] = defaultdict(deque)
        _STATE["middleware"] = self

    def reset(self) -> None:
        """Clear tracked request state (useful for tests)."""

        self._buckets.clear()

    def _client_identifier(
        self, request: Request, settings: RateLimitSettings
    ) -> str | None:
        """Return the identifier used for rate-limiting decisions."""

        client_host = request.client.host if request.client else None
        if (
            client_host
            and client_host in settings.trusted_proxies
            and (forwarded := request.headers.get("x-forwarded-for"))
        ):
            first = forwarded.split(",", 1)[0].strip()
            if first:
                return first
        if client_host:
            return client_host
        if forwarded := request.headers.get("x-forwarded-for"):
            first = forwarded.split(",", 1)[0].strip()
            if first:
                return first
        return None

    def _should_bypass(
        self, settings: RateLimitSettings, identifier: str | None
    ) -> bool:
        """Return ``True`` when the identifier should bypass rate limiting."""

        return bool(identifier and identifier in settings.trusted_bypass)

    async def dispatch(
        self, request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:  # type: ignore[override]
        # Emit metrics for throttled requests so operators can monitor impact.
        settings = self._settings_provider()
        if not settings.enabled:
            return await call_next(request)

        identifier = self._client_identifier(request, settings)
        if self._should_bypass(settings, identifier):
            return await call_next(request)

        now = time.monotonic()
        window_start = now - settings.window_seconds

        async with self._lock:
            key = identifier or "unknown"
            bucket = self._buckets[key]
            while bucket and bucket[0] < window_start:
                bucket.popleft()
            if len(bucket) >= settings.requests:
                response = PlainTextResponse(
                    "Too Many Requests", status_code=HTTP_429_TOO_MANY_REQUESTS
                )
                response.headers.setdefault("Retry-After", str(settings.window_seconds))
                metrics_callback = cast(
                    RateLimitMetricsCallback, _STATE["metrics_callback"]
                )
                metrics_callback(identifier, settings)
                return response
            bucket.append(now)

        return await call_next(request)
