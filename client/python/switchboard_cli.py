"""Interactive command-line tooling for running Switchboard agents."""

import argparse
import json
import sys
import threading
import time
from collections.abc import Callable, Mapping, Sequence
from typing import Any, Optional, cast

import requests
from switchboard_client import SwitchboardClient

from .runtime_config import (
    DEFAULT_HEARTBEAT_INTERVAL,
    DEFAULT_MAX_POLL_INTERVAL,
    RuntimeConfiguration,
    compute_backoff_interval,
    derive_runtime_configuration,
    extract_lease_duration,
    sanitize_heartbeat_interval,
)

BYTE_SCALE = 1024.0
HEARTBEAT_SHUTDOWN_TIMEOUT = 5.0

TaskPayload = dict[str, Any]

__all__ = [
    "DEFAULT_HEARTBEAT_INTERVAL",
    "DEFAULT_MAX_POLL_INTERVAL",
    "HEARTBEAT_SHUTDOWN_TIMEOUT",
    "HeartbeatLoop",
    "RuntimeConfiguration",
    "analytics_command",
    "build_parser",
    "compute_backoff_interval",
    "configuration_command",
    "derive_runtime_configuration",
    "display_runtime_configuration",
    "extract_lease_duration",
    "format_task",
    "main",
    "maintenance_command",
    "process_task",
    "run_command",
    "sanitize_heartbeat_interval",
]


def _format_bytes(value: float | int | None) -> str:
    """Return a human-readable string for ``value`` bytes."""

    if value is None:
        return "unknown"
    number = float(value)
    units = ["B", "KiB", "MiB", "GiB", "TiB"]
    for unit in units:
        if number < BYTE_SCALE or unit == units[-1]:
            if unit == "B":
                return f"{int(number)} {unit}"
            return f"{number:.1f} {unit}"
        number /= BYTE_SCALE
    return f"{number:.1f} TiB"


def _append_section(lines: list[str], section: Sequence[str]) -> None:
    """Append ``section`` to ``lines`` separated by a blank line."""

    if not section:
        return
    if lines and lines[-1] != "":
        lines.append("")
    lines.extend(section)


def _render_rate_limit_section(
    rate: Mapping[str, Any],
    lease: Mapping[str, Any],
    admin: Mapping[str, Any],
) -> list[str]:
    enabled = "enabled" if rate.get("enabled") else "disabled"
    requests = rate.get("requests", "n/a")
    window = rate.get("window_seconds", "n/a")
    lines = [
        "Switchboard configuration",
        "------------------------",
        f"Rate limit: {requests} requests / {window}s ({enabled})",
    ]

    bypass = [str(value) for value in rate.get("trusted_bypass") or []]
    if bypass:
        lines.append(f"  Trusted bypass: {', '.join(bypass)}")

    proxies = [str(value) for value in rate.get("trusted_proxies") or []]
    if proxies:
        lines.append(f"  Trusted proxies: {', '.join(proxies)}")

    duration = lease.get("duration_seconds")
    if duration is None:
        lines.append("Lease duration: n/a")
    else:
        lines.append(f"Lease duration: {duration} seconds")

    configured = "yes" if admin.get("configured") else "no"
    lines.append(f"Admin token configured: {configured}")
    return lines


def _render_storage_section(storage: Mapping[str, Any]) -> list[str]:
    root = storage.get("root", "<unknown>")
    exists = storage.get("exists")
    writable = storage.get("writable")
    free_bytes = _format_bytes(storage.get("free_bytes"))
    total_bytes = _format_bytes(storage.get("total_bytes"))
    return [
        (
            "Storage root: "
            f"{root} (exists: {exists}, writable: {writable})"
        ),
        f"Storage free: {free_bytes} / {total_bytes}",
    ]


def _render_database_section(database: Mapping[str, Any]) -> list[str]:
    url = database.get("url", "<unknown>")
    driver = database.get("driver", "n/a")
    configured_via_env = database.get("configured_via_env")
    source = (
        "DATABASE_URL environment variable"
        if configured_via_env
        else "default configuration"
    )
    lines = [
        f"Database URL: {url} (driver: {driver})",
        f"  Source: {source}",
    ]

    options = database.get("engine_options") or {}
    if options:
        rendered = ", ".join(
            f"{key}={value}" for key, value in sorted(options.items())
        )
        lines.append(f"  Engine options: {rendered}")
    return lines


