#!/usr/bin/env python3
"""Convenience wrapper around ``pytest`` with project defaults."""

from __future__ import annotations

import argparse

import pytest


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Run the Switchboard test suite. Additional arguments after ``--`` "
            "are forwarded directly to pytest."
        )
    )
    parser.add_argument(
        "--path",
        default="server/tests",
        help="Default path or expression to test (default: %(default)s).",
    )
    parser.add_argument(
        "pytest_args",
        nargs=argparse.REMAINDER,
        help="Arguments forwarded to pytest (prefix with --).",
    )
    return parser.parse_args(argv)


def build_args(args: argparse.Namespace) -> list[str]:
    extra_args = args.pytest_args or []
    if extra_args and extra_args[0] == "--":
        extra_args = extra_args[1:]

    command: list[str] = [args.path]
    command.extend(extra_args)
    return command


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    pytest_args = build_args(args)
    return pytest.main(pytest_args)


if __name__ == "__main__":
    raise SystemExit(main())
