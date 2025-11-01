# Switchboard Architecture Overview

## Runtime Topology

```
+-------------------------------+
|           Web / CLI           |
|  React-less JS + Python CLI   |
+---------------+---------------+
                |
                v
+---------------+---------------+
|          FastAPI Gateway       |
|  server/api/, server/app.py    |
|  - Router modules & app factory|
|  - Request context middleware  |
|  - Extension bundle loader     |
+---------------+---------------+
                |
                v
+---------------+---------------+
|        Application Layer       |
|  server/application/*          |
|  - TaskService w/ lifecycle    |
|    hooks                       |
|  - SystemStateService          |
+---------------+---------------+
                |
                v
+---------------+---------------+
|          Domain Contracts      |
|  server/domain/*               |
|  - Entities & policies         |
|  - Repository protocols        |
+---------------+---------------+
                |
                v
+---------------+---------------+
|         Infrastructure         |
|  server/infrastructure/*       |
|  - SQLAlchemy repositories     |
|  - File store adapters         |
+---------------+---------------+
```

## Key Packages

- **`server/api/` & `server/app.py`** – Modular FastAPI routers plus the
  application factory. `server/app.py` re-exports the assembled app for
  backwards compatibility while routing logic lives in `server/api/routers/*`.
- **`server/extensions/`** – Modular extension loader, registry, and builtin
  task + plan metrics plugins. Hooks are dispatched from `TaskService` and
  plan broadcasts so operators can attach automation (alerts, analytics
  exporters, audit trails, custom sinks) without modifying core code paths.
- **`server/extensions/contracts.py`** – Versioned dataclasses (`TaskHookContext`,
  `PlanBroadcastContext`) injected into extension hooks when requested so
  plugins can consume consistent metadata without parsing kwargs.
- **`server/extensions/builtin/webhook_notifier.py`** – Reference builtin
  extension that posts lifecycle events to a configurable HTTP endpoint and
  documents the contract note surfaced via `/api/settings`.
- **`server/extensions/builtin/plan_snapshot.py`** – Captures plan broadcast
  analytics, publishes runtime metadata, and registers observability details for
  dashboards and responders.
- **`server/application/task_service.py`** – Coordinates task lifecycle and
  notifies registered extensions on checkout, completion, abandonment, and task
  mutations.
- **`server/instrumentation/`** – Optional logging, metrics, and tracing
  helpers. Metrics now work in concert with the extension hooks so Prometheus
  counters reflect lifecycle events and plan broadcasts.
- **`server/observability/telemetry.py`** – Centralises instrumentation
  bootstrap, exposes `/api/observability/telemetry`, and annotates runtime
  metadata (including plan snapshot state) with logging/metrics/tracing status.
- **`server/observability/overview.py`** – Aggregates runtime, health,
  diagnostics, and extension metadata to drive the `/api/observability/overview`
  endpoint and developer CLI snapshot command.
- **`scripts/dev.py`** – Developer CLI for bootstrapping, coverage enforcement,
  todo auditing, extension scaffolding, extension inventory, and version bump
  automation.

## Observability Flow

1. `RequestIdMiddleware` (configured in `server/instrumentation/logging.py`)
   injects `X-Request-ID` headers, derives a stable `X-Trace-ID`, and shares
   both through logging context so structured logs, telemetry, and audit feeds
   can be correlated.
2. Builtin extensions register Prometheus counters. When `TaskService`
   transitions a task, the metrics hook increments labeled counters.
3. `server/observability/health.py` centralises probe definitions so
  `/health/live` and `/health/ready` emit consistent observations while
  `/api/health` returns a JSON envelope and `/api/observability/health`
  combines liveness, readiness, and telemetry state for dashboards or
  automation.
4. `/api/observability/telemetry` exposes logging/metrics/tracing enablement,
  request ID headers, runtime metadata, and extension notes so agents and
  operators can adapt behaviour dynamically.
5. `/api/observability/metrics` surfaces the Prometheus analytics catalog (or a
  disabled summary) alongside timestamps so dashboards know when builtin gauges
  last refreshed.
6. `/api/observability/overview` (and the matching `scripts/dev.py`
  `observability-overview` command) synthesise health probes, telemetry,
  diagnostics, plan snapshot metadata, and registered observability hooks to
  give responders a single payload for incident triage.
7. The builtin `activity_feed` extension persists a rolling in-memory audit log
  via `server/observability/activity.py`, surfaced at
  `/api/observability/audit-feed`. Agents and incident responders can review
  recent lifecycle events without tailing logs.
8. CI's coverage job produces `reports/coverage.json` and gates critical
  modules at ≥85% coverage to keep the observability and extension layer
  trustworthy. `scripts/audit_metrics.py` expands this with complexity and
  dependency depth metrics for stewardship reviews.

## Extension Lifecycle

- Startup: `initialize_extensions(app)` loads builtin and user-defined modules,
  registering optional FastAPI startup hooks.
- Runtime: `TaskService` emits events (`on_checkout`, `on_complete`, etc.) to the
  bundle and `broadcast_plan` triggers plan observers. Hooks may perform async
  work such as logging, alerting, analytics export, or fan-out.
- Discovery: `/api/settings` now returns `extensions` metadata (configured
  modules, builtin toggle, registered descriptors) so operators and agents can
  inspect which plugins are active.
- Context: Extensions targeting contract version **2025.3** can accept an
  optional `context` keyword parameter (task or plan) to access structured
  metadata without manual kwarg parsing.

## Deployment Notes

- The Makefile target `make coverage` mirrors the CI pipeline (lint → typecheck
  → test → coverage gate). Operators can run it locally before submitting PRs.
- `scripts/dev.py bump-version` updates the FastAPI wrapper (`server/app.py`),
  `CHANGELOG.md`, and `RELEASE_NOTES.md`, ensuring release automation stays in
  sync with the runtime version.
- Observability components remain optional via environment toggles (e.g.,
  `SWITCHBOARD_ENABLE_METRICS`, `SWITCHBOARD_ENABLE_BUILTIN_EXTENSIONS`). When
  metrics are enabled the builtin `plan_metrics` and `plan_latency` observers
  update analytics gauges and interval histograms so operators can spot stale
  plans quickly.
- Operators can capture real-time telemetry snapshots by running
  `python scripts/dev.py observability-overview --pretty`, which mirrors the
  `/api/observability/overview` payload consumed by dashboards and automation.