def _render_extensions_section(extensions: Mapping[str, Any]) -> list[str]:
    modules = [str(module) for module in extensions.get("modules") or []]
    registered = [
        descriptor.get("name", "<unknown>")
        for descriptor in extensions.get("registered") or []
    ]
    builtin = extensions.get("builtin_enabled")
    contract_version = extensions.get("contract_version")
    contract_notes = [
        str(note).strip()
        for note in extensions.get("contract_notes") or []
        if str(note).strip()
    ]

    lines = [
        f"Extensions: {len(modules)} configured, {len(registered)} active",
    ]
    if builtin is not None:
        enabled = "yes" if builtin else "no"
        lines.append(f"  Builtin extensions enabled: {enabled}")
    if modules:
        lines.append(f"  Modules: {', '.join(modules)}")
    if registered:
        lines.append(f"  Registered: {', '.join(registered)}")
    if contract_version:
        lines.append(f"  Contract version: {contract_version}")
    if contract_notes:
        lines.append("  Contract notes:")
        lines.extend(f"    - {note}" for note in contract_notes)
    return lines


def _render_runtime_section(runtime: Mapping[str, Any]) -> list[str]:
    lines: list[str] = []
    started_at = runtime.get("started_at")
    if started_at:
        lines.append(f"Runtime started: {started_at}")
    uptime = runtime.get("uptime_seconds")
    if isinstance(uptime, (int, float)):
        lines.append(f"Runtime uptime: {uptime:.1f}s")
    version = runtime.get("version")
    if version:
        lines.append(f"Runtime version: {version}")
    environment = runtime.get("environment")
    if environment:
        lines.append(f"Runtime environment: {environment}")
    commit = runtime.get("commit_sha")
    if commit:
        lines.append(f"Runtime commit: {commit}")
    metadata = runtime.get("metadata") or {}
    if metadata:
        lines.append("Runtime metadata:")
        lines.extend(
            f"  - {key}: {value}" for key, value in sorted(metadata.items())
        )
    return lines


def _render_warnings_section(warnings: Sequence[str]) -> list[str]:
    cleaned = [warning for warning in warnings if warning]
    if not cleaned:
        return []
    lines = ["Warnings:"]
    lines.extend(f"  - {warning}" for warning in cleaned)
    return lines


def _render_environment_section(
    environment: Sequence[Mapping[str, Any]]
) -> list[str]:
    if not environment:
        return []
    sorted_entries = sorted(environment, key=lambda item: item.get("name", ""))
    lines = ["Environment variables:"]
    for entry in sorted_entries:
        name = entry.get("name", "<unknown>")
        value = entry.get("value", "")
        source = entry.get("source", "environment")
        lines.append(f"  {name} = {value} ({source})")
    return lines


class HeartbeatLoop(threading.Thread):
    """Background thread that maintains task leases via heartbeats."""

    def __init__(
        self,
        client: SwitchboardClient,
        task_id: int,
        interval: float,
        *,
        max_heartbeats: int | None = None,
    ) -> None:
        """Initialise the heartbeat loop thread with its dependencies."""

        super().__init__(daemon=True)
        self._client = client
        self._task_id = task_id
        self._interval = interval
        self._stop = threading.Event()
        self._error: Optional[str] = None
        self._heartbeats_sent = 0
        self._max_heartbeats = (
            max_heartbeats if max_heartbeats and max_heartbeats > 0 else None
        )
        self._limit_reached = False

    def run(self) -> None:
        """Send heartbeats until the loop is stopped or an error occurs."""

        while not self._stop.is_set():
            try:
                ok = self._client.heartbeat(self._task_id)
            except Exception as exc:  # pragma: no cover - network errors
                self._error = f"Heartbeat failed: {exc}"
                return
            if not ok:
                self._error = "Server rejected heartbeat"
                return
            self._heartbeats_sent += 1
            if (
                self._max_heartbeats is not None
                and self._heartbeats_sent >= self._max_heartbeats
            ):
                self._limit_reached = True
                self._stop.set()
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

    @property
    def limit_reached(self) -> bool:
        """Return ``True`` when the configured heartbeat limit has been reached."""

        return self._limit_reached

    @property
    def heartbeats_sent(self) -> int:
        """Return the number of heartbeats emitted by the loop."""

        return self._heartbeats_sent


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


