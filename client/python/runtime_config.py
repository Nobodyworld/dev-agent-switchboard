"""Runtime configuration helpers shared by the Switchboard CLI."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass

DEFAULT_MAX_POLL_INTERVAL = 120.0
DEFAULT_HEARTBEAT_INTERVAL = 30.0


@dataclass(frozen=True)
class RuntimeConfiguration:
    """Derived runtime parameters used by the interactive CLI loop.

    Attributes
    ----------
    heartbeat_interval:
        Interval in seconds between automatic heartbeats while a task lease is
        held.
    heartbeat_reason:
        Optional explanatory message describing why the heartbeat interval was
        adjusted from the requested value.
    poll_interval:
        Baseline interval in seconds for polling checkout requests.
    max_poll_interval:
        Upper bound for exponential backoff when no tasks are available.
    backoff_multiplier:
        Exponential backoff multiplier applied after consecutive checkout
        misses.
    lease_duration:
        Lease duration reported by the server when available.
    warnings:
        Normalised warnings surfaced during configuration derivation.
    maintenance_mode:
        ``True`` when server-side maintenance mode is enabled.
    maintenance_message:
        Optional human-readable message supplied by the operator.
    max_heartbeats:
        Optional upper bound on automatic heartbeats before abandoning a task.
    """

    heartbeat_interval: float
    heartbeat_reason: str | None
    poll_interval: float
    max_poll_interval: float
    backoff_multiplier: float
    lease_duration: float | None
    warnings: tuple[str, ...]
    maintenance_mode: bool
    maintenance_message: str | None
    max_heartbeats: int | None


WarningSequence = Iterable[str]


def sanitize_heartbeat_interval(
    requested_interval: float | None,
    lease_seconds: float | None,
    *,
    default_interval: float = DEFAULT_HEARTBEAT_INTERVAL,
) -> tuple[float, str | None]:
    """Return a safe heartbeat interval and optional adjustment explanation.

    Parameters
    ----------
    requested_interval:
        Interval requested by the user. ``None`` means use the default.
    lease_seconds:
        Lease duration reported by the server, if known.
    default_interval:
        Default heartbeat cadence applied when no override is provided.

    Returns
    -------
    tuple[float, str | None]
        A tuple of the sanitized interval and an optional reason string when
        the input required adjustment.
    """

    interval = (
        default_interval if requested_interval is None else float(requested_interval)
    )
    interval = max(interval, 0.0)
    if lease_seconds is None or lease_seconds <= 0:
        if interval <= 0:
            return default_interval, "using default heartbeat interval"
        return interval, None

    lease = float(lease_seconds)
    if interval <= 0:
        adjusted = max(lease / 2.0, 1.0)
        return (
            adjusted,
            (
                "requested heartbeat interval was non-positive; "
                "using half the lease duration"
            ),
        )
    if interval >= lease:
        adjusted = max(lease / 2.0, 1.0)
        return (
            adjusted,
            (
                "requested heartbeat interval would exceed the lease duration; "
                "using half the lease instead"
            ),
        )
    return interval, None


def extract_lease_duration(
    settings_payload: Mapping[str, object] | None,
) -> tuple[float | None, list[str]]:
    """Parse ``settings_payload`` and return ``(lease_seconds, warnings)``."""

    warnings: list[str] = []
    if not isinstance(settings_payload, Mapping):
        warnings.append("settings payload was not a mapping")
        return None, warnings

    lease_block = settings_payload.get("lease")
    if lease_block is None:
        warnings.append("settings payload did not include lease information")
        return None, warnings

    if not isinstance(lease_block, Mapping):
        warnings.append("lease section was not a mapping")
        return None, warnings

    value = lease_block.get("duration_seconds")
    if isinstance(value, (int, float)):
        if value > 0:
            return float(value), warnings
        warnings.append(
            "lease duration from server was non-positive; ignoring unsafe value"
        )
        return None, warnings

    if value is not None:
        warnings.append("lease duration was not numeric; ignoring value")
    else:
        warnings.append("lease duration missing from lease settings")
    return None, warnings


def compute_backoff_interval(
    base_interval: float,
    misses: int,
    *,
    max_interval: float,
    multiplier: float,
) -> float:
    """Return the next poll interval using exponential backoff."""

    if misses <= 1 or multiplier <= 1.0:
        return max(base_interval, 0.0)
    candidate = base_interval * (multiplier ** (misses - 1))
    return min(max_interval, max(candidate, base_interval, 0.0))


def derive_runtime_configuration(  # noqa: PLR0913 - CLI config derivation requires explicit knobs
    *,
    requested_heartbeat_interval: float | None,
    poll_interval: float,
    max_poll_interval: float | None,
    backoff_multiplier: float,
    lease_settings: Mapping[str, object] | None,
    system_state: Mapping[str, object] | None = None,
    warnings: WarningSequence = (),
    max_heartbeats: int | None = None,
) -> RuntimeConfiguration:
    """Derive sanitized runtime values for the interactive CLI loop."""

    base_warnings = tuple(warnings)
    if lease_settings is None:
        lease_seconds: float | None = None
        lease_warnings: list[str] = []
    else:
        lease_seconds, lease_warnings = extract_lease_duration(lease_settings)
    all_warnings: tuple[str, ...] = (*base_warnings, *lease_warnings)

    heartbeat_interval, heartbeat_reason = sanitize_heartbeat_interval(
        requested_heartbeat_interval, lease_seconds
    )

    sanitized_poll = max(float(poll_interval), 0.0)
    if sanitized_poll != poll_interval:
        all_warnings += ("poll interval was negative; using 0 seconds",)

    if max_poll_interval is None:
        sanitized_max_poll = sanitized_poll
    else:
        sanitized_max_poll = max(float(max_poll_interval), sanitized_poll)
        if sanitized_max_poll != max_poll_interval:
            all_warnings += (
                "max poll interval was lower than the base interval; "
                "using the base interval",
            )

    sanitized_backoff = max(float(backoff_multiplier), 1.0)
    if sanitized_backoff != backoff_multiplier:
        all_warnings += (
            "backoff multiplier was less than one; using a multiplier of 1.0",
        )

    maintenance_enabled = False
    maintenance_message: str | None = None
    if isinstance(system_state, Mapping):
        maintenance_enabled = bool(system_state.get("maintenance_mode"))
        raw_message = system_state.get("message")
        if isinstance(raw_message, str):
            maintenance_message = raw_message.strip() or None

    sanitized_max_heartbeats: int | None = None
    if max_heartbeats is not None:
        try:
            candidate = int(max_heartbeats)
        except (TypeError, ValueError):
            candidate = 0
        if candidate <= 0:
            all_warnings += (
                "max heartbeats must be a positive integer; disabling auto abandonment",
            )
        else:
            sanitized_max_heartbeats = candidate

    return RuntimeConfiguration(
        heartbeat_interval=heartbeat_interval,
        heartbeat_reason=heartbeat_reason,
        poll_interval=sanitized_poll,
        max_poll_interval=sanitized_max_poll,
        backoff_multiplier=sanitized_backoff,
        lease_duration=lease_seconds,
        warnings=all_warnings,
        maintenance_mode=maintenance_enabled,
        maintenance_message=maintenance_message,
        max_heartbeats=sanitized_max_heartbeats,
    )


__all__ = [
    "DEFAULT_HEARTBEAT_INTERVAL",
    "DEFAULT_MAX_POLL_INTERVAL",
    "RuntimeConfiguration",
    "compute_backoff_interval",
    "derive_runtime_configuration",
    "extract_lease_duration",
    "sanitize_heartbeat_interval",
]
