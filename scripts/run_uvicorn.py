#!/usr/bin/env python3
"""Convenience wrapper around ``uvicorn`` for local development."""

from __future__ import annotations

import argparse
import os

import uvicorn.main


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
    default_host = os.getenv("UVICORN_HOST", "127.0.0.1")
    parser.add_argument(
        "--host",
        default=default_host,
        help=(
            "Host interface to bind (default: %(default)s). "
            "Use 0.0.0.0 only on trusted networks."
        ),
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


def build_args(args: argparse.Namespace) -> list[str]:
    extra_args = args.uvicorn_args or []
    if extra_args and extra_args[0] == "--":
        extra_args = extra_args[1:]

    command: list[str] = [
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
    cli_args = build_args(args)
    try:
        uvicorn.main.main(cli_args)
    except SystemExit as exc:  # uvicorn exits via SystemExit
        code = int(exc.code or 0)
        return code
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