def process_task(
    client: SwitchboardClient,
    task: TaskPayload,
    heartbeat_interval: float,
    *,
    max_heartbeats: int | None = None,
) -> bool:
    """Interactively process ``task`` using the provided client."""

    task_id = task["id"]
    print()
    print(format_task(task))
    loop = HeartbeatLoop(
        client,
        task_id,
        heartbeat_interval,
        max_heartbeats=max_heartbeats,
    )
    # The heartbeat thread keeps the lease alive while we wait for user input.
    # We always stop and join the thread in the finally block so the daemon
    # never leaks if the command exits early.
    loop.start()
    heartbeat_note = f"every {heartbeat_interval:.0f}s"
    if max_heartbeats is not None and max_heartbeats > 0:
        heartbeat_note += f"; auto-abandon after {max_heartbeats} heartbeats"
    print(
        "Heartbeat thread started "
        f"({heartbeat_note}). "
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
            if loop.limit_reached:
                print(
                    "Heartbeat limit reached; abandoning task automatically.",
                    file=sys.stderr,
                )
                return finalize("abandon")
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


def display_runtime_configuration(config: RuntimeConfiguration) -> None:
    """Print a formatted configuration summary for the active session."""

    maintenance_summary = 'Enabled' if config.maintenance_mode else 'Disabled'
    if config.maintenance_mode and config.maintenance_message:
        maintenance_summary = f"Enabled — {config.maintenance_message}"
    elif config.maintenance_mode:
        maintenance_summary = 'Enabled — checkouts are paused'

    rows: list[tuple[str, str]] = [
        ("Maintenance mode", maintenance_summary),
        ("Heartbeat interval", f"{config.heartbeat_interval:.1f}s"),
        ("Poll interval", f"{config.poll_interval:.1f}s"),
        ("Max poll interval", f"{config.max_poll_interval:.1f}s"),
        ("Backoff multiplier", f"{config.backoff_multiplier:.2f}"),
    ]
    if config.max_heartbeats is not None:
        rows.append(("Max heartbeats", str(config.max_heartbeats)))
    else:
        rows.append(("Max heartbeats", "disabled"))
    if config.lease_duration is not None:
        rows.append(("Server lease", f"{config.lease_duration:.0f}s"))
    if config.heartbeat_reason:
        rows.append(("Heartbeat note", config.heartbeat_reason))

    width = max((len(label) for label, _ in rows), default=0)
    print()
    print("Runtime configuration")
    print("-" * (width + 25))
    for label, value in rows:
        print(f"{label:<{width}} : {value}")


def analytics_command(args: argparse.Namespace) -> int:
    """Fetch and display aggregated task analytics."""

    try:
        with SwitchboardClient(args.base, args.agent, auto_register=False) as client:
            payload = client.get_task_analytics()
    except requests.RequestException as exc:
        print(f"Failed to fetch task analytics: {exc}", file=sys.stderr)
        return 1

    if getattr(args, "json", False):
        print(json.dumps(payload, indent=2, sort_keys=True))
        return 0

    rows = [
        ("Total tasks", payload.get("total_tasks", 0)),
        ("Pending", payload.get("pending_tasks", 0)),
        ("In progress", payload.get("in_progress_tasks", 0)),
        ("Completed", payload.get("completed_tasks", 0)),
        ("Ready", payload.get("ready_tasks", 0)),
        ("Blocked", payload.get("blocked_tasks", 0)),
        ("With dependencies", payload.get("with_dependencies", 0)),
        ("Without dependencies", payload.get("without_dependencies", 0)),
        ("Dependency edges", payload.get("dependency_edges", 0)),
        (
            "Average dependencies",
            f"{payload.get('average_dependencies', 0.0):.2f}",
        ),
    ]

    width = max(len(label) for label, _ in rows)
    for label, value in rows:
        print(f"{label:<{width}} : {value}")

    missing_tasks = payload.get("missing_dependency_tasks", 0)
    missing_edges = payload.get("missing_dependency_edges", 0)
    if missing_tasks or missing_edges:
        print(
            "Warnings: tasks reference missing dependencies — "
            f"{missing_tasks} tasks, {missing_edges} edges.",
            file=sys.stderr,
        )
    return 0


def configuration_command(args: argparse.Namespace) -> int:
    """Fetch and display the server configuration snapshot."""

    try:
        with SwitchboardClient(args.base, args.agent, auto_register=False) as client:
            payload = client.get_configuration()
    except requests.RequestException as exc:
        print(f"Failed to fetch configuration: {exc}", file=sys.stderr)
        return 1

    if getattr(args, "json", False):
        print(json.dumps(payload, indent=2, sort_keys=True))
        return 0

    settings = payload.get("settings", {})
    sections: list[str] = []
    _append_section(
        sections,
        _render_rate_limit_section(
            settings.get("rate_limit", {}),
            settings.get("lease", {}),
            payload.get("admin", {}),
        ),
    )
    _append_section(sections, _render_storage_section(payload.get("storage", {})))
    _append_section(sections, _render_database_section(payload.get("database", {})))
    _append_section(
        sections, _render_extensions_section(settings.get("extensions", {}))
    )
    _append_section(sections, _render_runtime_section(payload.get("runtime", {})))
    _append_section(sections, _render_warnings_section(payload.get("warnings", [])))
    _append_section(
        sections,
        _render_environment_section(payload.get("environment", [])),
    )

    for line in sections:
        print(line)

    return 0



def confirm_completion(
    client: SwitchboardClient, task_id: int, notes: Optional[str]
) -> bool:
    """Attempt to mark ``task_id`` complete, returning the server status."""

    try:
        return client.complete(task_id, notes=notes or "")
    except requests.HTTPError as exc:  # pragma: no cover - network errors
        print(f"Complete failed: {exc}", file=sys.stderr)
    return False


def _print_system_state(payload: Mapping[str, Any]) -> None:
    status = 'enabled' if payload.get('maintenance_mode') else 'disabled'
    print(f"Maintenance mode {status}.")
    message = payload.get('message')
    if isinstance(message, str) and message.strip():
        print(f"Message: {message.strip()}")
    updated_at = payload.get('updated_at')
    if updated_at:
        print(f"Updated at: {updated_at}")
    version = payload.get('version')
    if version is not None:
        print(f"Version: {version}")


def maintenance_command(args: argparse.Namespace) -> int:
    """Inspect or toggle maintenance mode via the HTTP API."""

    try:
        with SwitchboardClient(
            args.base,
            args.agent,
            auto_register=False,
            admin_token=getattr(args, "admin_token", None),
        ) as client:
            token = getattr(args, "admin_token", None)
            if token:
                client.set_admin_token(token)
            if getattr(args, "enable", False) or getattr(args, "disable", False):
                desired = bool(getattr(args, "enable", False))
                try:
                    payload = client.set_system_state(
                        desired,
                        message=getattr(args, "message", None),
                        expected_version=getattr(args, "expected_version", None),
                        admin_token=token,
                    )
                except requests.RequestException as exc:
                    print(f"Failed to update maintenance mode: {exc}", file=sys.stderr)
                    return 1
                _print_system_state(payload)
                return 0

            try:
                payload = client.get_system_state()
            except requests.RequestException as exc:
                print(f"Failed to fetch maintenance state: {exc}", file=sys.stderr)
                return 1
            _print_system_state(payload)
            return 0
    except requests.RequestException as exc:
        print(f"Failed to initialise client: {exc}", file=sys.stderr)
        return 1


def run_command(args: argparse.Namespace) -> int:  # noqa: PLR0912 - CLI loop handles multiple failure modes
    """Execute the interactive agent loop using parsed arguments."""

    try:
        with SwitchboardClient(args.base, args.agent) as client:
            print(f"Registered agent '{args.agent}' against {args.base}.")
            settings_payload: Mapping[str, Any] | None = None
            system_state_payload: Mapping[str, Any] | None = None
            warning_messages: list[str] = []
            try:
                settings_payload = client.get_settings()
            except requests.RequestException as exc:
                warning_messages.append(f"failed to fetch server settings ({exc}).")
            try:
                system_state_payload = client.get_system_state()
            except requests.RequestException as exc:
                warning_messages.append(f"failed to fetch system state ({exc}).")

            config: RuntimeConfiguration = derive_runtime_configuration(
                requested_heartbeat_interval=getattr(
                    args, "heartbeat_interval", DEFAULT_HEARTBEAT_INTERVAL
                ),
                poll_interval=getattr(args, "poll_interval", 0.0),
                max_poll_interval=getattr(args, "max_poll_interval", None),
                backoff_multiplier=getattr(args, "backoff_multiplier", 1.0),
                lease_settings=settings_payload,
                system_state=system_state_payload,
                warnings=warning_messages,
                max_heartbeats=getattr(args, "max_heartbeats", None),
            )

            display_runtime_configuration(config)

            for message in config.warnings:
                print(f"Warning: {message}", file=sys.stderr)
            if config.heartbeat_reason:
                print(
                    "Heartbeat interval adjusted to "
                    f"{config.heartbeat_interval:.1f}s "
                    f"({config.heartbeat_reason}).",
                    file=sys.stderr,
                )

            if config.maintenance_mode:
                default_reason = (
                    "maintenance mode is active; checkouts are disabled."
                )
                reason = config.maintenance_message or default_reason
                print(f"Checkout blocked: {reason}", file=sys.stderr)
                return 2

            heartbeat_interval = config.heartbeat_interval
            poll_interval = config.poll_interval
            max_poll_interval = config.max_poll_interval
            backoff_multiplier = config.backoff_multiplier
            max_heartbeats = config.max_heartbeats
            misses = 0
            current_interval = poll_interval
            while True:
                try:
                    task = client.checkout()
                except requests.RequestException as exc:
                    print(f"Checkout failed: {exc}", file=sys.stderr)
                    return 1
                if not task:
                    reason_code = cast(
                        str | None,
                        getattr(client, "last_checkout_reason", None),
                    )
                    detail = cast(
                        str | None,
                        getattr(client, "last_checkout_message", None),
                    )
                    if reason_code:
                        if reason_code == 'maintenance_mode':
                            message = detail or 'Maintenance mode is active; exiting.'
                            print(f"Checkout blocked: {message}", file=sys.stderr)
                            return 2
                        print(f"No task available ({reason_code}).")
                        if detail:
                            print(f"Details: {detail}")
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
                if not process_task(
                    client,
                    task,
                    heartbeat_interval,
                    max_heartbeats=max_heartbeats,
                ):
                    return 1
    except requests.RequestException as exc:
        print(f"Failed to register agent: {exc}", file=sys.stderr)
        return 1


def build_parser() -> argparse.ArgumentParser:
    """Return the top-level argument parser for the CLI."""

    parser = argparse.ArgumentParser(
        prog="switchboard-cli",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
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
    run_parser.add_argument(
        "--max-heartbeats",
        type=int,
        default=None,
        help="Automatically abandon a task after this many heartbeats (0 disables)",
    )
    run_parser.set_defaults(func=run_command)

    maintenance_parser = subparsers.add_parser(
        "maintenance", help="Inspect or toggle maintenance mode"
    )
    maintenance_parser.add_argument(
        "--base", required=True, help="Base URL of the Switchboard server"
    )
    maintenance_parser.add_argument(
        "--agent",
        default="admin-cli",
        help="Agent identifier used for client initialisation",
    )
    maintenance_parser.add_argument(
        "--admin-token",
        help="Admin token required to enable or disable maintenance mode",
    )
    maintenance_parser.add_argument(
        "--message",
        help="Optional message to display when maintenance mode is enabled",
    )
    maintenance_parser.add_argument(
        "--expected-version",
        type=int,
        help="Optimistic concurrency token obtained from a prior state read",
    )
    toggle_group = maintenance_parser.add_mutually_exclusive_group()
    toggle_group.add_argument(
        "--enable", action="store_true", help="Enable maintenance mode"
    )
    toggle_group.add_argument(
        "--disable", action="store_true", help="Disable maintenance mode"
    )
    maintenance_parser.set_defaults(func=maintenance_command)

    config_parser = subparsers.add_parser(
        "config", help="Display runtime configuration snapshot"
    )
    config_parser.add_argument(
        "--base", required=True, help="Base URL of the Switchboard server"
    )
    config_parser.add_argument(
        "--agent",
        default="config-cli",
        help="Agent identifier used for configuration requests",
    )
    config_parser.add_argument(
        "--json",
        action="store_true",
        help="Output the configuration payload as JSON",
    )
    config_parser.set_defaults(func=configuration_command)

    stats_parser = subparsers.add_parser(
        "stats", help="Display aggregated task analytics"
    )
    stats_parser.add_argument(
        "--base", required=True, help="Base URL of the Switchboard server"
    )
    stats_parser.add_argument(
        "--agent",
        default="analytics-cli",
        help="Agent identifier used for analytics requests",
    )
    stats_parser.add_argument(
        "--json",
        action="store_true",
        help="Output the analytics payload as JSON",
    )
    stats_parser.set_defaults(func=analytics_command)
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
