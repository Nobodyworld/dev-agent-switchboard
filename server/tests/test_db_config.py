"""Tests for database configuration helpers."""

import pytest

from server.db import DatabaseConfigurationError, engine_options_from_env


def test_engine_options_defaults_are_sane():
    options = engine_options_from_env({})
    assert options == {"echo": False, "future": True}


def test_engine_options_supports_overrides():
    pool_size = 5
    max_overflow = 2
    pool_timeout = 30.5
    pool_recycle = 3600
    env = {
        "DATABASE_ECHO": "true",
        "DATABASE_POOL_PRE_PING": "1",
        "DATABASE_POOL_SIZE": str(pool_size),
        "DATABASE_MAX_OVERFLOW": str(max_overflow),
        "DATABASE_POOL_TIMEOUT": str(pool_timeout),
        "DATABASE_POOL_RECYCLE": str(pool_recycle),
    }
    options = engine_options_from_env(env)
    assert options["echo"] is True
    assert options["pool_pre_ping"] is True
    assert options["pool_size"] == pool_size
    assert options["max_overflow"] == max_overflow
    assert options["pool_timeout"] == pytest.approx(pool_timeout)
    assert options["pool_recycle"] == pool_recycle
    assert options["future"] is True


@pytest.mark.parametrize(
    "env",
    [
        {"DATABASE_POOL_SIZE": "0"},
        {"DATABASE_POOL_SIZE": "-1"},
        {"DATABASE_MAX_OVERFLOW": "-5"},
        {"DATABASE_POOL_TIMEOUT": "-2"},
        {"DATABASE_POOL_RECYCLE": "-10"},
        {"DATABASE_ECHO": "maybe"},
    ],
)
def test_engine_options_invalid_values_raise(env):
    with pytest.raises(DatabaseConfigurationError):
        engine_options_from_env(env)
