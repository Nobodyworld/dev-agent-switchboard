---
title: "Harden Core Runtime Helpers"
summary: "ExecPlan focused on reliability upgrades for time utilities, instrumentation, storage, and clients."
nav:
  section: "ExecPlans"
  order: 2
search:
  keywords:
    - reliability
    - execplan
    - runtime helpers
tags:
  - execplans
  - reliability
---

# Harden core runtime helpers for production reliability

This ExecPlan is a living document. The sections `Progress`, `Surprises & Discoveries`, `Decision Log`, and `Outcomes & Retrospective` must be kept up to date as work proceeds.

This repository implements the Switchboard service. This plan must be maintained in accordance with `.agent/PLANS.md`.

## Purpose / Big Picture

Increase reliability of frequently used runtime helpers so the production deployment behaves predictably. Focus areas:

- Deterministic time utilities that tests and services can override without monkeypatching globals.
- Observability hooks (logging and metrics) that better align with modern deployment expectations.
- Safer file storage writes to avoid partial results and surface filesystem misconfiguration early.
- Rate-limit middleware instrumentation so operators can monitor throttling behavior.

## Progress

- [x] Initial state captured.
- [x] Drafted implementation approach.
- [x] Implemented time provider injection and tests.
- [x] Upgraded instrumentation helpers (logging, metrics) with configuration flexibility.
- [x] Hardened file store writes and permission checks with coverage.
- [x] Instrumented rate limit middleware to publish throttling metrics.
- [x] Validation complete (lint/tests/docs).
- [x] Enforced strongly typed task statuses and hardened database engine configuration.
- [x] Hardened API client retries/timeout overrides and tightened CLI ergonomics for unattended use.
- [x] Eliminated ExecPlan registry race conditions and backfilled regression coverage.

## Surprises & Discoveries

- Observation: Repository-wide `ruff check` still fails because of a historical backlog of lint violations.
  Evidence: Running `ruff check` without file filters reports hundreds of pre-existing issues (see task notes).
- Discovered that logging setup marked itself configured even when optional dependencies were missing, preventing later retries.
  Fix: Allow reconfiguration attempts until structured logging successfully installs handlers.
- Found the ExecPlan registry bootstrap could raise IntegrityError under concurrent startups.
  Fix: Guard creation with graceful retry-on-conflict logic.
- Identified the CLI still polled aggressively and lacked deterministic timeouts for large uploads.
  Fix: Added adaptive backoff controls and per-operation client timeouts/retries.

## Decision Log

- Decision: Use context managers over global mutation for time overrides to keep tests isolated.
  Rationale: Context managers avoid accidental global leakage and align with asyncio-friendly patterns.
  Date/Author: 2025-02-15 / gpt-5-codex
- Decision: Accept JSON payloads via environment for logging dictConfig to keep configuration file-agnostic.
  Rationale: Operators can template structured configs via secret stores without mounting files.
  Date/Author: 2025-02-15 / gpt-5-codex
- Decision: Replace module-level globals in the rate limit middleware with a shared state dictionary to avoid repeated global statements.
  Rationale: The shared state improves testability and satisfies linting rules without changing behavior.
  Date/Author: 2025-02-15 / gpt-5-codex
- Decision: Track logging initialization separately from successful configuration so structured logging can retry when dependencies become available post-startup.
  Rationale: Production deployments may install optional log formatters lazily; ensuring retries avoids permanently degraded observability.
  Date/Author: 2025-02-16 / gpt-5-codex
- Decision: Consolidate task lifecycle states in a shared enum and persist them via SQLAlchemy ``Enum`` columns.
  Rationale: Avoids accidental status drift, gives FastAPI native validation, and keeps the database from accepting invalid values.
  Date/Author: 2025-02-16 / gpt-5-codex
- Decision: Read async engine tuning parameters from the environment with strict validation.
  Rationale: Lets operators size connection pools per deployment while failing fast on misconfiguration.
  Date/Author: 2025-02-16 / gpt-5-codex
- Decision: Teach the REST client to retry transient failures and honour per-operation timeout overrides.
  Rationale: Production deployments often face flaky networks and long-running uploads that benefit from tuned deadlines.
  Date/Author: 2025-02-16 / gpt-5-codex
