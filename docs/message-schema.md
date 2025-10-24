# Message Schema Reference

This reference documents the JSON contracts exchanged between agents, the
dashboard, and the Switchboard orchestration router. Every structure is backed
by the dataclasses in `server/interfaces.py` and the Pydantic models in
`server/schema.py`.

## TaskEnvelope

A `TaskEnvelope` wraps the canonical payload returned during checkout and plan
updates. It combines queue metadata, task details, and the active lease when one
exists.

```json
{
  "queue": {
    "name": "default",
    "kind": "task",
    "metadata": {
      "version": "v1"
    }
  },
  "task": {
    "id": 42,
    "title": "Publish documentation",
    "description": "Refresh message schema reference",
    "status": "in_progress",
    "depends_on": [21, 23],
    "metadata": {
      "updated_at": "2025-02-20T18:04:32.481Z"
    }
  },
  "lease": {
    "task_id": 42,
    "agent_id": "docbot",
    "issued_at": "2025-02-20T18:00:00Z",
    "expires_at": "2025-02-20T18:20:00Z"
  }
}
```

- **queue** – `QueueDescriptor` containing a stable queue identifier and optional
  metadata (version tags, affinity labels, etc.).
- **task** – `TaskPayload` representing the work item. The `metadata` bag may
  include `completed_notes`, `updated_at`, or future routing hints.
- **lease** – `TaskLease` describing the active lease. Absent when the task is
  not leased.

## CheckoutOutcome

The `/api/tasks/checkout` endpoint returns a `CheckoutOutcome` serialized as:

```json
{
  "task": {
    "id": 42,
    "title": "Publish documentation",
    "description": "Refresh message schema reference",
    "status": "in_progress",
    "depends_on": [21, 23],
    "completed_notes": null
  },
  "reason": null
}
```

- **task** – Populated `TaskOut` structure when a lease is granted.
- **reason** – Machine-readable failure code (`"no_available_tasks"`,
  `"task_not_found"`, or `"task_not_available"`).

Clients should persist `reason` (the Python SDK stores it on
`SwitchboardClient.last_checkout_reason`) to inform backoff policies.

## CompletionOutcome

The `/api/tasks/{id}/complete` endpoint responds with:

```json
{
  "ok": true,
  "notes": "Verified locally"
}
```

- **ok** – Indicates whether the completion succeeded.
- **notes** – Normalized completion notes persisted on the task (may be `null`).

When completion succeeds, a fresh `TaskEnvelope` is emitted via the plan
broadcast WebSocket containing the updated status and cleared lease.

## HealthStatus

Health probes share a consistent payload shape:

```json
{
  "ok": true,
  "checks": {
    "process": true,
    "database": true,
    "storage": true
  },
  "version": "0.1.0"
}
```

- `/health/live` always returns `process: true` and reflects application
  version.
- `/health/ready` toggles `database` and `storage` based on runtime probes.
  When any check fails the endpoint responds with HTTP 503 and `ok: false` while
  still emitting the body above.

## Agent Registration

Agent registration is unchanged but included here for completeness:

```json
{
  "ok": true,
  "agent_id": "local-runner"
}
```

The `AgentDescriptor` introduced in `server/interfaces.py` ensures the
`agent_id` is normalized before persistence, enabling future metadata (labels,
capabilities) to be captured without breaking wire contracts.
