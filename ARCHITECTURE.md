# Switchboard Architecture Overview

Switchboard is a FastAPI-based control plane that coordinates agent tasks and
mirrors live project documents. The system is intentionally lightweight so it
can run in constrained environments while remaining observable.

## High-Level Components

| Layer | Description |
| --- | --- |
| API (`server/app.py`) | FastAPI application exposing REST and WebSocket endpoints for tasks, plans, and live file storage. |
| Persistence (`server/models.py`, `server/db.py`) | Async SQLAlchemy models backed by SQLite by default; supports task DAGs, agent leases, and plan versions. |
| Business Logic (`server/task_logic.py`) | Encapsulates checkout, heartbeat, completion, and dependency updates. |
| Middleware & Settings (`server/middleware/`, `server/settings.py`) | Rate limiting, logging, metrics, tracing, and environment-driven configuration. |
| Client SDK (`client/python/`) | HTTP client and CLI loop for autonomous or human-in-the-loop agents. |
| Admin UI (`web/`) | Static HTMX/Tailwind interface served by FastAPI for quick plan inspection and updates. |

## Request Lifecycle

1. Agents register via `POST /api/agents` and obtain a lease when checking out a
   task.
2. Task mutations flow through `server/task_logic.py`, which enforces dependency
   ordering and increments the plan version for WebSocket broadcasts.
3. Live file uploads reach `server/file_store.py`, which writes content to the
   configured storage root and exposes it under `/live/<path>`.
4. Rate limiting and observability middleware wrap requests using settings from
   `server/settings.py`.

## Configuration & Deployment

- Runtime behavior is driven by environment variables (`.env.example`). Invalid
  rate limit inputs now raise `RateLimitConfigurationError` during startup.
- The provided `Makefile` offers local automation for formatting, linting,
  typing, testing, and security scans.
- `ops/docker-compose.yml` packages the API and SQLite database for local or
  staging deployments.

See `docs/architecture.md` for a deeper dive into sequence diagrams and
component interactions.
