import argparse
import time
from typing import Any, Optional

from switchboard_client import SwitchboardClient


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Example agent loop for Switchboard")
    parser.add_argument(
        "--base-url",
        default="http://localhost:8000",
        help="Switchboard server base URL",
    )
    parser.add_argument(
        "--agent-id",
        default="codex-1",
        help="Agent identifier to use when talking to the server",
    )
    parser.add_argument(
        "--heartbeat-count",
        type=int,
        default=3,
        help="Number of heartbeats to send before completing a task",
    )
    parser.add_argument(
        "--heartbeat-interval",
        type=float,
        default=2.0,
        help="Seconds to wait between heartbeats",
    )
    parser.add_argument(
        "--sleep-interval",
        type=float,
        default=5.0,
        help="Seconds to sleep when no tasks are available",
    )
    parser.add_argument(
        "--completion-notes",
        default="done",
        help="Notes to include when completing a task",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print planned actions without mutating server state",
    )
    return parser.parse_args()


def dry_run(client: SwitchboardClient, args: argparse.Namespace) -> None:
    base = client.base
    agent = client.agent_id
    print(f"[dry-run] Would POST {base}/api/agents with {{'agent_name': '{agent}'}}")

    planned_task: Optional[dict[str, Any]] = None
    try:
        tasks = client.list_tasks()
        for task in tasks:
            if task.get("status") == "pending":
                planned_task = task
                break
    except Exception as exc:
        print(f"[dry-run] Unable to fetch available tasks: {exc}")

    checkout_url = f"{base}/api/tasks/checkout?agent_id={agent}"
    if planned_task:
        tid = planned_task["id"]
        title = planned_task.get("title", "")
        print(f"[dry-run] Would POST {checkout_url} -> task {tid} {title!r}")
        for i in range(args.heartbeat_count):
            hb_url = f"{base}/api/tasks/{tid}/heartbeat?agent_id={agent}"
            print(
                "[dry-run] Would POST "
                f"{hb_url} (heartbeat {i + 1}/{args.heartbeat_count})"
            )
        complete_url = f"{base}/api/tasks/{tid}/complete?agent_id={agent}"
        print(
            f"[dry-run] Would POST {complete_url} with notes={args.completion_notes!r}"
        )
    else:
        print(f"[dry-run] Would POST {checkout_url} -> no tasks available")

    print(f"[dry-run] Would sleep {args.sleep_interval} seconds before polling again")


def run(client: SwitchboardClient, args: argparse.Namespace) -> None:
    while True:
        task = client.checkout()
        if not task:
            print("No tasks available; sleeping...")
            time.sleep(args.sleep_interval)
            continue
        tid = task["id"]
        print("Checked out:", task)
        for _ in range(args.heartbeat_count):
            ok = client.heartbeat(tid)
            print("heartbeat", ok)
            time.sleep(args.heartbeat_interval)
        ok = client.complete(tid, notes=args.completion_notes)
        print("complete", ok)


if __name__ == "__main__":
    cli_args = parse_args()
    client = SwitchboardClient(
        cli_args.base_url, cli_args.agent_id, auto_register=not cli_args.dry_run
    )
    if cli_args.dry_run:
        dry_run(client, cli_args)
    else:
        run(client, cli_args)
