#!/usr/bin/env bash
set -euo pipefail

BASE_URL="${1:-http://localhost:8000}"
PLAN_PATH="${2:-.agent/PLANS.md}"
REMOTE_PATH="${3:-plans/execplan.md}"
INDEX_REMOTE_PATH="${4:-}"

BASE_URL="${BASE_URL%/}"

if ! command -v curl >/dev/null 2>&1; then
  echo "Error: curl is required" >&2
  exit 1
fi

if [ ! -f "${PLAN_PATH}" ]; then
  echo "Error: plan file not found at ${PLAN_PATH}" >&2
  exit 1
fi

CONTENT_TYPE="text/markdown"

echo "Publishing ${PLAN_PATH} to ${BASE_URL}/api/files/${REMOTE_PATH}"

curl --fail -sS -X PUT "${BASE_URL}/api/files/${REMOTE_PATH}" \
  -H "Content-Type: ${CONTENT_TYPE}" \
  --data-binary @"${PLAN_PATH}"

echo "Available at ${BASE_URL}/live/${REMOTE_PATH}"

if [ -n "${INDEX_REMOTE_PATH}" ]; then
  TMP_INDEX="$(mktemp)"
  INDEX_URL="${BASE_URL}/api/execplans/index?format=yaml"
  echo "Fetching ExecPlan index from ${INDEX_URL}"
  trap 'rm -f "${TMP_INDEX}"' EXIT
  curl --fail -sS -H "Accept: application/yaml" "${INDEX_URL}" -o "${TMP_INDEX}"

  echo "Publishing ExecPlan index to ${BASE_URL}/api/files/${INDEX_REMOTE_PATH}"
  curl --fail -sS -X PUT "${BASE_URL}/api/files/${INDEX_REMOTE_PATH}" \
    -H "Content-Type: application/yaml" \
    --data-binary @"${TMP_INDEX}"

  rm -f "${TMP_INDEX}"
  trap - EXIT
  echo "Index available at ${BASE_URL}/live/${INDEX_REMOTE_PATH}"
fi

