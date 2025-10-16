#!/usr/bin/env python3
"""Convenience wrapper around ``pytest`` with project defaults."""

from __future__ import annotations

import argparse
import subprocess
import sys
from typing import List


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


def build_command(args: argparse.Namespace) -> List[str]:
    extra_args = args.pytest_args or []
    if extra_args and extra_args[0] == "--":
        extra_args = extra_args[1:]

    command: List[str] = [
        sys.executable,
        "-m",
        "pytest",
        args.path,
    ]
    command.extend(extra_args)
    return command


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    command = build_command(args)
    completed = subprocess.run(command, check=False)
    return completed.returncode


if __name__ == "__main__":
    raise SystemExit(main())
