# Incident Response Runbook

This runbook outlines the steps for diagnosing and recovering from production
incidents affecting Switchboard.

## Severity Levels

- **SEV-1** – Total outage (API unreachable, WebSocket broadcast halted).
- **SEV-2** – Degraded functionality (tasks cannot be checked out, health
  endpoint returns 503, storage errors).
- **SEV-3** – Intermittent or scoped issues (single agent affected, slow
  heartbeat responses).

## First Response Checklist

1. **Capture context**
   - Request/trace identifiers (`X-Request-ID`, `X-Trace-ID`) from the failing
     response headers.
   - `/api/settings` payload (rate limits, lease duration, extensions).
   - `/health/live`, `/health/ready`, `/api/health`, `/api/observability/health`,
     and `/api/observability/telemetry` JSON payloads (instrumentation status,
     request header guidance, probe observations, plan snapshot metadata).
   - `/api/observability/audit-feed` snapshot (confirms which lifecycle events
     the builtin `activity_feed` observed around the incident window).
   - `/api/observability/metrics` snapshot (confirms whether plan analytics
     gauges are updating and when they were last refreshed).
2. **Check telemetry**
   - `/metrics` (if enabled) – focus on `switchboard_task_*` counters to identify
     spikes in checkout/heartbeat failures. Cross-reference with
     `/api/observability/metrics` when Prometheus is unreachable.
   - Application logs filtered by `request_id` or `trace_id` using the structured
     JSON output.
   - Database connectivity: run `SELECT 1` using the same credentials as the app.
3. **Stabilise**
   - Toggle maintenance mode via `POST /api/system-state` if agents must be
     paused.
   - Restart workers or API pods only after collecting diagnostics; request IDs
     aid in correlating traces if OpenTelemetry is enabled.

## Common Failure Scenarios

### Database Outage
- **Symptoms** – `/health/ready` returns `503`, logs show SQLAlchemy connection
  errors.
- **Actions** – Verify database availability, fail over if possible, then clear
  stale leases by calling `POST /api/tasks/abandon` for affected tasks. Monitor
  Prometheus counters to confirm checkouts recover.

### Storage Errors
- **Symptoms** – File uploads failing, `/health/ready` `storage=false`.
- **Actions** – Ensure filesystem permissions on the live file root. Use the
  automation script `scripts/dev.py coverage-gate` to confirm tests still pass
  after remediation (guards against regressions in file hooks).

### Extension Misconfiguration
- **Symptoms** – `/api/settings` lists custom extensions but tasks emit errors
  during lifecycle events.
- **Actions** – Check extension module logs, temporarily disable via
  `SWITCHBOARD_EXTENSIONS` override, and file follow-up issues referencing the
  extension descriptor metadata returned by the API.

## Recovery & Postmortem

1. Annotate the incident timeline in `RELEASE_NOTES.md` (under the relevant
   version) with impact, mitigation, and follow-up items.
2. File TODO entries (with priority/effort tags) in `TASKSLIST.md` for any
   structural improvements identified.
3. Ensure CI runs (`make qa`) before closing the incident to verify no regressions
   were introduced during the fix. `python scripts/dev.py verify` mirrors the CI
   job graph and runs in the same order, including pip-audit.
