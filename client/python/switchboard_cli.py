"""Interactive command-line tooling for running Switchboard agents."""

import argparse
import json
import sys
import threading
import time
from collections.abc import Callable, Mapping
from typing import Any, Optional

import requests
from switchboard_client import SwitchboardClient

HEARTBEAT_SHUTDOWN_TIMEOUT = 5.0

TaskPayload = dict[str, Any]

DEFAULT_MAX_POLL_INTERVAL = 120.0
DEFAULT_HEARTBEAT_INTERVAL = 30.0

__all__ = [
    "DEFAULT_MAX_POLL_INTERVAL",
    "DEFAULT_HEARTBEAT_INTERVAL",
    "HEARTBEAT_SHUTDOWN_TIMEOUT",
    "HeartbeatLoop",
    "build_parser",
    "compute_backoff_interval",
    "extract_lease_duration",
    "format_task",
    "main",
    "process_task",
    "run_command",
    "sanitize_heartbeat_interval",
]


class HeartbeatLoop(threading.Thread):
    """Background thread that maintains task leases via heartbeats."""

    def __init__(
        self, client: SwitchboardClient, task_id: int, interval: float
    ) -> None:
        super().__init__(daemon=True)
        self._client = client
        self._task_id = task_id
        self._interval = interval
        self._stop = threading.Event()
        self._error: Optional[str] = None

    def run(self) -> None:
        while not self._stop.is_set():
            try:
                ok = self._client.heartbeat(self._task_id)
            except Exception as exc:  # pragma: no cover - network errors
                self._error = f"Heartbeat failed: {exc}"
                return
            if not ok:
                self._error = "Server rejected heartbeat"
                return
            if self._stop.wait(self._interval):
                return

    def stop(self) -> None:
        """Signal the heartbeat loop to stop sending requests."""

        self._stop.set()

    @property
    def error(self) -> Optional[str]:
        """Return the last error encountered by the heartbeat loop, if any."""

        return self._error


def format_task(task: TaskPayload) -> str:
    """Return a human-readable summary for ``task``."""

    depends = task.get("depends_on") or []
    lines = [
        f"Task {task['id']}: {task.get('title', '<no title>')}",
        task.get("description", "").strip() or "(no description)",
    ]
    if depends:
        lines.append("Depends on: " + ", ".join(str(d) for d in depends))
    return "\n".join(lines)


def sanitize_heartbeat_interval(
    requested_interval: Optional[float],
    lease_seconds: Optional[float],
) -> tuple[float, Optional[str]]:
    """Return a safe heartbeat interval and optional adjustment reason."""

    interval = DEFAULT_HEARTBEAT_INTERVAL if requested_interval is None else float(requested_interval)
    interval = max(interval, 0.0)
    if lease_seconds is None or lease_seconds <= 0:
        if interval <= 0:
            return DEFAULT_HEARTBEAT_INTERVAL, "using default heartbeat interval"
        return interval, None

    lease = float(lease_seconds)
    if interval <= 0:
        adjusted = max(lease / 2.0, 1.0)
        return adjusted, (
            "requested heartbeat interval was non-positive; using half the lease duration"
        )
    if interval >= lease:
        adjusted = max(lease / 2.0, 1.0)
        return adjusted, (
            "requested heartbeat interval would exceed the lease duration; using half the lease instead"
        )
    return interval, None


def extract_lease_duration(
    settings_payload: Mapping[str, Any] | None,
) -> tuple[Optional[float], list[str]]:
    """Parse ``settings_payload`` and return (lease_seconds, warnings)."""

    warnings: list[str] = []
    if not isinstance(settings_payload, Mapping):
        warnings.append("settings payload was not a mapping")
        return None, warnings

    lease_block = settings_payload.get("lease")
    if lease_block is None:
        warnings.append("settings payload did not include lease information")
        return None, warnings

    if not isinstance(lease_block, Mapping):
        warnings.append("lease section was not a mapping")
        return None, warnings

    value = lease_block.get("duration_seconds")
    if isinstance(value, (int, float)):
        if value > 0:
            return float(value), warnings
        warnings.append(
            "lease duration from server was non-positive; ignoring unsafe value"
        )
        return None, warnings

    if value is not None:
        warnings.append("lease duration was not numeric; ignoring value")
    else:
        warnings.append("lease duration missing from lease settings")
    return None, warnings


