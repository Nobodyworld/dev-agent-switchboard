#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BASE_URL="${BASE_URL:-http://localhost:8000}"
DATA_FILE="${DATA_FILE:-${SCRIPT_DIR}/seed_tasks.json}"

if [[ ! -f "${DATA_FILE}" ]]; then
  echo "Seed data file not found: ${DATA_FILE}" >&2
  exit 1
fi

echo "Seeding tasks from ${DATA_FILE} into ${BASE_URL}" >&2

python3 - "$BASE_URL" "$DATA_FILE" <<'PY'
import json
import sys
import urllib.error
import urllib.request

base_url = sys.argv[1].rstrip("/")
json_path = sys.argv[2]

with open(json_path, "r", encoding="utf-8") as fh:
    tasks = json.load(fh)

created_ids = {}

for idx, task in enumerate(tasks, start=1):
    payload = {
        "title": task["title"],
        "description": task.get("description", ""),
        "depends_on": list(task.get("depends_on", [])),
    }

    for dep_title in task.get("depends_on_titles", []):
        if dep_title not in created_ids:
            raise SystemExit(f"Unknown dependency '{dep_title}' for task '{task['title']}'. Ensure dependencies reference prior tasks.")
        payload["depends_on"].append(created_ids[dep_title])

    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        f"{base_url}/api/tasks",
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    try:
        with urllib.request.urlopen(req) as resp:
            body = resp.read().decode("utf-8")
            print(f"[{idx}] Created '{payload['title']}': {body}")
            try:
                created = json.loads(body)
                created_ids[task["title"]] = created["id"]
            except Exception:
                # If the response isn't JSON or lacks an ID we still continue, but warn.
                print(f"Warning: could not parse response for '{payload['title']}'", file=sys.stderr)
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8")
        raise SystemExit(f"Failed to create '{payload['title']}': {exc.code} {detail}") from exc
PY
