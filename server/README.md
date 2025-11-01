# Server Application

This package hosts the FastAPI application, domain logic, and infrastructure
integrations that power Switchboard.

Top-level highlights:

- `api/` and `app.py` compose the FastAPI routers and ASGI application.
- `application/` contains service-layer orchestration such as task lifecycles and
  configuration snapshots.
- `domain/` defines immutable entities used throughout the application layer.
- `infrastructure/` implements repository adapters and storage integrations.
- `observability/` surfaces health, telemetry, and diagnostics endpoints.
- `extensions/` delivers the pluggable extension runtime and builtin observers.
- `tests/` includes module-specific unit tests co-located with the server code.

For architectural context read [`docs/architecture/architecture.md`](../docs/architecture/architecture.md)
and [`docs/architecture/architecture-overview.md`](../docs/architecture/architecture-overview.md).
