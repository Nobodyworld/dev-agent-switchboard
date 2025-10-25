# Automation & Agent Operations

This handbook explains how external agents (human or autonomous) can interact
with Switchboard safely and consistently.

## Core Principles

1. **Single-task ownership** – Checkout one task at a time via
   `POST /api/tasks/checkout?agent_id=<id>` and heartbeat every 60 seconds.
2. **Transparent state** – `/api/settings` exposes rate limits, lease duration,
   and registered extensions so agents can adapt behaviour dynamically.
3. **Idempotence** – All task lifecycle endpoints tolerate retries. Prefer
   sending the same request again rather than attempting manual recovery.
4. **Observability** – Use `X-Request-ID` headers (returned by the API) when
   logging or reporting incidents so maintainers can correlate traces and logs.

## Recommended Workflow

1. **Register** – `POST /api/agents` with a unique `agent_id`. The response
   includes the lease configuration and rate limits.
2. **Discover** – Query `GET /api/plan` to fetch task metadata and dependencies.
   The payload now contains `extensions` metadata so automation can adapt to
   active plugins (e.g., suppress duplicate notifications).
3. **Checkout** – Call `POST /api/tasks/checkout` with the agent ID.
4. **Work** – Execute the task while heartbeating. Use `/live/` endpoints to
   upload artifacts and reference them in plan notes.
5. **Complete or Abandon** – Finish with `POST /api/tasks/{id}/complete` including
   `notes`, or `POST /api/tasks/{id}/abandon` if you cannot proceed.

## Tooling

- `scripts/dev.py bootstrap` – Provision a local environment (`.venv`) with all
  dev dependencies, including pre-commit hooks for formatting and security.
- `scripts/dev.py coverage-gate` – Validate coverage JSON output against
  required thresholds. CI runs the same command to guard critical modules.
- `scripts/dev.py bump-version` – Update runtime version metadata and create new
  changelog/release note stubs.
- `Makefile` targets:
  - `make qa` runs lint, typecheck, tests, security scan, and coverage gate.
  - `make coverage` mirrors the CI coverage job and writes `reports/coverage.json`.

## Safety Checklist

- Honour `429` responses – the rate limiter surfaces cooldown windows via
  headers. Back off rather than retrying aggressively.
- Observe `extensions.registered` values – if custom plugins (e.g., audit
  loggers) are active, ensure your agent supplies any expected metadata or
  headers documented by that plugin.
- Use the incident response runbook (`docs/incident-response.md`) when tasks or
  health probes fail repeatedly. It captures common diagnostics (logs, metrics,
  extension states) that maintainers expect when triaging issues.

## Automation Boundaries

- **Do not** mutate `.agent/PLANS.md` without also updating the hosted plan file
  via `PUT /api/files/docs/PLANS.md` to keep Git and live state aligned.
- **Do not** disable builtin extensions in production without documenting the
  rationale and expected observability impact in `RELEASE_NOTES.md`.
- **Do** attach the `X-Request-ID` header when making follow-up calls related to
  a failure so logs can be correlated quickly.
