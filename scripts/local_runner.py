"""Local agent runner that exercises the Switchboard orchestration router."""

from __future__ import annotations

import argparse
import logging
import sys
import time
from typing import Any

from client.python.switchboard_client import SwitchboardClient

LOGGER = logging.getLogger("switchboard.local_runner")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse command-line arguments for the local runner.

    Parameters
    ----------
    argv:
        Optional argument vector; defaults to :data:`sys.argv` when ``None``.

    Returns
    -------
    argparse.Namespace
        Parsed arguments controlling runner behaviour.
    """

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--base-url",
        default="http://localhost:8000",
        help="Root URL of the Switchboard server (default: %(default)s)",
    )
    parser.add_argument(
        "--agent-id",
        default="local-runner",
        help="Identifier used when registering the agent (default: %(default)s)",
    )
    parser.add_argument(
        "--poll-interval",
        type=float,
        default=5.0,
        help="Seconds to wait before rechecking the queue when no tasks are available",
    )
    parser.add_argument(
        "--heartbeat-interval",
        type=float,
        default=20.0,
        help="Seconds between heartbeats when running without auto-completion",
    )
    parser.add_argument(
        "--auto-complete",
        action="store_true",
        help="Automatically complete tasks after checkout instead of heartbeating",
    )
    parser.add_argument(
        "--completion-notes",
        default="Completed by local runner.",
        help="Notes stored when --auto-complete is enabled (default: %(default)s)",
    )
    parser.add_argument(
        "--once",
        action="store_true",
        help="Exit after a single checkout attempt (useful for smoke tests)",
    )
    return parser.parse_args(argv)


def _log_task(task: dict[str, Any]) -> None:
    """Log a concise representation of the checked-out task.

    Parameters
    ----------
    task:
        Task payload returned by :meth:`SwitchboardClient.checkout`.
    """

    task_id = task.get("id")
    title = task.get("title", "<missing title>")
    LOGGER.info("Checked out task %s — %s", task_id, title)


def _perform_heartbeat(
    client: SwitchboardClient, task_id: int, interval: float
) -> None:
    """Send a heartbeat loop for a task until interrupted.

    Parameters
    ----------
    client:
        Initialized Switchboard client.
    task_id:
        Identifier of the task being heartbeated.
    interval:
        Number of seconds to wait between heartbeats.
    """

    LOGGER.info("Starting heartbeat loop for task %s", task_id)
    try:
        while True:
            success = client.heartbeat(task_id)
            LOGGER.debug("Heartbeat for %s returned ok=%s", task_id, success)
            time.sleep(max(interval, 0.1))
    except KeyboardInterrupt:
        LOGGER.info("Heartbeat loop interrupted for task %s", task_id)


def main(argv: list[str] | None = None) -> int:
    """Entry point that runs the local agent loop.

    Parameters
    ----------
    argv:
        Optional argument vector; defaults to :data:`sys.argv` when ``None``.

    Returns
    -------
    int
        Process exit code (``0`` on success).
    """
 
    args = parse_args(argv)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )
    LOGGER.debug("Parsed arguments: %s", args)

    with SwitchboardClient(args.base_url, args.agent_id) as client:
        LOGGER.info("Registered agent %s against %s", args.agent_id, args.base_url)
        while True:
            task = client.checkout()
            if task:
                _log_task(task)
                task_id = int(task["id"])
                if args.auto_complete:
                    notes = args.completion_notes
                    success = client.complete(task_id, notes=notes)
                    LOGGER.info(
                        "Completed task %s (success=%s) with notes: %s",
                        task_id,
                        success,
                        notes,
                    )
                else:
                    LOGGER.info(
                        (
                            "Starting heartbeat maintenance for task %s — "
                            "press Ctrl+C to stop"
                        ),
                        task_id,
                    )
                    _perform_heartbeat(client, task_id, args.heartbeat_interval)
            else:
                LOGGER.info(
                    "No task available (reason=%s); sleeping for %.1f seconds",
                    client.last_checkout_reason,
                    args.poll_interval,
                )
                time.sleep(max(args.poll_interval, 0.5))

            if args.once:
                break

    return 0
 

if __name__ == "__main__":  # pragma: no cover - CLI entry point
    sys.exit(main())
