#!/usr/bin/env bash
set -euo pipefail

BASE_URL="${1:-http://localhost:8000}"

create_task() {
  local title="$1"
  local description="$2"
  local depends_on_json="$3"

  local payload
  payload=$(jq -n --arg title "$title" --arg description "$description" --argjson depends_on "$depends_on_json" '{title:$title, description:$description, depends_on:$depends_on}')

  curl -sS -X POST "${BASE_URL}/api/tasks" \
    -H "Content-Type: application/json" \
    -d "${payload}" \
    | jq -r '.id // .detail // .message'
}

if ! command -v curl >/dev/null 2>&1; then
  echo "Error: curl is required" >&2
  exit 1
fi

if ! command -v jq >/dev/null 2>&1; then
  echo "Error: jq is required" >&2
  exit 1
fi

echo "Seeding initial tasks into ${BASE_URL}"

root_task_id=$(create_task "Initial plan setup" "Create the foundational tasks and docs" "[]")

if [[ ! "$root_task_id" =~ ^[0-9]+$ ]]; then
  echo "Failed to create root task: ${root_task_id}" >&2
  exit 1
fi

echo "Created root task with ID ${root_task_id}"

create_task "Implement feature A" "Build the first feature after setup" "[${root_task_id}]"
create_task "Implement feature B" "Build the second feature after setup" "[${root_task_id}]"
create_task "QA and launch" "Verify and launch after features" "[${root_task_id}]"

echo "Done."