def process_task(
    client: SwitchboardClient,
    task: TaskPayload,
    heartbeat_interval: float,
) -> bool:
    """Interactively process ``task`` using the provided client."""

    task_id = task["id"]
    print()
    print(format_task(task))
    loop = HeartbeatLoop(client, task_id, heartbeat_interval)
    # The heartbeat thread keeps the lease alive while we wait for user input.
    # We always stop and join the thread in the finally block so the daemon
    # never leaks if the command exits early.
    loop.start()
    print(
        "Heartbeat thread started "
        f"(every {heartbeat_interval:.0f}s). "
        "Type 'help' for options."
    )
    notes: Optional[str] = None

    def finalize(action: str) -> bool:
        nonlocal notes
        if action == "complete":
            if not notes:
                notes = input("Completion notes (optional): ") or None
            try:
                if confirm_completion(client, task_id, notes):
                    print("Task marked complete.")
                    return True
                print("Completion failed; heartbeat loop still running.")
            except requests.RequestException as exc:
                print(f"Completion request failed: {exc}", file=sys.stderr)
            return False

        try:
            if client.abandon(task_id):
                print("Task abandoned.")
                return True
            print("Abandon failed; heartbeat loop still running.")
        except requests.RequestException as exc:
            print(f"Abandon request failed: {exc}", file=sys.stderr)
        return False

    try:
        while True:
            if loop.error:
                print(loop.error, file=sys.stderr)
                return False
            try:
                command = (
                    input("Action [complete/abandon/heartbeat/status/notes/help]> ")
                    .strip()
                    .lower()
                )
            except (EOFError, KeyboardInterrupt):
                # Terminal interrupts default to abandon so leases aren't left dangling.
                print()
                command = "abandon"
            if command in {"complete", "c", "abandon", "a"}:
                action = "complete" if command in {"complete", "c"} else "abandon"
                if finalize(action):
                    return True
                continue
            if command in {"heartbeat", "h"}:
                ok = client.heartbeat(task_id)
                print("Manual heartbeat sent", "(ok)" if ok else "(rejected)")
                continue
            if command in {"status", "s"}:
                print(json.dumps(task, indent=2))
                continue
            if command.startswith("notes"):
                notes = input("Set notes: ") or None
                continue
            if command in {"help", "?"}:
                print(
                    "Commands: complete (c), abandon (a), heartbeat (h), status (s), "
                    "notes, help (?)"
                )
                continue
            if command == "":
                continue
            print(f"Unknown command: {command}")
    finally:
        # Coordinate shutdown with the background thread regardless of how we exit.
        loop.stop()
        loop.join(HEARTBEAT_SHUTDOWN_TIMEOUT)


def compute_backoff_interval(
    base_interval: float,
    misses: int,
    *,
    max_interval: float,
    multiplier: float,
) -> float:
    """Return the next poll interval using exponential backoff."""

    if misses <= 1 or multiplier <= 1.0:
        return max(base_interval, 0.0)
    candidate = base_interval * (multiplier ** (misses - 1))
    return min(max_interval, max(candidate, base_interval, 0.0))


def confirm_completion(
    client: SwitchboardClient, task_id: int, notes: Optional[str]
) -> bool:
    """Attempt to mark ``task_id`` complete, returning the server status."""

    try:
        return client.complete(task_id, notes=notes or "")
    except requests.HTTPError as exc:  # pragma: no cover - network errors
        print(f"Complete failed: {exc}", file=sys.stderr)
    return False


