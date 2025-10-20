"""Server configuration helpers for environment-driven settings."""

from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache


class RateLimitConfigurationError(ValueError):
    """Raised when rate limit environment variables are invalid."""


RATE_LIMIT_REQUESTS_ENV = "SWITCHBOARD_RATE_LIMIT_REQUESTS"
RATE_LIMIT_WINDOW_ENV = "SWITCHBOARD_RATE_LIMIT_WINDOW_SECONDS"
RATE_LIMIT_TRUSTED_ENV = "SWITCHBOARD_RATE_LIMIT_TRUSTED_BYPASS"
RATE_LIMIT_TRUSTED_PROXIES_ENV = "SWITCHBOARD_RATE_LIMIT_TRUSTED_PROXIES"

_DEFAULT_REQUESTS = 120
_DEFAULT_WINDOW_SECONDS = 60


@dataclass(frozen=True)
class RateLimitSettings:
    """Configuration values that control the request rate limiter."""

    requests: int
    window_seconds: int
    trusted_bypass: frozenset[str]
    trusted_proxies: frozenset[str]

    @property
    def enabled(self) -> bool:
        """Return True when rate limiting is active."""

        return self.requests > 0 and self.window_seconds > 0


def _parse_int(name: str, value: str | None, default: int) -> int:
    if value is None:
        return default
    try:
        parsed = int(value)
    except (TypeError, ValueError) as exc:
        raise RateLimitConfigurationError(
            f"{name} must be a non-negative integer; got {value!r}"
        ) from exc
    if parsed < 0:
        raise RateLimitConfigurationError(
            f"{name} must be a non-negative integer; got {value!r}"
        )
    return parsed


def _parse_trusted(raw: str | None) -> frozenset[str]:
    if not raw:
        return frozenset()
    items = [item.strip() for item in raw.split(",")]
    return frozenset(item for item in items if item)


@lru_cache(maxsize=1)
def get_rate_limit_settings() -> RateLimitSettings:
    """Load rate limit settings from environment variables."""

    requests = _parse_int(
        RATE_LIMIT_REQUESTS_ENV,
        os.getenv(RATE_LIMIT_REQUESTS_ENV),
        _DEFAULT_REQUESTS,
    )
    window = _parse_int(
        RATE_LIMIT_WINDOW_ENV,
        os.getenv(RATE_LIMIT_WINDOW_ENV),
        _DEFAULT_WINDOW_SECONDS,
    )
    trusted = _parse_trusted(os.getenv(RATE_LIMIT_TRUSTED_ENV))
    proxies = _parse_trusted(os.getenv(RATE_LIMIT_TRUSTED_PROXIES_ENV))
    return RateLimitSettings(
        requests=requests,
        window_seconds=window,
        trusted_bypass=trusted,
        trusted_proxies=proxies,
    )


def reload_rate_limit_settings() -> RateLimitSettings:
    """Clear cached configuration and return reloaded settings.

    Intended for tests and hot-reload scenarios.
    """

    get_rate_limit_settings.cache_clear()
    return get_rate_limit_settings()
