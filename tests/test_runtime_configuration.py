"""Tests for the runtime configuration helpers used by the CLI."""

from __future__ import annotations

from client.python.runtime_config import (
    DEFAULT_HEARTBEAT_INTERVAL,
    RuntimeConfiguration,
    compute_backoff_interval,
    derive_runtime_configuration,
)


def test_derive_runtime_configuration_with_valid_payload() -> None:
    config = derive_runtime_configuration(
        requested_heartbeat_interval=15.0,
        poll_interval=5.0,
        max_poll_interval=20.0,
        backoff_multiplier=2.0,
        lease_settings={"lease": {"duration_seconds": 180}},
    )

    assert isinstance(config, RuntimeConfiguration)
    assert config.lease_duration == 180.0
    assert config.heartbeat_interval == 15.0
    assert config.heartbeat_reason is None
    assert config.poll_interval == 5.0
    assert config.max_poll_interval == 20.0
    assert config.backoff_multiplier == 2.0
    assert not config.warnings
    assert config.maintenance_mode is False
    assert config.maintenance_message is None


def test_derive_runtime_configuration_sanitizes_inputs() -> None:
    config = derive_runtime_configuration(
        requested_heartbeat_interval=-5.0,
        poll_interval=-2.0,
        max_poll_interval=-1.0,
        backoff_multiplier=0.0,
        lease_settings={"lease": {"duration_seconds": 60}},
    )

    assert config.lease_duration == 60.0
    assert config.heartbeat_interval == 30.0
    assert config.heartbeat_reason and "non-positive" in config.heartbeat_reason
    assert config.poll_interval == 0.0
    assert config.max_poll_interval == 0.0
    assert config.backoff_multiplier == 1.0
    assert "poll interval was negative" in config.warnings[0]
    assert any("max poll interval" in warning for warning in config.warnings)
    assert config.maintenance_mode is False
    assert config.maintenance_message is None
    assert any("backoff multiplier" in warning for warning in config.warnings)


def test_derive_runtime_configuration_carries_forward_warnings() -> None:
    config = derive_runtime_configuration(
        requested_heartbeat_interval=None,
        poll_interval=DEFAULT_HEARTBEAT_INTERVAL,
        max_poll_interval=None,
        backoff_multiplier=1.0,
        lease_settings=None,
        warnings=("pre-existing",),
    )

    assert config.lease_duration is None
    assert config.heartbeat_interval == DEFAULT_HEARTBEAT_INTERVAL
    assert config.warnings == ("pre-existing",)
    assert config.maintenance_mode is False
    assert config.maintenance_message is None


def test_derive_runtime_configuration_includes_system_state() -> None:
    config = derive_runtime_configuration(
        requested_heartbeat_interval=None,
        poll_interval=10.0,
        max_poll_interval=20.0,
        backoff_multiplier=2.0,
        lease_settings=None,
        system_state={"maintenance_mode": True, "message": "Upgrading"},
    )

    assert config.maintenance_mode is True
    assert config.maintenance_message == "Upgrading"


def test_compute_backoff_interval_delegates_to_runtime_helper() -> None:
    assert compute_backoff_interval(10.0, 0, max_interval=60.0, multiplier=2.0) == 10.0
    assert compute_backoff_interval(10.0, 1, max_interval=60.0, multiplier=2.0) == 10.0
    assert compute_backoff_interval(10.0, 2, max_interval=60.0, multiplier=2.0) == 20.0
    assert compute_backoff_interval(10.0, 3, max_interval=60.0, multiplier=2.0) == 40.0
    assert compute_backoff_interval(15.0, 4, max_interval=40.0, multiplier=3.0) == 40.0
    assert compute_backoff_interval(12.0, 5, max_interval=30.0, multiplier=1.0) == 12.0
