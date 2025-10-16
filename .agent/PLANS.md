
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

Summarize outcomes vs. purpose.

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
