# Observability Playbook

Switchboard ships with opt-in instrumentation layers that surface system
behaviour without requiring third-party agents. This document summarises the
available probes, how to enable them, and how automation should consume the
signals.

## Health & Diagnostics

| Endpoint | Purpose |
| --- | --- |
| `/health/live` | Liveness check confirming the process is up and returning probe observations for the `process` check. |
| `/health/ready` | Readiness check executing database and storage probes; returns HTTP 503 with detailed observations when a critical dependency fails. |
| `/api/health` | JSON envelope combining liveness and readiness payloads; returns HTTP 503 when readiness is degraded. |
| `/api/observability/health` | Aggregated payload combining the liveness/readiness probes with the latest telemetry snapshot. Requires the admin token when configured. |
| `/api/diagnostics` | Deep inspection surface exposing package versions, extension metadata, and runtime environment details. |
| `/api/observability/overview` | Consolidated JSON snapshot combining health probes, telemetry state, diagnostics, and extension observability metadata. Requires the admin token when configured. |

Both `/health/*` endpoints and `/api/observability/health` include the
`observations` array, providing per-probe duration, criticality, and error
information. Downstream monitors should alert on `ok: false` or probe-specific
failures rather than parsing log text.

## Telemetry & Metrics

- `SWITCHBOARD_ENABLE_METRICS=1` enables the Prometheus instrumentator and the
  builtin metrics extensions. Metrics are exposed at `/metrics` and include
  counters such as `switchboard_task_checkout_total`, gauges updated by
  `plan_metrics`, histograms emitted by `plan_latency`, and plan snapshot
  metadata published via `/api/observability/metrics`.
- `SWITCHBOARD_ENABLE_TRACING=1` instruments FastAPI with OpenTelemetry. Even
  without exporters, the request pipeline emits a stable `X-Trace-ID` header that
  correlates HTTP responses, logs, telemetry payloads, and the audit feed.
- `SWITCHBOARD_ENABLE_STRUCTURED_LOGGING=1` enables JSON logging via
  `python-json-logger`; every record includes `request_id` and `trace_id`
  properties.

- The `/api/observability/telemetry` endpoint summarises which subsystems are
  active, the expected request/trace headers, runtime metadata (including plan
  snapshot details), and the last time builtin metrics were updated.
- `/api/observability/metrics` returns the analytics catalog (enabled flag,
  timestamps, sample values) so dashboards can confirm whether gauges remain
  fresh without scraping `/metrics` directly.
- `python scripts/dev.py extensions` prints the loaded extensions, contract
  notes, and observability registrations so responders can correlate telemetry
  payloads with extension outputs.

## Audit Feed

The builtin `activity_feed` extension records recent task lifecycle events,
plan broadcasts, and server startup in an in-memory ring buffer. Fetch
`/api/observability/audit-feed` to retrieve the latest events along with the
correlated `request_id` and `trace_id` values. Tune retention via the
`SWITCHBOARD_ACTIVITY_FEED_SIZE` environment variable (defaults to 128 events).

Use the feed to verify whether automated agents observed a lifecycle change or
whether webhook notifications fired without reading log files.

## Operational Checklist

1. Enable metrics/tracing in staging environments first to validate exporters.
2. Ensure Prometheus scrapers include the `/metrics` path and propagate the
   `X-Request-ID` header to preserve correlation where possible.
3. Automate health checks against `/api/observability/health`; fallback to
   `/health/ready` if the admin token is unavailable.
4. Include the audit feed snapshot in incident reports so responders can
   reconstruct task activity without digging through logs.
