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
4. **Observability** – Use `X-Request-ID` and `X-Trace-ID` headers (returned by
   the API) when logging or reporting incidents so maintainers can correlate
   traces, audit feeds, and logs.

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

## Observability Signals

- `GET /api/observability/telemetry` – Summarises whether logging, metrics, and
  tracing are currently active and which request/trace headers to propagate.
  This is the canonical way for agents to detect feature flags before emitting
  extra headers or scraping `/metrics`.
- `GET /api/observability/health` – Combines liveness, readiness, and telemetry
  state with structured probe observations. Ideal for alerting pipelines that
  want a single JSON document instead of scraping multiple endpoints.
- `GET /api/observability/audit-feed` – Returns the rolling in-memory audit
  trail captured by the builtin `activity_feed` extension. Useful when agents
  need to confirm whether lifecycle webhooks or external automations observed a
  state transition.
- `GET /api/diagnostics` – Rich runtime snapshot including extension contract
  metadata and dependency status. Automation should cache this payload and
  invalidate when `runtime.metadata.observability` changes.
- `GET /metrics` – Prometheus endpoint if `SWITCHBOARD_ENABLE_METRICS=1`.
  When builtin extensions are enabled the `plan_metrics` observer publishes
  gauges such as `switchboard_task_status_total` and
  `switchboard_task_readiness_total` after every plan broadcast, so scrape
  targets can alert on blocked work without polling the analytics API.
- `GET /api/observability/overview` – Consolidated JSON snapshot combining
  liveness, readiness, telemetry, diagnostics, and extension observability
  registrations. Mirrors the output of
  `python scripts/dev.py observability-overview` and is ideal for runbooks or
  on-call dashboards.

## Tooling

- `scripts/dev.py bootstrap` – Provision a local environment (`.venv`) with all
  dev dependencies, including pre-commit hooks for formatting and security.
- `scripts/dev.py verify` – Run lint, type, test, security, and coverage gates in
  one invocation (CI mirrors this pipeline).
- `scripts/dev.py coverage-gate` – Validate coverage JSON output against required
  thresholds.
- `scripts/dev.py check-todos` – Ensure TODO/FIXME markers include priority and
  effort metadata.
- `scripts/dev.py scaffold-extension` – Generate a starter module pre-populated
  with contract metadata and TODO placeholders.
- `scripts/dev.py observability-overview` – Emit the same payload as
  `/api/observability/overview`, useful for capturing point-in-time telemetry
  snapshots in incident reports.
- `scripts/dev.py bump-version` – Update runtime version metadata and create new
  changelog/release note stubs.
- `scripts/audit_metrics.py` – Produce coverage, cyclomatic complexity, and dependency depth summaries in `reports/system_metrics.json` for stewardship reporting.
- Runtime metadata can be extended via
  `server.observability.runtime.register_runtime_metadata()`
  (`# agent-entrypoint`) so deployments annotate health responses with rollout
  details that downstream monitors can read.
- `Makefile` targets:
  - `make qa` runs lint, typecheck, tests, security scan, and coverage gate.
  - `make coverage` mirrors the CI coverage job and writes `reports/coverage.json`.

## Safety Checklist

- Honour `429` responses – the rate limiter surfaces cooldown windows via
  headers. Back off rather than retrying aggressively.
- Observe `extensions.registered` values – if custom plugins (e.g., audit
  loggers) are active, ensure your agent supplies any expected metadata or
  headers documented by that plugin.
- Review `GET /api/observability/audit-feed` when debugging automation – the
  feed mirrors recent lifecycle events alongside request and trace identifiers
  without scraping logs.
- Watch for plan observer contract notes – new plan observers (including the
  builtin `plan_metrics`) surface contract notes via `/api/settings` so agents
  know when analytics gauges or downstream automations expect additional
  context.
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
- **Do** call `server.app.broadcast_plan()` (`# agent-safe-task`) after
  automation mutates plan state so connected clients receive consistent
  snapshots.
- **Do** query `/api/observability/telemetry` during startup to determine
  whether builtin webhook or metrics extensions are active before emitting
  redundant alerts.
