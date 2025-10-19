# AI Interface Guide

This document summarizes the primary integration points for agents interacting
with Switchboard. It covers REST endpoints, WebSocket feeds, and reusable Python
utilities.

## REST API Endpoints

| Endpoint | Method | Purpose |
| --- | --- | --- |
| `/api/agents` | `POST` | Register an agent by name and receive an ID. |
| `/api/tasks` | `GET` | List all tasks with dependencies and status metadata. |
| `/api/tasks` | `POST` | Create a new task (title, description, dependency list). |
| `/api/tasks/checkout` | `POST` | Lease an available task for work; responds with task data or reason for failure. |
| `/api/tasks/{id}/heartbeat` | `POST` | Extend the lease for the active task. |
| `/api/tasks/{id}/complete` | `POST` | Submit completion notes and mark the task done. |
| `/api/tasks/{id}/abandon` | `POST` | Release the lease without completing the task. |
| `/api/files/{path}` | `PUT` | Upload live documentation; available under `/live/<path>`. |

Task creation and updates now enforce maximum lengths for `title` (200
characters) and `description` (5,000 characters). Exceeding these limits raises a
422 validation error.

## WebSocket Broadcasts

Agents can subscribe to plan updates via `ws://<host>/ws/plan`. Payloads include
plan snapshots and version increments so clients can reconcile local state.

## Python Client Toolkit

The `client/python/switchboard_client.py` module provides `SwitchboardClient`
with helpers for:

- `register_agent()`/constructor — initialize and register.
- `checkout()` — claim a task for execution.
- `heartbeat(task_id)` — maintain the lease.
- `complete(task_id, notes)` and `abandon(task_id)` — finalize work.
- `upload_file(path, content)` — publish documentation artifacts.

The CLI shim (`switchboard_cli.py`) now exposes explicit re-exports, ensuring
static analysis tools report accurate names and enabling `from switchboard_cli
import run_command` usage without wildcard imports.

## Rate Limit Configuration

The API enforces request rate limiting via `RateLimitMiddleware`. Environment
variables listed in `.env.example` control behavior. Invalid numeric inputs now
raise a `RateLimitConfigurationError` during startup, making misconfiguration
immediately visible in agent logs.

## Integration Tips

- Use the `/api/tasks/checkout` response `reason` field to detect why checkout
  failed (e.g., `no_available_tasks`).
- Leverage the WebSocket plan feed to refresh UI or agent context when the plan
  version increments.
- For deterministic tests, inject HTTP mocks around `SwitchboardClient`; its
  methods use `requests.Session` internally.
