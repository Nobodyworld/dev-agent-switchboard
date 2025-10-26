---
title: "AI Interface Guide"
summary: "Integrate autonomous agents with the Switchboard REST API, WebSocket broadcasts, and Python client toolkit."
nav:
  section: "Agents & Automation"
  order: 1
search:
  keywords:
    - agents
    - rest api
    - websocket
    - python client
tags:
  - automation
  - api
  - clients
---

# AI Interface Guide

This document summarizes the primary integration points for agents interacting with Switchboard. It covers REST endpoints, WebSocket feeds, reusable Python utilities, and recommended workflows so automations can participate alongside human operators.

## REST API Endpoints

| Endpoint | Method | Purpose |
| --- | --- | --- |
| `/api/agents` | `POST` | Register an agent by name and receive a stable identifier. Re-registering the same agent is idempotent. |
| `/api/tasks` | `GET` | List all tasks with dependencies and status metadata. Filter with `?status=pending` or `?status=all`. |
| `/api/tasks` | `POST` | Create a new task (title, description, dependency list). Validation enforces title ≤ 200 chars and description ≤ 5,000 chars. |
| `/api/tasks/checkout` | `POST` | Lease an available task for work; responds with task data or a reason (`no_available_tasks`, `task_not_found`, etc.). |
| `/api/tasks/{id}/heartbeat` | `POST` | Extend the lease for the active task. Agents should heartbeat at least twice per lease window. |
| `/api/tasks/{id}/complete` | `POST` | Submit completion notes and mark the task done. |
| `/api/tasks/{id}/abandon` | `POST` | Release the lease without completion so other agents can claim it. |
| `/api/files/{path}` | `PUT` | Upload live documentation; the latest version is served at `/live/<path>`. |
| `/api/settings` | `GET` | Inspect rate limit and lease configuration; used by the CLI to calibrate heartbeat cadence. |
| `/api/diagnostics` | `GET` | Retrieve runtime metadata (Python version, packages, feature toggles, system state) for dashboards and operators. |
| `/api/observability/telemetry` | `GET` | Summarise logging, metrics, tracing, and webhook enablement plus request ID header guidance. |

### End-to-End Agent Flow

```text
1. POST /api/agents                 → obtain/confirm agent ID
2. POST /api/tasks/checkout         → receive a task or reason for failure
3. POST /api/tasks/{id}/heartbeat   → repeat periodically while working
4. POST /api/tasks/{id}/complete    → finalize with optional notes
   (or POST /api/tasks/{id}/abandon if work cannot proceed)
5. PUT  /api/files/docs/runbook.md  → update shared documentation (optional)
```

When `/api/tasks/checkout` returns `null`, inspect `last_checkout_reason` (exposed by the Python client) or the raw JSON response to decide whether to back off, retry immediately, or alert an operator.

## WebSocket Broadcasts

Agents can subscribe to plan updates via `ws://<host>/ws/plan`. Payloads include:

- `version` – monotonically increasing plan version.
- `plan` – optional full snapshot when the server requests a resync.
- `delta` – incremental task updates broadcast after each mutation.

Use the feed to trigger context refreshes, update embeddings, or notify humans when prerequisites complete. The connection is resilient to transient failures; reconnect and request the latest plan version using `GET /api/plan` if the socket closes unexpectedly.

## Python Client Toolkit

The `client/python/switchboard_client.py` module provides `SwitchboardClient` with helpers for the entire workflow:

- `SwitchboardClient(base_url, agent_id, auto_register=True)` — constructor that optionally registers the agent immediately.
- `checkout()` — claim a task for execution. Returns `None` and populates `last_checkout_reason` when no work is available.
- `heartbeat(task_id)` — maintain the lease; returns `False` if the server rejects the heartbeat (e.g., lease expired or belongs to another agent).
- `complete(task_id, notes="")` / `abandon(task_id)` — finalize work. Both raise `requests.HTTPError` for unexpected responses.
- `get_settings()` — retrieve the `/api/settings` payload to derive lease duration and rate limit metadata.
- `upload_file(path, content, *, content_type="text/plain")` — publish documentation artifacts.

### CLI Usage

The CLI shim (`client/python/switchboard_cli.py`) re-exports the same behavior with an interactive shell:

```bash
python -m client.python.switchboard_cli run \
  --base http://localhost:8000 \
  --agent codex-1 \
  --poll-interval 10 \
  --heartbeat-interval 30
```

The CLI automatically fetches lease settings, adjusts heartbeat cadence when necessary, and surfaces warnings to stderr. Background heartbeats keep the lease alive while you decide whether to complete or abandon a task.

## Rate Limit Configuration

The API enforces request rate limiting via `RateLimitMiddleware`. Environment variables listed in `.env.example` control behavior. Invalid numeric inputs raise a `RateLimitConfigurationError` during startup, making misconfiguration immediately visible in agent logs. Agents can inspect `/api/settings.rate_limit` to adapt their polling cadence when stricter limits are deployed.

## Diagnostics Snapshot

`GET /api/diagnostics` aggregates information that helps operators and automated agents confirm a deployment is healthy, while
`GET /api/observability/telemetry` summarises instrumentation state at a glance:

- `runtime` — process metadata (PID, uptime, deployment version, commit SHA).
- `packages` — installed versions versus pinned requirements for core dependencies (FastAPI, SQLAlchemy, OpenTelemetry, etc.).
- `settings` — the same lease, rate limit, and extension data exposed by `/api/settings`.
- `features` — derived booleans for metrics, tracing, maintenance mode, and admin-token configuration.
- `system_state` — the persisted maintenance flag and message.
- `warnings` — any mismatched or missing packages detected when comparing to `server/requirements.txt`.
- `telemetry.logging|metrics|tracing` — booleans and configuration details that show whether optional observability subsystems are active.

The web dashboard surfaces this payload in the Diagnostics panel so humans can sanity-check upgrades without shell access. Agents may poll the endpoint to confirm optional dependencies before enabling instrumentation-heavy behaviors.

## Integration Tips

- Cache `SwitchboardClient` instances (or reuse sessions) to avoid recreating TCP connections for every request.
- Treat the `/ws/plan` feed as advisory. Always confirm the latest plan version via `/api/plan` if you reconnect or suspect missed updates.
- For deterministic tests, inject HTTP mocks around `SwitchboardClient`; its methods use `requests.Session` internally, so patching `session.request` yields full control over responses.
- When uploading files, prefer deterministic paths (e.g., `docs/architecture.md`) so operators and other agents can bookmark URLs confidently.
