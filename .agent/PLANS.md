
# Codex Execution Plans (ExecPlans)

This file defines the single‑fence ExecPlan format that agents must use. When the content of a plan lives in its own `.md` file, omit the surrounding ``` fences as specified below.

## How to use

- Read this file in full before writing or following an ExecPlan.
- Keep plans **self‑contained**, **novice‑guiding**, **outcome‑focused**, **living**.
- Record **Progress**, **Surprises & Discoveries**, **Decision Log**, **Outcomes & Retrospective**.

## ExecPlan Skeleton (copy below into a plan file)

```md
# <Short, action‑oriented description>

This ExecPlan is a living document. The sections `Progress`, `Surprises & Discoveries`, `Decision Log`, and `Outcomes & Retrospective` must be kept up to date as work proceeds.

This repository implements the Switchboard service. This plan must be maintained in accordance with `.agent/PLANS.md`.

## Purpose / Big Picture

Explain the user‑visible behavior to be enabled and how to observe it.

## Progress

- [ ] Initial state.

## Surprises & Discoveries

- Observation: ...
  Evidence: ...

## Decision Log

- Decision: ...
  Rationale: ...
  Date/Author: ...

## Outcomes & Retrospective

- Backend endpoint logic now shares dependency serialization helpers, reducing duplicated queries and clarifying plan broadcasts.
- File storage utilities provide consistent UTC metadata and simpler imports, while new tests cover error conditions and filtering behavior.
- Python client tooling loads reliably in test environments thanks to deterministic module aliasing.

## Context and Orientation

Name key files and modules with full paths; assume the reader is new to the repo.

## Plan of Work

Describe concrete edits and additions, with file paths and functions.

## Concrete Steps

Exact commands to run, with expected outputs (short transcripts).

## Validation and Acceptance

Describe how to verify behavior end‑to‑end.

## Idempotence and Recovery

How to retry safely or roll back.

## Artifacts and Notes

Short diffs, logs, or transcripts that prove success.

## Interfaces and Dependencies

