"""Internal graceful wrapper for the operator-owned loopback server process."""

from __future__ import annotations

import argparse
import asyncio
from pathlib import Path

import uvicorn


async def _watch_stop(server: uvicorn.Server, stop_file: Path) -> None:
    while not server.should_exit:
        if stop_file.is_file():  # noqa: ASYNC240 - bounded local marker poll
            server.should_exit = True
            return
        await asyncio.sleep(0.1)


async def _serve(host: str, port: int, stop_file: Path) -> None:
    configuration = uvicorn.Config(
        "server.app:app",
        host=host,
        port=port,
        log_level="warning",
        access_log=False,
    )
    server = uvicorn.Server(configuration)
    watcher = asyncio.create_task(_watch_stop(server, stop_file))
    try:
        await server.serve()
    finally:
        watcher.cancel()
        await asyncio.gather(watcher, return_exceptions=True)


def main() -> int:
    parser = argparse.ArgumentParser(description="Run one operator-owned server")
    parser.add_argument(
        "--host", choices=("127.0.0.1", "::1", "localhost"), required=True
    )
    parser.add_argument("--port", type=int, choices=range(1024, 65536), required=True)
    parser.add_argument("--stop-file", type=Path, required=True)
    arguments = parser.parse_args()
    if not arguments.stop_file.is_absolute() or arguments.stop_file.exists():
        parser.error("--stop-file must be an absent absolute path")
    asyncio.run(_serve(arguments.host, arguments.port, arguments.stop_file))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
