#!/usr/bin/env python3
"""Convenience wrapper around ``uvicorn`` for local development."""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from typing import List


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Start the Switchboard FastAPI app with sensible development defaults. "
            "Additional arguments after ``--`` are forwarded to uvicorn."
        )
    )
    parser.add_argument(
        "--app",
        default="server.app:app",
        help="Dotted path to the ASGI app (default: %(default)s).",
    )
    parser.add_argument(
        "--host",
        default=os.getenv("UVICORN_HOST", "0.0.0.0"),
        help="Host interface to bind (default: %(default)s).",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=int(os.getenv("UVICORN_PORT", "8000")),
        help="Port to bind (default: %(default)s).",
    )
    parser.add_argument(
        "--reload/--no-reload",
        dest="reload",
        default=True,
        help="Toggle uvicorn's reload flag (default: --reload).",
    )
    parser.add_argument(
        "uvicorn_args",
        nargs=argparse.REMAINDER,
        help="Arguments forwarded directly to uvicorn (prefix with --).",
    )
    return parser.parse_args(argv)


def build_command(args: argparse.Namespace) -> List[str]:
    extra_args = args.uvicorn_args or []
    if extra_args and extra_args[0] == "--":
        extra_args = extra_args[1:]

    command: List[str] = [
        sys.executable,
        "-m",
        "uvicorn",
        args.app,
        "--host",
        args.host,
        "--port",
        str(args.port),
    ]
    if args.reload:
        command.append("--reload")
    command.extend(extra_args)
    return command


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    command = build_command(args)
    try:
        completed = subprocess.run(command, check=False)
    except KeyboardInterrupt:
        return 1
    return completed.returncode


if __name__ == "__main__":
    raise SystemExit(main())