- Decision: Add adaptive polling backoff to the CLI and expose configuration flags for unattended agents.
  Rationale: Prevents tight polling loops from overloading the server while enabling CI usage without manual intervention.
  Date/Author: 2025-02-16 / gpt-5-codex
- Decision: Handle ExecPlan registry creation races by catching unique constraint violations and re-querying.
  Rationale: Ensures a single registry entry without relying on dialect-specific locks.
  Date/Author: 2025-02-16 / gpt-5-codex

## Outcomes & Retrospective

- Time utilities now expose context-managed overrides with comprehensive unit coverage.
- Logging and metrics instrumentation accept inline configuration and optional registries while remaining idempotent.
- Logging configuration now retries when structured logging dependencies appear after an initial failure, keeping observability robust.
- File store writes are atomic with explicit permission validation and new regression tests.
- Rate limit middleware emits metrics via an overridable callback and includes tests verifying invocation.
- Task APIs now validate lifecycle filters through the shared enum while the database enforces allowed values and configurable engine tuning covers pool sizing and health.
- SwitchboardClient exposes resilient retries, per-operation timeouts, and accompanying regression tests while the CLI adds configurable backoff for unattended agents.
- ExecPlan registry initialization now tolerates concurrent startups, backed by targeted tests.

## Context and Orientation

- `server/time_utils.py` – central UTC helpers currently hardwired to real time.
- `server/instrumentation/logging.py` – structured logging bootstrap lacking dictConfig support.
- `server/instrumentation/metrics.py` – Prometheus setup without custom registry hooks.
- `server/file_store.py` – live file persistence lacking permission and atomic write safeguards.
- `server/middleware/rate_limit.py` – rate limiter without observability hooks.
- `server/tests/` – pytest suite needing coverage for the above behaviors.

## Plan of Work

1. Extend `time_utils` with override utilities (`use_time_provider`) and migrate consumers/tests to rely on them.
2. Add dictConfig ingestion and request ID filter safety to logging setup; expose metrics registry parameter with caching in `setup_metrics`.
3. Enhance `file_store.ensure_root` and `put_file` for permission checking and atomic writes.
4. Instrument rate limit middleware with an overridable counter hook and add tests verifying invocation.
5. Write focused pytest coverage for the new behaviors.
6. Run repository linters/tests and update docs/plan progress.

## Concrete Steps

1. Implement time provider override helpers and unit tests (`server/tests/test_time_utils.py`).
2. Update instrumentation modules and adjust smoke tests to cover new configuration paths.
3. Refactor file store to use atomic writes and raise HTTP 500 for unwritable directories; add regression tests.
4. Extend rate limit middleware with an injectable callback; cover via tests using a fake collector.
5. Execute `pytest -q` (allowing skips for optional deps) and `ruff check` to ensure code quality.
6. Update this ExecPlan progress checklist and summarize outcomes.

## Validation and Acceptance

- New tests for time provider overrides, file store permission failures, logging dictConfig usage, and rate limit metrics pass.
- Existing instrumentation smoke tests continue to succeed when optional dependencies are present or gracefully skip otherwise.
- `pytest -q` succeeds locally (apart from documented skips) and `ruff check` reports no issues.

## Idempotence and Recovery

- Time provider overrides rely on contextvars and tokens, so resets are automatic even on exceptions.
- Atomic file writes write to temp files before renaming, keeping partially written files from surfacing.
- Metrics instrumentation caches the instrumentator, so repeated startup invocations stay safe.
- The rate limit metric hook defaults to a no-op; disabling metrics simply removes the callback.

## Artifacts and Notes

- `pytest -q` ⇒ 33 passed, 2 skipped. (See execution log.)
- `ruff check server/...` ⇒ No issues for touched modules.

## Interfaces and Dependencies

- `logging.config.dictConfig` and JSON parsing for inline logging configs.
- Optional `prometheus_fastapi_instrumentator` for metrics setup; changes remain backwards compatible when missing.
- `tempfile.NamedTemporaryFile` and atomic renames for file writes.
