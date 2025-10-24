# Switchboard Documentation Hub

Welcome to the Switchboard operator and agent guide. This site explains how the
queue and agent orchestration router is structured, how to run it locally, and
how to integrate agents safely.

## Quick Start

1. **Install dependencies**

   ```bash
   make install
   ```

2. **Start the API and dashboard**

   ```bash
   make serve
   ```

3. **Verify health checks**

   ```bash
   curl http://localhost:8000/health/live
   curl -i http://localhost:8000/health/ready
   ```

4. **Run the local runner**

   ```bash
   python scripts/local_runner.py --base-url http://localhost:8000 --once
   ```

   The runner registers an agent, attempts a checkout, and optionally completes
   a task when `--auto-complete` is supplied. See the [end-to-end
   example](#end-to-end-example) for a fuller walkthrough.

## Architecture Overview

Switchboard is intentionally modular:

- **Router & API** – `server/app.py` exposes REST, WebSocket, and health
  endpoints. Queue orchestration occurs in `server/application/task_service.py`
  backed by shared dataclasses in `server/domain/` and `server/interfaces.py`.
- **Domain Logic** – `server/domain/` and `server/application/task_service.py` encapsulate task lifecycle rules,
  leases, and dependency evaluation.
- **Client Toolkit** – `client/python/switchboard_client.py` and
  `scripts/local_runner.py` provide a Python API and executable runner that
  exercise the router.

See [Architecture](architecture.md) for diagrams and deeper discussion.

## Message Schema

The router exchanges structured payloads defined in `server/interfaces.py`. Key
structures include:

- **TaskEnvelope** – wraps queue metadata, task payload, and active lease
  details.
- **HealthStatus** – aggregates liveness and readiness checks with per-probe
  booleans.

Consult the [Message Schema reference](message-schema.md) for serialized
examples and field definitions.

## Failure Modes

Operational concerns—from database outages to lease contention—are captured in
[Failure Modes](failure-modes.md). Each scenario includes detection guidance and
recommended remediation steps.

## End-to-End Example

Follow these steps to process a task locally:

1. Seed a task using the REST API:

   ```bash
   http POST http://localhost:8000/api/tasks title="Sample" description="Demo"
   ```

2. Run the local runner in auto-complete mode:

   ```bash
   python scripts/local_runner.py --base-url http://localhost:8000 --auto-complete --completion-notes "Verified locally"
   ```

3. Observe the task transition to `completed` via the dashboard or `http
   http://localhost:8000/api/tasks`.

## Additional Resources

- [Architecture](architecture.md)
- [Message Schema](message-schema.md)
- [Failure Modes](failure-modes.md)
- [README](../README.md)
- [CHANGELOG](../CHANGELOG.md)
- [TODO Issues](TODO-ISSUES.md)

For historical documents that have not yet been migrated, see `docs/INDEX.md`.
