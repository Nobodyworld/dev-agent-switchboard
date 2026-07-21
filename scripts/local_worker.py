"""Launch the safe outbound local execution worker from operator JSON config.

The Phase-1 token is read exclusively from ``SWITCHBOARD_ADMIN_TOKEN``.
"""

from __future__ import annotations

import argparse
import json
import signal
import time
from pathlib import Path

from client.python.execution_worker.client import ExecutionClient
from client.python.execution_worker.config import WorkerConfig
from client.python.execution_worker.worker import LocalWorker


def main() -> int:
    parser = argparse.ArgumentParser(description="Run trusted local execution work")
    parser.add_argument(
        "--config", type=Path, required=True, help="operator-owned JSON (no token)"
    )
    parser.add_argument("--once", action="store_true", help="attempt a single checkout")
    arguments = parser.parse_args()
    config = WorkerConfig.from_mapping(
        json.loads(arguments.config.read_text(encoding="utf-8"))
    )
    with ExecutionClient(
        config.base_url, config.worker_id, config.admin_token
    ) as client:
        worker = LocalWorker(config, client)
        worker.start()
        signal.signal(signal.SIGINT, lambda _signal, _frame: worker.request_shutdown())
        if hasattr(signal, "SIGTERM"):
            signal.signal(
                signal.SIGTERM,
                lambda _signal, _frame: worker.request_shutdown(),
            )
        while True:
            worker.poll_once()
            if arguments.once or worker.shutting_down:
                client.heartbeat_worker(status="draining")
                return 0
            client.heartbeat_worker(status="online")
            time.sleep(config.poll_interval_seconds)


if __name__ == "__main__":
    raise SystemExit(main())
