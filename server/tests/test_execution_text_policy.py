# ruff: noqa: S108 - literal unsafe path shapes are the policy inputs under test
"""Focused boundary coverage for API-safe local-path detection."""

from __future__ import annotations

import pytest

from server.execution.text_policy import (
    contains_absolute_local_path,
    validate_no_absolute_local_paths,
)


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
        "nested/relative.txt",
        "https://example.invalid/path",
        "git://example.test/repository",
        "urn:example:value",
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
        "C:/worker/result.json",
        r"\\server\share\result.json",
        "file:///tmp/result.json",
        "sqlite:///tmp/result.db",
        "sqlite+aiosqlite:///tmp/result.db",
    ],
)
def test_genuine_local_absolute_paths_remain_rejected(value: str) -> None:
    assert contains_absolute_local_path(value) is True


@pytest.mark.parametrize(
    "value",
    [
        {"nested": {"path": "/tmp/result.json"}},
        {"nested": ["safe", r"C:\worker\result.json"]},
        ["safe", {"database": "sqlite+aiosqlite:///tmp/result.db"}],
    ],
)
def test_recursive_policy_rejects_nested_local_values(value: object) -> None:
    with pytest.raises(ValueError, match="absolute local path"):
        validate_no_absolute_local_paths(value)
