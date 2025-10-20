from client.python.switchboard_cli import compute_backoff_interval


def test_compute_backoff_interval_defaults_to_base_interval() -> None:
    assert compute_backoff_interval(10.0, 0, max_interval=60.0, multiplier=2.0) == 10.0
    assert compute_backoff_interval(10.0, 1, max_interval=60.0, multiplier=2.0) == 10.0


def test_compute_backoff_interval_scales_with_multiplier() -> None:
    assert compute_backoff_interval(10.0, 2, max_interval=60.0, multiplier=2.0) == 20.0
    assert compute_backoff_interval(10.0, 3, max_interval=60.0, multiplier=2.0) == 40.0


def test_compute_backoff_interval_respects_maximum() -> None:
    assert compute_backoff_interval(15.0, 4, max_interval=40.0, multiplier=3.0) == 40.0


def test_compute_backoff_interval_handles_multiplier_below_one() -> None:
    assert compute_backoff_interval(12.0, 5, max_interval=30.0, multiplier=1.0) == 12.0
