"""Server configuration helpers for environment-driven settings."""

from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache


class RateLimitConfigurationError(ValueError):
    """Raised when rate limit environment variables are invalid."""


class LeaseConfigurationError(ValueError):
    """Raised when lease environment variables are invalid."""


RATE_LIMIT_REQUESTS_ENV = "SWITCHBOARD_RATE_LIMIT_REQUESTS"
RATE_LIMIT_WINDOW_ENV = "SWITCHBOARD_RATE_LIMIT_WINDOW_SECONDS"
RATE_LIMIT_TRUSTED_ENV = "SWITCHBOARD_RATE_LIMIT_TRUSTED_BYPASS"
RATE_LIMIT_TRUSTED_PROXIES_ENV = "SWITCHBOARD_RATE_LIMIT_TRUSTED_PROXIES"

LEASE_SECONDS_ENV = "SWITCHBOARD_LEASE_SECONDS"
ADMIN_TOKEN_ENV = "SWITCHBOARD_ADMIN_TOKEN"  # noqa: S105 - environment variable name
EXTENSION_MODULES_ENV = "SWITCHBOARD_EXTENSIONS"
ENABLE_BUILTIN_EXTENSIONS_ENV = "SWITCHBOARD_ENABLE_BUILTIN_EXTENSIONS"

_DEFAULT_REQUESTS = 120
_DEFAULT_WINDOW_SECONDS = 60
_DEFAULT_LEASE_SECONDS = 300


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


@dataclass(frozen=True)
class LeaseSettings:
    """Configuration values that control task lease duration."""

    duration_seconds: int


@dataclass(frozen=True)
class ExtensionSettings:
    """Configuration describing extension modules and builtin toggles."""

    modules: tuple[str, ...]
    enable_builtin: bool


@dataclass(frozen=True)
class SettingsBundle:
    """Aggregated configuration values for the settings endpoint."""

    rate_limit: RateLimitSettings
    lease: LeaseSettings
    extensions: ExtensionSettings


def _parse_int(
    name: str,
    value: str | None,
    default: int,
    *,
    error_type: type[ValueError] = RateLimitConfigurationError,
    allow_zero: bool = True,
) -> int:
    if value is None:
        return default
    requirement = (
        "a non-negative integer"
        if allow_zero
        else "a positive integer"
    )
    try:
        parsed = int(value)
    except (TypeError, ValueError) as exc:
        raise error_type(f"{name} must be {requirement}; got {value!r}") from exc
    if parsed < 0 or (not allow_zero and parsed == 0):
        raise error_type(f"{name} must be {requirement}; got {value!r}")
    return parsed


def _parse_trusted(raw: str | None) -> frozenset[str]:
    if not raw:
        return frozenset()
    items = [item.strip() for item in raw.split(",")]
    return frozenset(item for item in items if item)


def _parse_extensions(raw: str | None) -> tuple[str, ...]:
    if not raw:
        return ()
    modules = []
    for entry in raw.split(","):
        candidate = entry.strip()
        if not candidate:
            continue
        if candidate not in modules:
            modules.append(candidate)
    return tuple(modules)


def _truthy(value: str | None, *, default: bool = False) -> bool:
    if value is None:
        return default
    return value.lower() in {"1", "true", "yes", "on"}


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
    settings = get_rate_limit_settings()
    reload_settings_bundle()
    return settings


@lru_cache(maxsize=1)
def get_lease_settings() -> LeaseSettings:
    """Load lease duration settings from environment variables."""

    duration = _parse_int(
        LEASE_SECONDS_ENV,
        os.getenv(LEASE_SECONDS_ENV),
        _DEFAULT_LEASE_SECONDS,
        error_type=LeaseConfigurationError,
        allow_zero=False,
    )
    return LeaseSettings(duration_seconds=duration)


def reload_lease_settings() -> LeaseSettings:
    """Clear cached lease configuration and return the reloaded value."""

    get_lease_settings.cache_clear()
    settings = get_lease_settings()
    reload_settings_bundle()
    return settings


@lru_cache(maxsize=1)
def get_extension_settings() -> ExtensionSettings:
    """Return extension configuration derived from environment variables."""

    modules = _parse_extensions(os.getenv(EXTENSION_MODULES_ENV))
    enabled = _truthy(os.getenv(ENABLE_BUILTIN_EXTENSIONS_ENV), default=True)
    return ExtensionSettings(modules=modules, enable_builtin=enabled)


def reload_extension_settings() -> ExtensionSettings:
    """Clear cached extension configuration and return the refreshed values."""

    get_extension_settings.cache_clear()
    settings = get_extension_settings()
    # Ensure the runtime extension bundle stays in sync with the refreshed settings.
    from server.extensions.runtime import reload_extensions

    reload_extensions(modules=settings.modules)
    reload_settings_bundle()
    return settings


@lru_cache(maxsize=1)
def get_settings_bundle() -> SettingsBundle:
    """Return an aggregated snapshot of rate limit and lease configuration."""

    return SettingsBundle(
        rate_limit=get_rate_limit_settings(),
        lease=get_lease_settings(),
        extensions=get_extension_settings(),
    )


def reload_settings_bundle() -> SettingsBundle:
    """Clear the cached bundle and return an up-to-date snapshot."""

    get_extension_settings.cache_clear()
    get_settings_bundle.cache_clear()
    return get_settings_bundle()


@lru_cache(maxsize=1)
def get_admin_token() -> str | None:
    """Return the configured admin token if present."""

    token = os.getenv(ADMIN_TOKEN_ENV)
    if token:
        return token.strip() or None
    return None


def reload_admin_token() -> str | None:
    """Clear the cached admin token value and return the new value."""

    get_admin_token.cache_clear()
    return get_admin_token()
