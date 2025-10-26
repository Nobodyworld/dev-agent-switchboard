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

## TelemetryReportOut

`/api/observability/telemetry` surfaces instrumentation posture via
`TelemetryReportOut`:

```json
{
  "logging": {
    "enabled": true,
    "notes": ["RequestIdMiddleware active"]
  },
  "metrics": {
    "enabled": true,
    "notes": ["Prometheus exporter registered"]
  },
  "tracing": {
    "enabled": false,
    "notes": []
  },
  "webhook": {
    "enabled": true,
    "notes": ["SWITCHBOARD_WEBHOOK_URL configured"]
  },
  "request_id_header": "X-Request-ID"
}
```

- **logging/metrics/tracing/webhook** – `TelemetrySubsystemOut` structures with
  `enabled` flags and explanatory notes.
- **request_id_header** – Header downstream systems should propagate.

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
