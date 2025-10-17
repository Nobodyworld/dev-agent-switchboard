# Switchboard Architecture Overview

Switchboard is composed of a FastAPI backend, a lightweight web UI, and Python tooling for agents. The goal of this document is to
summarize how the major pieces interact so new contributors can onboard quickly.

## Server layout (`server/`)

* **`app.py`** – Defines the FastAPI application, routers, and WebSocket broadcaster. The `PlanBroadcaster` helper manages all
  WebSocket connections, guaranteeing stale sockets are closed and removed. Request handlers delegate to `task_logic.py` for
  database mutations and serialization helpers in `schema.py`.
* **`task_logic.py`** – Encapsulates lease management and plan version tracking. Functions such as
  `checkout_task()` and `complete()` return NamedTuple results (`CheckoutResult`, `CompleteResult`) so callers receive structured
  outcomes with clear semantics.
* **`file_store.py`** – Resolves safe filesystem paths for live file uploads and keeps metadata synchronized through
  `FileWriteResult` records.
* **`db.py`** – Centralizes async SQLAlchemy engine configuration and exposes the `get_session()` dependency used throughout the
  API.
* **`instrumentation/`** – Houses logging, metrics, and tracing integration. Each module uses environment flags for opt-in
  behavior and exports a single `setup_*` function that can be safely called multiple times.
* **`middleware/`** – Contains reusable ASGI middleware, including the sliding-window `RateLimitMiddleware` configured through
  `settings.py`.
* **`schema.py`** – Provides the Pydantic models that define request/response payloads returned by the API.

## Client tooling (`client/python/`)

* **`switchboard_client.py`** – Implements the `SwitchboardClient` wrapper around the REST API. The client now exposes context
  manager support (`with SwitchboardClient(...)`) and a `timeout` property for observability. All public methods raise HTTP errors
  when the server returns unexpected statuses, ensuring calling code can react immediately.
* **`switchboard_cli.py`** – Supplies the interactive CLI that uses `SwitchboardClient` to register, checkout, and complete tasks
  with optional heartbeat maintenance. Helpers such as `format_task()` produce a consistent textual representation for command
  output, while `HeartbeatLoop` runs in a background thread to keep leases alive.

## Testing

* **`client/python/tests/`** – Covers the client and CLI behavior through mocks, including the newly added context manager and
  timeout property regression checks.
* **`server/tests/`** – Validates API behavior, instrumentation, and persistence logic. These tests rely on optional FastAPI and
  SQLAlchemy dependencies and are skipped automatically when the packages are unavailable.
* **`tests/test_shims.py`** – Ensures the root-level compatibility shims remain in sync with the packaged modules.

Refer to `README.md` for setup instructions, operational workflows, and sample API calls.