def run_command(args: argparse.Namespace) -> int:
    """Execute the interactive agent loop using parsed arguments."""

    try:
        client = SwitchboardClient(args.base, args.agent)
    except requests.RequestException as exc:
        print(f"Failed to register agent: {exc}", file=sys.stderr)
        return 1
    try:
        print(f"Registered agent '{args.agent}' against {args.base}.")
        lease_seconds: Optional[float] = None
        warning_messages: list[str] = []
        try:
            settings_payload = client.get_settings()
        except requests.RequestException as exc:
            warning_messages.append(f"failed to fetch server settings ({exc}).")
        else:
            lease_seconds, parse_warnings = extract_lease_duration(settings_payload)
            warning_messages.extend(parse_warnings)
            if lease_seconds is not None:
                print(
                    f"Server lease duration is {lease_seconds:.0f}s.",
                    file=sys.stderr,
                )
        for message in warning_messages:
            print(f"Warning: {message}", file=sys.stderr)
        heartbeat_interval, heartbeat_reason = sanitize_heartbeat_interval(
            getattr(args, "heartbeat_interval", DEFAULT_HEARTBEAT_INTERVAL),
            lease_seconds,
        )
        if heartbeat_reason:
            print(
                f"Heartbeat interval set to {heartbeat_interval:.1f}s ({heartbeat_reason}).",
                file=sys.stderr,
            )
        poll_interval = max(args.poll_interval, 0.0)
        max_poll_interval = max(
            getattr(args, "max_poll_interval", poll_interval), poll_interval
        )
        backoff_multiplier = max(
            getattr(args, "backoff_multiplier", 1.0), 1.0
        )
        misses = 0
        current_interval = poll_interval
        while True:
            try:
                task = client.checkout()
            except requests.RequestException as exc:
                print(f"Checkout failed: {exc}", file=sys.stderr)
                return 1
            if not task:
                reason = getattr(client, "last_checkout_reason", None)
                if reason:
                    print(f"No task available ({reason}).")
                else:
                    print("No task available.")
                misses += 1
                current_interval = compute_backoff_interval(
                    poll_interval,
                    misses,
                    max_interval=max_poll_interval,
                    multiplier=backoff_multiplier,
                )
                try:
                    time.sleep(current_interval)
                except KeyboardInterrupt:
                    print()
                    return 0
                continue
            misses = 0
            current_interval = poll_interval
            if not process_task(client, task, heartbeat_interval):
                return 1
    finally:
        client.close()


def build_parser() -> argparse.ArgumentParser:
    """Return the top-level argument parser for the CLI."""

    parser = argparse.ArgumentParser(prog="switchboard-cli")
    subparsers = parser.add_subparsers(dest="command")
    run_parser = subparsers.add_parser("run", help="Run the interactive agent loop")
    run_parser.add_argument(
        "--base", required=True, help="Base URL of the Switchboard server"
    )
    run_parser.add_argument(
        "--agent", required=True, help="Agent identifier to register and use for leases"
    )
    run_parser.add_argument(
        "--poll-interval",
        type=float,
        default=10.0,
        help="Seconds to wait before retrying checkout",
    )
    run_parser.add_argument(
        "--max-poll-interval",
        type=float,
        default=DEFAULT_MAX_POLL_INTERVAL,
        help="Upper bound for adaptive polling backoff",
    )
    run_parser.add_argument(
        "--backoff-multiplier",
        type=float,
        default=2.0,
        help="Multiplier applied to the poll interval after consecutive misses",
    )
    run_parser.add_argument(
        "--heartbeat-interval",
        type=float,
        default=DEFAULT_HEARTBEAT_INTERVAL,
        help="Seconds between automatic heartbeats while a task is checked out",
    )
    run_parser.set_defaults(func=run_command)
    return parser


def main(argv: Optional[list[str]] = None) -> int:
    """Entry point for console scripts and ``python -m`` execution."""

    parser = build_parser()
    args = parser.parse_args(argv)
    func: Callable[[argparse.Namespace], int] | None = getattr(args, "func", None)
    if func is None:
        parser.print_help()
        return 1
    return func(args)


if __name__ == "__main__":
    sys.exit(main())
