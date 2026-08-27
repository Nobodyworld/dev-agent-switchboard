# ruff: noqa: S108 - literal unsafe path shapes are the policy inputs under test
"""Focused boundary coverage for API-safe local-path detection."""

from __future__ import annotations

import pytest

from server.execution.text_policy import contains_absolute_local_path


@pytest.mark.parametrize(
    "value",
    [
        "tmp_path / child",
        'tmp_path / "child.pid"',
        "left / right",
        "1 / 2",
        "logs/tests.stdout.log",
        "./relative/path",
        "../relative/path",
        "https://example.test/results/1",
        "git://example.test/repository",
    ],
)
def test_safe_slash_shapes_are_not_local_absolute_paths(value: str) -> None:
    assert contains_absolute_local_path(value) is False


@pytest.mark.parametrize(
    "value",
    [
        "/",
        "/tmp",
        "/tmp/child.pid",
        "retained at /var/log/switchboard.log",
        r"C:\worker\result.json",
        r"\\server\share\result.json",
        "file:///tmp/result.json",
    ],
)
def test_genuine_local_absolute_paths_remain_rejected(value: str) -> None:
    assert contains_absolute_local_path(value) is True
