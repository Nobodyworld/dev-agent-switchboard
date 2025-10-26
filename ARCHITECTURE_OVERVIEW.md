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
|  server/app.py                 |
|  - REST & WebSocket routes     |
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

- **`server/app.py`** – FastAPI wiring that now initializes the extension
  runtime and surfaces configuration metadata via `/api/settings`.
- **`server/extensions/`** – Modular extension loader, registry, and builtin
  task + plan metrics plugins. Hooks are dispatched from `TaskService` and
  plan broadcasts so operators can attach automation (alerts, analytics
  exporters, audit trails, custom sinks) without modifying core code paths.
- **`server/extensions/builtin/webhook_notifier.py`** – Reference builtin
  extension that posts lifecycle events to a configurable HTTP endpoint and
  documents the contract note surfaced via `/api/settings`.
- **`server/application/task_service.py`** – Coordinates task lifecycle and
  notifies registered extensions on checkout, completion, abandonment, and task
  mutations.
- **`server/instrumentation/`** – Optional logging, metrics, and tracing
  helpers. Metrics now work in concert with the extension hooks so Prometheus
  counters reflect lifecycle events and plan broadcasts.
- **`server/observability/telemetry.py`** – Centralises instrumentation
  bootstrap, exposes `/api/observability/telemetry`, and annotates runtime
  metadata with logging/metrics/tracing status.
- **`scripts/dev.py`** – Developer CLI for bootstrapping, coverage enforcement,
  todo auditing, extension scaffolding, and version bump automation.

## Observability Flow

1. `RequestIdMiddleware` (configured in `server/instrumentation/logging.py`)
   injects `X-Request-ID` headers and logging context.
2. Builtin extensions register Prometheus counters. When `TaskService`
   transitions a task, the metrics hook increments labeled counters.
3. Health endpoints (`/health/live`, `/health/ready`) include service version,
   uptime, start timestamp, and storage/database status. `/api/observability/telemetry`
   summarises whether logging, metrics, tracing, and builtin webhooks are active
   so operators can correlate events quickly. The incident response guide
   explains how to react to failures and what telemetry to capture.
4. CI's coverage job produces `reports/coverage.json` and gates critical
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

## Deployment Notes

- The Makefile target `make coverage` mirrors the CI pipeline (lint → typecheck
  → test → coverage gate). Operators can run it locally before submitting PRs.
- `scripts/dev.py bump-version` updates `server/app.py`, `CHANGELOG.md`, and
  `RELEASE_NOTES.md`, ensuring release automation stays in sync with the runtime
  version.
- Observability components remain optional via environment toggles (e.g.,
  `SWITCHBOARD_ENABLE_METRICS`, `SWITCHBOARD_ENABLE_BUILTIN_EXTENSIONS`), and
  when enabled the builtin `plan_metrics` observer keeps Prometheus gauges in
  sync with the latest task analytics.