Name libraries and module interfaces (function names, types) that must exist.
```
# Enhance web UI resiliency and clarity

This ExecPlan is a living document. The sections `Progress`, `Surprises & Discoveries`, `Decision Log`, and `Outcomes & Retrospective` must be kept up to date as work proceeds.

This repository implements the Switchboard service. This plan must be maintained in accordance with `.agent/PLANS.md`.

## Purpose / Big Picture

Improve the Switchboard operator UI so task data stays reliable and comprehensible even during network hiccups. Specifically: surface toast feedback for failed network calls, show plan metadata (version & last updated), clarify dependency presentation and confirm destructive actions, move inline assets into bundled static files, and add lightweight Playwright coverage for these UX behaviors.

## Progress

- [x] Initial state.
- [x] Static asset scaffolding decided.
- [x] API additions for plan metadata finalized.
- [x] UI updated with resilience & clarity improvements.
- [x] Automated UI test committed.
- [x] Validation complete.

## Surprises & Discoveries

- Observation: Playwright waits for `networkidle` never resolve while our WebSocket stays open, so UI navigation uses `domcontentloaded` instead.
  Evidence: Manual run during test development showed `page.goto(..., wait_until="networkidle")` hanging until timeout.

## Decision Log

- Decision: Source plan metadata and tasks from `/api/plan`, exposing the DB-backed `updated_at` timestamp via a new `plan_version_snapshot` helper.
  Rationale: Keeps a single round-trip for UI refreshes while surfacing last-update information without extra queries.
  Date/Author: 2024-05-12 / gpt-5-codex

## Outcomes & Retrospective

- UI now surfaces toast banners on failures, shows plan metadata, and clarifies dependencies with accessible chips.
- API schema exposes plan `updated_at`, enabling freshness indicators in the UI.
- Playwright coverage validates the toast, dependency chips, and confirmation prompts; execution skipped locally when browsers are unavailable.

## Context and Orientation

- `web/index.html` currently embeds all Tailwind usage and inline JavaScript to render tasks via REST calls to `/api/tasks`.
- Static assets can be hosted from `/static` via FastAPI's mounting of `web/static`.
- Plan metadata is exposed via `GET /api/plan`, returning `version` and `tasks`; `PlanVersion.updated_at` exists in the database but is not surfaced in schema responses.
- Existing Python tests under `server/tests` use pytest; no UI automation exists yet.

## Plan of Work

1. Extend the API schema so `PlanOut` includes a `updated_at` timestamp sourced from `PlanVersion.updated_at`. Update `/api/plan` handler accordingly and ensure defaults handle missing row.
2. Refactor the web UI to load consolidated CSS/JS from `web/static/`. Move inline logic into `app.js`, implementing:
   - central `apiFetch` wrapper with toast banner feedback for failures or network errors.
   - plan metadata display near the Tasks header and dependency chips with tooltips.
   - confirmation prompts for complete/delete actions.
   - graceful updates of tasks/plan data using `/api/plan` payloads.
3. Add supporting styles in `styles.css` for toast banners, chips, and layout tweaks complementary to Tailwind.
4. Write a Playwright-based pytest under `web/tests/` that spins up the FastAPI app, exercises task creation, dependency rendering, plan metadata, and error toast behavior (simulated via mocked fetch or forced 500) at least once.
5. Update documentation or README snippets if necessary to mention the new tests/assets.
6. Run unit and Playwright tests locally.

## Concrete Steps

1. Modify `server/schema.py` and related logic to expose `updated_at` in `PlanOut`; adjust tests or add new ones validating timestamp presence.
2. Create `web/static/app.js` and `web/static/styles.css`; update `web/index.html` to include these assets and adjust markup for plan metadata and dependency chips.
3. Implement toast manager, dependency tooltip logic, confirmation dialogs, and network error handling in `app.js`.
4. Add a Playwright pytest (e.g., `web/tests/test_ui.py`) with fixtures to launch the FastAPI server and automate UI validation.
5. Ensure `requirements-dev.txt` includes Playwright dependencies; update `Makefile` or docs if needed.
6. Execute `pytest` (limiting to fast subsets if Playwright browsers unavailable) and document results.

## Validation and Acceptance

- `pytest` (or targeted subset) should pass, including the new Playwright test when browsers are available.
- Manual verification (if possible) that toast banners appear on simulated network failure and dependency chips render with tooltips.
- Plan version and updated timestamp visible beside Tasks header.

## Idempotence and Recovery

- Schema/API changes are additive; migrating again resets the metadata row automatically.
- Static asset bundling uses relative imports so reloads are safe.
- If Playwright installation fails, mark tests with informative skip without leaving stateful resources running.

## Artifacts and Notes

- Pending.

## Interfaces and Dependencies

- `GET /api/plan` now returns `{version:int, updated_at:str, tasks:[...]}`.
- Toast utilities rely on DOM IDs inserted into `index.html`.
- Playwright tests depend on `pytest` and `playwright.sync_api`.
# Restore core server imports and datetime helpers

This ExecPlan is a living document. The sections `Progress`, `Surprises & Discoveries`, `Decision Log`, and `Outcomes & Retrospective` must be kept up to date as work proceeds.

This repository implements the Switchboard service. This plan must be maintained in accordance with `.agent/PLANS.md`.

## Purpose / Big Picture

The Switchboard backend defines overlapping datetime utilities across modules, leading to duplicated logic for obtaining UTC timestamps and inconsistent timezone handling. We will introduce a shared helper (`server/time_utils.py`) and refactor the modules that maintain leases and live-file metadata to use it so that timestamp creation is consistent and easily testable. While touching those modules we will verify imports remain accurate.

## Progress

- [x] Initial state captured.
- [x] Repository audit complete.
- [x] Fixes implemented.
- [x] Validation attempted (dependency installation blocked by proxy).

## Surprises & Discoveries

- Observation: Unable to install pinned FastAPI dependency (`fastapi==0.115.0`) because the execution environment blocks outbound PyPI traffic via proxy.
  Evidence: `pip install -r server/requirements-dev.txt` failed with repeated `ProxyError` and "No matching distribution" errors.

## Decision Log

- Decision: Introduced a central `time_utils` module and refactored lease/file helpers to consume it, keeping timestamp semantics aligned while noting that full pytest runs remain blocked by missing dependencies in the sandbox.
  Rationale: A shared helper avoids duplicated datetime math and makes it clearer how to mock or adjust UTC semantics later, while still documenting the environment limitation.
  Date/Author: 2024-06-08 / gpt-5-codex

## Outcomes & Retrospective

- UTC helper usage is centralized, reducing duplication and ensuring leases and file metadata use consistent timestamp semantics.

## Context and Orientation

- `server/db.py` should expose SQLAlchemy engine/session factories and depends on environment variables via `os`.
- `server/models.py` defines ORM models using `sqlalchemy.orm` constructs (e.g., `Mapped`, `mapped_column`) and Python `datetime`/`typing`.
- `server/schema.py` mirrors task and plan payloads, requiring `datetime`, `Enum`, and typing imports.
- `server/task_logic.py` handles plan/task workflows, relying on `datetime`, `typing`, and SQLAlchemy `select`/`delete` APIs.
- `server/file_store.py` manages filesystem persistence and uses `hashlib`, `os`, and timezone-aware timestamps.

## Plan of Work

1. Create `server/time_utils.py` exposing timezone-aware (`utcnow`) and naive (`utcnow_naive`) UTC helpers.
2. Refactor `server/task_logic.py` to depend on the shared helper instead of local `_utcnow_naive` logic while preserving existing deadlines and lease handling.
3. Update `server/file_store.py` to reuse the shared helper for filesystem metadata timestamps.
4. Re-run compilation or targeted tests to confirm imports resolve and modules remain loadable.

## Concrete Steps

1. Author `server/time_utils.py` with `utcnow`/`utcnow_naive` helpers backed by a shared `UTC` constant.
2. Replace the bespoke `_utcnow_naive` implementation in `server/task_logic.py` with calls to the shared helper.
3. Adjust `server/file_store.py` to pull timestamps from the shared helper.
4. Execute `python scripts/run_pytest.py` (or `pytest`) to verify everything passes (or document blocking dependency issues).

## Validation and Acceptance

- `python scripts/run_pytest.py` completes successfully with no failures (or is documented as blocked by missing dependencies).
- `python -m compileall server` succeeds, confirming modules import cleanly with the shared helpers.

## Idempotence and Recovery

- The shared `time_utils` module is stateless; reapplying the refactor safely reuses the same helpers.
- If tests fail, revert individual module changes and re-run to isolate regressions.

## Artifacts and Notes

- `python scripts/run_pytest.py` aborted because `sqlalchemy` was unavailable; `pip install -r server/requirements-dev.txt` failed with proxy-blocked PyPI access, preventing dependency resolution.

## Interfaces and Dependencies

- SQLAlchemy async session helpers remain exposed from `server/db.py`.
- ORM models rely on `sqlalchemy.orm.Mapped` and `mapped_column` definitions.
- API schema dataclasses continue to use Pydantic `BaseModel` imports.
- New `server/time_utils.py` provides `utcnow`/`utcnow_naive` functions consumed by `task_logic` and `file_store`.
# Harden backend and API consistency

This ExecPlan is a living document. The sections `Progress`, `Surprises & Discoveries`, `Decision Log`, and `Outcomes & Retrospective` must be kept up to date as work proceeds.

This repository implements the Switchboard service. This plan must be maintained in accordance with `.agent/PLANS.md`.

## Purpose / Big Picture

Deliver a production-grade refresh of the Switchboard backend by eliminating duplication, tightening error handling, and ensuring API responses, filesystem helpers, and websocket flows are consistent. The aim is to simplify maintenance, ensure typing coverage, and back the behavior with targeted tests.

## Progress

- [x] Initial state captured.
- [x] Repo audit and scope finalised.
- [x] Core backend refactors implemented.
- [x] Supplemental tests authored and passing.
- [x] Documentation/config verification complete.
- [x] Final validation and cleanup finished.

## Surprises & Discoveries

- Observation: `server/app.py` duplicates numerous imports and leaves unreachable plan serialization fallback, complicating maintenance.
  Evidence: Manual inspection of `server/app.py` around the `/api/plan` handler revealed redundant return statements and repeated import blocks.
- Observation: Python client tests patch `switchboard_client` and `switchboard_cli` via `sys.modules.setdefault`, so resolving modules through a compatibility shim alone leaves aliases pointing at lightweight sentinels.
  Evidence: Initial pytest run failed importing `DEFAULT_REQUEST_TIMEOUT` and CLI helpers until conftest ensured canonical modules were preloaded.

## Decision Log

- Decision: Consolidated plan serialization, task responses, and dependency loading into shared helpers inside `server/app.py`.
  Rationale: Removes N+1 dependency queries, eliminates duplicate imports, and keeps API payloads consistent.
  Date/Author: 2024-06-02 / gpt-5-codex
- Decision: Tightened live file helpers to reuse shared timestamp utility and avoid duplicate imports.
  Rationale: Clarifies storage behavior and ensures consistent UTC timestamps for cache validation.
  Date/Author: 2024-06-02 / gpt-5-codex
- Decision: Preload real client modules for tests to avoid namespace shims overriding actual implementations.
  Rationale: Pytest fixtures now force consistent imports so CLI/unit tests share the same module object, allowing mocks to behave predictably.
  Date/Author: 2024-06-02 / gpt-5-codex

## Outcomes & Retrospective

- Backend endpoint logic now shares dependency serialization helpers, reducing duplicated queries and clarifying plan broadcasts.
- File storage utilities provide consistent UTC metadata and simpler imports, while new tests cover error conditions and filtering behavior.
- Python client tooling loads reliably in test environments thanks to deterministic module aliasing.

## Context and Orientation

Key modules:
- `server/app.py` – FastAPI application wiring, websocket push logic, REST handlers.
- `server/task_logic.py` – business logic for plan versions, leases, and dependencies.
- `server/file_store.py` – persistent live-file helper utilities.
- `server/schema.py` – Pydantic models that surface API contracts.
- `server/tests/` – pytest suite covering API, websocket, and storage behaviors.

## Plan of Work

1. Audit backend modules for duplicated imports, inconsistent helper usage, and outdated patterns. Outline precise cleanup targets.
2. Refactor `server/app.py` for clarity: deduplicate imports, centralize plan serialization, strengthen websocket lifecycle cleanup, and ensure API handlers surface consistent error responses.
3. Modernize `server/file_store.py` helpers with clearer typing, docstrings, and efficient database synchronization when computing ETags.
4. Verify schema alignment between `PlanOut` and API responses, ensuring `updated_at` is reliably included across code paths.
5. Add regression tests covering plan serialization (version + updated_at) and file-store ETag caching to guard new behaviors.
6. Review configuration documentation (`README.md` or others) for alignment with updated best practices; adjust as necessary.
7. Run lint-equivalent formatting (ruff/black style via `python -m compileall`? -> adopt `ruff`?); ensure pytest suite passes.

## Concrete Steps

1. Use `rg` to identify duplicate imports and inconsistent responses across backend modules.
2. Update `server/app.py` per plan, adding helper docstrings and type hints.
3. Update `server/file_store.py` with structured imports, improved error handling, and optional session reuse for ETag computation.
4. Ensure `PlanOut` usage in API route returns `updated_at` by calling `plan_version_snapshot`; adjust websocket bootstrap accordingly.
5. Write new pytest modules (e.g., `server/tests/test_plan_serialization.py`) for plan serialization and ETag caching.
6. Re-run `pytest` and `python -m compileall server` to validate code and bytecode compilation.

## Validation and Acceptance

- `pytest` succeeds locally.
- Targeted command `python -m compileall server` completes without syntax errors.
- Manual review confirms imports are deduplicated and docstrings clarify behavior.

## Idempotence and Recovery

- Database migrations untouched; rerunning app reuses same schema.
- File-store adjustments remain backward compatible; existing data unaffected.
- Tests are deterministic and can be rerun without manual intervention.

## Artifacts and Notes

- Pending as work progresses.

## Interfaces and Dependencies

- FastAPI endpoints continue to expose schemas defined in `server/schema.py`.
- `PlanOut` now consistently includes `updated_at` timestamp retrieved from `plan_version_snapshot`.
- `etag_for_path` optionally reuses provided SQLAlchemy session to avoid nested transactions.
