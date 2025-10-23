---
title: "Architecture Deep Dive"
summary: "Trace the FastAPI backend, client SDK, and operator UI components that power Switchboard."
nav:
  section: "System Design"
  order: 1
search:
  keywords:
    - architecture
    - backend
    - fastapi
    - client sdk
tags:
  - architecture
  - backend
  - client
---

# Switchboard Architecture Overview

Switchboard is composed of a FastAPI backend, a lightweight web UI, and Python tooling for agents. This document builds on the repository-wide overview in [ARCHITECTURE.md](../ARCHITECTURE.md) with extra detail targeted at contributors who need to trace execution paths or extend the platform.

## Server Layout (`server/`)

### Entry Points

- **`app.py`** – Wires the FastAPI application, HTTP routes, and WebSocket broadcaster. The module-level docstring calls out its role as the single integration point for middleware, settings, and templates. The `PlanBroadcaster` helper tracks connected WebSocket clients, pruning defunct sockets whenever send failures occur.
- **`schema.py`** – Collects the Pydantic models that guarantee consistent API payloads. Response models mirror the JSON returned to agents and the UI, which keeps serialization logic centralized.

### Domain Logic

- **`task_logic.py`** – Owns task lifecycle operations (checkout, heartbeat, completion, abandon). NamedTuple return types (`CheckoutResult`, `CompleteResult`) expose both success state and failure reasons, making API handlers predictable and easy to test.
- **`file_store.py`** – Handles live documentation writes. The helper enforces that uploads stay under the configured storage root, computes cache-friendly ETags when available, and records metadata for retrieval.
- **`execplan_registry.py`** – Produces the aggregated ExecPlan index. Docstrings document how timestamps are normalized, how weak ETags are computed, and why helper functions return `None` for empty collections (avoids noisy JSON output).

### Infrastructure Helpers

- **`db.py`** – Configures the async SQLAlchemy engine and exposes `get_session()` as a FastAPI dependency. Environment parsing is centralized here and reused by tests and runtime alike.
- **`settings.py`** – Parses environment variables into typed dataclasses. A shared `SettingsBundle` returns rate limit and lease settings together so API routes fetch configuration once per request.
- **`middleware/`** – Houses reusable ASGI middleware such as the sliding-window rate limiter. Each class is designed for explicit registration inside `app.py`.
- **`instrumentation/`** – Provides optional logging, metrics, and tracing hooks. The modules read environment flags during startup; disabling a feature results in a no-op configuration.
- **`time_utils.py`** – Supplies UTC-aware timestamp helpers that both server and client code reuse for consistent lease calculations.

## Client Tooling (`client/python/`)

- **`switchboard_client.py`** – Implements the `SwitchboardClient` wrapper around the REST API. Docstrings outline retry semantics, context manager support, and the purpose of each constructor parameter. Methods either return parsed JSON or raise `requests` exceptions, letting consumers opt into their own retry or logging layers.
- **`switchboard_cli.py`** – Supplies the interactive CLI that uses `SwitchboardClient` to register, check out, and complete tasks with optional heartbeat maintenance. The top-level docstring clarifies that it can be embedded in other tooling, while function docstrings explain how the heartbeat loop coordinates with user prompts.
- **`examples/agent_example.py`** – Demonstrates a minimal polling agent. Newly added docstrings explain how to run the script in dry-run mode versus actively mutating server state.

## Operator UI (`web/`)

The `web/` directory contains the static admin dashboard built with HTMX and Tailwind. Templates reside in `web/templates/`, and assets are served directly by FastAPI's `StaticFiles` mount. UI updates rely on the same REST and WebSocket endpoints documented for agents, so feature parity between humans and automation remains tight.

## Testing Strategy

- **`client/python/tests/`** – Exercises the Python client and CLI using mocks around the underlying `requests.Session`. Tests assert retry behavior, heartbeat adjustments based on lease durations, and command-line argument parsing.
- **`server/tests/`** – Covers API behavior, instrumentation toggles, and persistence logic. Integration tests use FastAPI's `TestClient` with async fixtures from `pytest-asyncio` to verify database interactions end-to-end.
- **`tests/test_shims.py`** – Ensures root-level shims (`switchboard_client.py`, `switchboard_cli.py`) stay synchronized with the packaged modules so external imports remain stable.

Refer back to [README.md](../README.md) for environment setup, operational workflows, and sample API calls. The README now links into each deeper document so you can navigate between conceptual overviews, design notes, and hands-on instructions with minimal friction.
