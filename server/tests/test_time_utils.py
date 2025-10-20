from __future__ import annotations

from datetime import datetime, timezone

import pytest

from server.time_utils import (
    override_time_provider,
    reset_time_provider,
    set_time_provider,
    utcnow,
    utcnow_naive,
)


def test_override_time_provider_yields_fixed_timestamp():
    moment = datetime(2024, 1, 1, 12, 30, tzinfo=timezone.utc)
    with override_time_provider(lambda: moment):
        assert utcnow() == moment
        assert utcnow_naive() == moment.replace(tzinfo=None)
    assert utcnow().tzinfo is timezone.utc


def test_set_time_provider_requires_datetime():
    token = set_time_provider(lambda: datetime(2023, 6, 1, tzinfo=timezone.utc))
    try:
        assert utcnow() == datetime(2023, 6, 1, tzinfo=timezone.utc)
    finally:
        reset_time_provider(token)
    assert utcnow().tzinfo is timezone.utc


def test_set_time_provider_rejects_non_datetime():
    token = set_time_provider(lambda: "not-a-datetime")  # type: ignore
    try:
        with pytest.raises(TypeError):
            utcnow()
    finally:
        reset_time_provider(token)
