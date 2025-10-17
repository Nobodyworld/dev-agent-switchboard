# Polish and document the full Switchboard stack

This ExecPlan is a living document. The sections `Progress`, `Surprises & Discoveries`, `Decision Log`, and `Outcomes & Retrospective` must be kept up to date as work proceeds.

This repository implements the Switchboard service. This plan must be maintained in accordance with `.agent/PLANS.md`.

## Purpose / Big Picture

Deliver a production-ready Switchboard release by polishing each subsystem: clarify documentation, enforce consistent structure and naming, tighten type hints, and remove lingering footguns while preserving existing runtime behavior. The result should feel cohesive from FastAPI server through CLI tooling, with clear guidance in docs and reliable tests demonstrating the steady-state functionality.

## Progress

- [x] Initial state captured.
- [x] Server modules audited and refactored for clarity and consistency.
- [x] Client and CLI polished with unified ergonomics and documentation.
- [x] Documentation and developer tooling refreshed.
- [x] Tests updated and run to confirm stability.
- [x] Final validation and retrospective completed.

## Surprises & Discoveries

- Observation: The old WebSocket broadcast list occasionally left closed sockets behind, leading to repeated send failures that
  were silently suppressed.
  Evidence: While reviewing `server/app.py` the broadcast loop appended sockets to a list and relied on `ValueError` suppression
  for removals, meaning stale connections persisted after send errors.

## Decision Log

- Decision: Introduced structured result NamedTuples for checkout and completion flows so API handlers receive explicit fields
  instead of ambiguous tuples.
  Rationale: Clarifies downstream usage, prevents accidental tuple unpacking mistakes, and enables future extension without
  breaking callers.
  Date/Author: 2025-02-15 / gpt-5-codex

## Outcomes & Retrospective

- WebSocket broadcasting is centralized in `PlanBroadcaster`, eliminating stale connection leaks and improving observability for tests.
- Task lifecycle helpers now return structured results, clarifying API behavior while preserving compatibility.
- Client and CLI ergonomics improved through context management, richer docstrings, and refreshed architecture documentation for maintainers.

## Context and Orientation

- `server/app.py` hosts the FastAPI application, websocket broadcasts, and REST endpoints for agents, tasks, plans, and file uploads.
- `server/task_logic.py` encapsulates leasing, dependency management, and plan version tracking logic shared by the API.
- `server/file_store.py` maps live-file requests onto disk paths and keeps metadata synchronized in the database.
- `server/instrumentation/` provides logging, metrics, and tracing configuration helpers.
- `client/python/switchboard_client.py` exposes the HTTP client used by agents, while `client/python/switchboard_cli.py` provides the interactive CLI entrypoint.
- Compatibility shims live at repo root (`switchboard_client.py`, `switchboard_cli.py`) and tests under `client/python/tests/` and `tests/` ensure shim parity.
- Documentation currently spans `README.md`, `docs/`, and `PROJECT_STATUS.md` but lacks an authoritative architecture overview.

## Plan of Work

1. Audit server modules for inconsistent imports, missing docstrings, and duplicated helper logic; introduce shared utilities where appropriate and tighten typing without altering behavior.
2. Clarify request/response modeling by centralizing serialization helpers, ensuring websockets and REST endpoints share consistent payloads and logging.
3. Polish client and CLI code with structured type hints, docstrings, context managers for sessions, and consistent error messaging; update root shims accordingly.
4. Refresh documentation to describe the polished architecture, runtime expectations, and operational flows for agents and operators.
5. Align tests and developer tooling with the refinements: adjust fixtures, add regression coverage where gaps emerge, and run the full suite.

## Concrete Steps

1. Run `python -m compileall server client/python` to baseline syntax health before changes.
2. Refactor and document `server/app.py`, `server/task_logic.py`, `server/file_store.py`, `server/db.py`, `server/settings.py`, and instrumentation modules, ensuring consistent logging and imports.
3. Update `client/python/switchboard_client.py`, `client/python/switchboard_cli.py`, and root shims with cohesive APIs, docstrings, and type hints while maintaining compatibility.
4. Extend or adjust documentation (`README.md`, `docs/architecture.md` or similar) to reflect the polished system and workflow expectations.
5. Update or add tests (`server/tests`, `client/python/tests`, root `tests`) to codify any clarified behavior, then run `pytest -q` and targeted lint/typing commands if feasible.
6. Review and update the ExecPlan, fill decision/outcome sections, and prepare final validation notes.

## Validation and Acceptance

- `pytest -q` passes (with expected skips for optional dependencies) after refactor.
- `python -m compileall server client/python` succeeds post-changes.
- Documentation clearly describes architecture and usage, and code modules carry descriptive docstrings.

## Idempotence and Recovery

- Changes remain backwards-compatible; the API surface and CLI commands retain existing signatures and semantics.
- Database schema untouched beyond metadata/documentation updates; migrations remain valid.
- Refactors favor pure-Python adjustments, so reverting to previous commit restores prior state without extra cleanup.

## Artifacts and Notes

- `python -m compileall server client/python` ⇒ success (no output beyond listings).
- `pytest -q` ⇒ 30 passed, 2 skipped.

## Interfaces and Dependencies

- FastAPI endpoints continue to satisfy schemas defined in `server/schema.py`.
- SQLAlchemy async session helpers remain the entrypoint for persistence.
- `requests.Session` remains the single external dependency for the Python client, with CLI dependent on stdlib modules.
