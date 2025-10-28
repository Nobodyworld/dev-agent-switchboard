# Message Schema Reference

This reference documents the JSON contracts exchanged between agents, the
dashboard, and the Switchboard orchestration router. Every structure is backed
by the Pydantic models in `server/schema.py`.

## TaskOut

`TaskOut` represents an immutable task payload returned by `/api/tasks`,
`/api/tasks/{id}`, and successful checkouts:

```json
{
  "id": 42,
  "title": "Publish documentation",
  "description": "Refresh message schema reference",
  "status": "in_progress",
  "completed_notes": null,
  "depends_on": [21, 23]
}
```

- **status** – Enumerated value from `TaskStatus`.
- **depends_on** – Ordered task identifiers representing prerequisites.
- **completed_notes** – Persisted operator or agent notes (may be `null`).

## CheckoutOut

The `/api/tasks/checkout` endpoint returns a `CheckoutOut` payload:

```json
{
  "task": {
    "id": 42,
    "title": "Publish documentation",
    "description": "Refresh message schema reference",
    "status": "in_progress",
    "completed_notes": null,
    "depends_on": [21, 23]
  },
  "reason": null,
  "message": null
}
```

- **task** – Populated `TaskOut` when a lease is granted; omitted when checkout
  fails.
- **reason** – Machine-readable failure code (`"no_available_tasks"`,
  `"task_not_found"`, `"task_not_available"`, or `"maintenance_mode"`).
- **message** – Optional human-readable explanation accompanying the failure
  reason.

Clients should persist `reason` (the Python SDK stores it on
`SwitchboardClient.last_checkout_reason`) to inform backoff policies.

## CompleteResponse

Completing a task responds with `CompleteResponse`:

```json
{
  "ok": true,
  "notes": "Verified locally"
}
```

- **ok** – Indicates whether the completion succeeded.
- **notes** – Normalized completion notes persisted on the task (may be `null`).

When completion succeeds, the WebSocket broadcaster emits a `plan_version`
payload (see `PlanOut` below) containing the updated task list and version.

## PlanOut

Plan broadcasts and `GET /api/plan` share the `PlanOut` payload:

```json
{
  "version": 17,
  "updated_at": "2025-10-26T03:15:40.124720+00:00",
  "tasks": [
    {
      "id": 42,
      "title": "Publish documentation",
      "description": "Refresh message schema reference",
      "status": "in_progress",
      "completed_notes": null,
      "depends_on": [21, 23]
    }
  ]
}
```

- **version** – Monotonically increasing integer indicating the latest plan
  revision.
- **updated_at** – UTC timestamp of the plan snapshot.
- **tasks** – Array of `TaskOut` objects.

## HealthStatus

Health probes share the `HealthStatus` payload:

```json
{
  "ok": true,
  "checks": {
    "process": true,
    "database": true,
    "storage": true
  },
  "version": "0.1.0",
  "uptime_seconds": 23.4,
  "started_at": "2025-10-26T02:45:19.120418+00:00"
}
```

- `/health/live` always returns `process: true` and reflects application
  version.
- `/health/ready` toggles `database` and `storage` based on runtime probes.
  When any check fails the endpoint responds with HTTP 503 and `ok: false` while
  still emitting the body above.

## HealthEnvelopeOut

`/api/health` wraps both health probes to provide a single JSON response:

```json
{
  "ok": true,
  "liveness": {"ok": true, "checks": {"process": true}},
  "readiness": {"ok": true, "checks": {"database": true, "storage": true}}
}
```

- **ok** – `true` only when both liveness and readiness passed.
- **liveness/readiness** – `HealthStatus` payloads mirroring the individual
  `/health/live` and `/health/ready` endpoints. The API responds with HTTP 503
  when `ok` is `false` to integrate cleanly with load balancers.

## TelemetryReportOut

`/api/observability/telemetry` surfaces instrumentation posture via
`TelemetryReportOut`:

```json
{
  "generated_at": "2025-02-18T12:30:00Z",
  "logging": {
    "enabled": true,
    "configured": true,
    "details": {
      "request_id_header": "X-Request-ID"
    },
    "warnings": []
  },
  "metrics": {
    "enabled": false,
    "configured": false,
    "details": {
      "endpoint": "/metrics",
      "plan_observers": 3
    },
    "warnings": [
      "Prometheus instrumentation disabled; set SWITCHBOARD_ENABLE_METRICS=1 to expose /metrics."
    ]
  },
  "tracing": {
    "enabled": true,
    "configured": true,
    "details": {
      "exporter": "console"
    },
    "warnings": []
  },
  "request_id_header": "X-Request-ID",
  "health_endpoints": ["/health/live", "/health/ready", "/api/health"],
  "runtime": {
    "metadata": {
      "plan_snapshot": {
        "blocked_tasks": 1,
        "ready_tasks": 4,
        "version": 12
      }
    }
  }
}
```

- **logging/metrics/tracing** – `TelemetrySubsystemOut` structures with
  `enabled` and `configured` flags plus descriptive details/warnings.
- **request_id_header** – Header downstream systems should propagate.
- **health_endpoints** – Enumerates which health routes are exposed for load
  balancers or monitors.
- **runtime.metadata.plan_snapshot** – Present when the builtin plan snapshot
  extension has observed a broadcast.

## MetricsCatalogOut

`/api/observability/metrics` returns the analytics catalog so dashboards can
confirm whether builtin gauges are fresh without scraping `/metrics`:

```json
{
  "generated_at": "2025-02-18T12:30:00Z",
  "enabled": true,
  "last_updated_at": "2025-02-18T12:29:58Z",
  "status": {"pending": 3, "completed": 5},
  "readiness": {"ready": 4, "blocked": 1},
  "dependency": {"with_dependencies": 2, "without_dependencies": 6},
  "missing": {"tasks": 0, "edges": 0},
  "dependency_edges": 4.0,
  "average_dependencies": 1.5,
  "updated_timestamp": 1708259398.0
}
```

- **enabled** – Indicates whether Prometheus metrics are currently instrumented.
- **last_updated_at** – Timestamp of the last plan analytics broadcast that
  refreshed gauges (null when metrics have never run).
- **status/readiness/dependency/missing** – Gauge snapshots describing the task
  portfolio.
- **updated_timestamp** – Raw Unix timestamp of the last metrics update.

## DiagnosticsReportOut

`/api/diagnostics` returns `DiagnosticsReportOut` summarising package versions
and runtime state. See the endpoint documentation for detailed fields; the
payload is intentionally verbose to support operations automation.

## Agent Registration

`POST /api/agents` returns an `AgentRegistrationResponse`:

```json
{
  "ok": true,
  "agent_id": "local-runner"
}
```

- **ok** – Always `true`.
- **agent_id** – Canonical identifier used in checkout and heartbeat calls.
