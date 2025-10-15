# Parallel hardening & live-doc rollout ExecPlan

This ExecPlan is a living document. The sections Progress, Surprises & Discoveries, Decision Log, and Outcomes & Retrospective must be kept up to date as work proceeds.

This repository implements the Switchboard service. This plan must be maintained in accordance with .agent/PLANS.md and mirrored via the live files API so collaborators can follow along.

## Purpose / Big Picture

Coordinate eight parallel workstreams that harden the API, leasing, plan versioning, live files, client tooling, UI, and ops packaging while preserving the production-lean FastAPI service that already serves HTTP, WebSocket, and live file traffic for agents and the admin UI.

## Progress

- Initial state (plan drafted, not yet mirrored live)
- Milestone 1 – ExecPlan committed and published to /live/docs/execplans/001_parallel_hardening.md
- Milestone 2 – Branch scaffolds created for A–H with empty commits
- Milestone 3 – Workstreams A–G implemented and validated independently
- Milestone 4 – Integration nits (branch H) applied after A–G land
- Milestone 5 – Final validation walkthrough documented in Outcomes

## Surprises & Discoveries

Observation: None recorded yet (populate as implementation reveals new information).  
Evidence: N/A at plan kickoff.

## Decision Log

Decision: Maintain a single ExecPlan as the authoritative coordination artifact and mirror it via /api/files so every agent can observe updates.  
Rationale: Complex, multi-branch efforts require a living plan per the agent guidance; mirroring keeps the live document reachable over /live/&lt;path&gt;.  
Date/Author: (update when executed)

## Outcomes & Retrospective

Pending completion of Milestone 5; summarize deltas versus purpose and link to the mirrored ExecPlan URL.

## Context and Orientation

server/app.py hosts REST endpoints for agents, tasks, WebSockets, and live file serving, and wires in schemas, models, and task logic.

server/schema.py defines the current Pydantic models for requests/responses that need tightening and expansion.

server/task_logic.py manages leases, availability, and plan versioning using a simple timestamp sum that must be replaced.

server/models.py holds SQLAlchemy models for tasks, leases, and files; additions must avoid breaking existing schema expectations.

server/file_store.py handles live file persistence, currently without ETag or conditional GET support.

client/python/switchboard_client.py offers basic task lifecycle helpers that need packaging and a CLI loop.

web/index.html renders the HTMX admin UI lacking filters/badges/dep visualization.

ops/docker-compose.yml, server/Dockerfile, and README ops instructions form the deploy story to be polished.

Existing automated coverage is minimal (server/tests/test_tasks.py), so new tests must be added per workstream requirements.

## Plan of Work

### Milestone 1 – ExecPlan creation & mirroring

Author this plan in .agent/execplans/001_parallel_hardening.md, ensure directory exists, and mirror via PUT /api/files/docs/execplans/001_parallel_hardening.md for /live/ access.

Commit on main: docs: add parallel hardening ExecPlan and publish to live.

### Milestone 2 – Branch scaffolding

Create branches feature/api-contracts, feature/lease-harden, feature/plan-version-counter, feature/live-files-etag, feature/python-client-package, feature/ui-listing-filters, chore/ops, and chore/integration-nits.

Add minimal placeholder files (e.g., empty test modules, README stubs) within each branch’s allowed directories to avoid merge conflicts later.

### Workstream A – API Contracts & JSON Schemas (feature/api-contracts)

Enhance Pydantic models in server/schema.py with explicit enums/defaults/response models and create typed response models for every route.

Annotate FastAPI routes with response_model or response_model_exclude_unset as needed (route signatures only).

Generate a documented OpenAPI snapshot at server/openapi.md describing each endpoint.

Ensure /openapi.json returns a valid schema (FastAPI auto-generation); adjust server/requirements.txt only if required for schema generation.

### Workstream B – Lease Logic & Concurrency Hardening (feature/lease-harden)

Introduce explicit lease constants/configuration in server/task_logic.py and ensure heartbeat/expiry/rescheduling is robust.

Update server/models.py if auxiliary fields are needed without breaking schema (e.g., indexes/config flags).

Add server/tests/test_leases.py covering checkout→heartbeat→expiry→re-checkout, abandon path, and completion with/without active lease.

### Workstream C – Plan Versioning & Event Broadcast (feature/plan-version-counter)

Replace timestamp sum with a monotonic counter (e.g., new table PlanVersion) in server/models.py; adjust plan_version logic in server/task_logic.py and server/app.py plan fetch to use it.

Emit WebSocket broadcast {type:"plan_version"} after task create/update/delete and live file PUT (may share helper to avoid duplication).

Add server/tests/test_plan_version.py to verify counter strictly increases on task/file mutations.

### Workstream D – Live Files: ETags & Conditional GET (feature/live-files-etag)

Update server/file_store.py to compute stable ETags (likely from SHA) and surface metadata for GET handling.

Modify /live/{path} handler in server/app.py to return ETag and 304 when If-None-Match matches the stored hash.

Expand server/tests/test_files.py (new) for ETag/304 coverage plus regression on PUT response payload.

### Workstream E – Python Client Packaging (feature/python-client-package)

Introduce pyproject.toml, CLI entry point (switchboard_cli.py), and README in client/python/ to allow editable install and CLI heartbeat loop built on the existing client class.

Ensure CLI exercises checkout/heartbeat/complete flow against server endpoints (/api/tasks/*).

Keep server untouched.

### Workstream F – Admin UI Quality Pass (feature/ui-listing-filters)

Update web/index.html to render status badges, filtering controls, and textual dependency visualization while keeping HTMX/Tailwind usage simple.

Add static assets under web/static/ if needed (icons/css). Ensure server already serves /static mount.

### Workstream G – Docker & Ops Polish (chore/ops)

Refine ops/docker-compose.yml (healthcheck, bind mounts), ops/.env.example, server/Dockerfile, and README ops section to ensure docker compose -f ops/docker-compose.yml up --build works from clean clone.

Add healthcheck script/command referencing /health endpoint.

### Workstream H – Integration Nits (chore/integration-nits)

After A–G merge, perform minimal shared-file tweaks (e.g., consolidated imports) required for coherence; keep diffs tiny and well isolated.

### Milestone 5 – Final Validation & Retrospective

Run manual scenario: create tasks with dependencies, exercise Python CLI loop, observe WS-driven UI refresh, upload/update live files with ETag checks.

Record validation outputs in Artifacts and Notes and summarize in Outcomes.

## Concrete Steps

### Environment setup (once)

```bash
python -m venv .venv && source .venv/bin/activate && pip install -r server/requirements.txt
```

### Create plan directory if absent

```bash
mkdir -p .agent/execplans
```

### Save ExecPlan markdown at .agent/execplans/001_parallel_hardening.md (no triple backticks). Commit per Milestone 1

### Mirror plan

```bash
curl -X PUT http://localhost:8000/api/files/docs/execplans/001_parallel_hardening.md --data-binary @.agent/execplans/001_parallel_hardening.md -H "Content-Type: text/markdown"
```

### For each branch (A–H)

```bash
git checkout -b <branch>, add scaffolds/tests per scope, commit an initial placeholder change, and open PR.
```

### Implement workstreams A–G in parallel, confining edits to allowed paths. Update ExecPlan Progress after each session

### Run targeted tests per branch (pytest -q server/tests/test_leases.py, etc.) plus full suite before merging

### Execute integration nits on chore/integration-nits after upstream branches merge

### Final validation

```bash
launch uvicorn server.app:app --reload --port 8000, run Python CLI loop (switchboard-cli run ...), interact with UI, verify live file ETag behavior, and document outcomes.
```

## Validation and Acceptance

### Automated

All new and existing tests (pytest -q) pass, covering leases, plan version counter, live files, and client packaging behaviors.

### Manual

- Confirm /openapi.json documents responses, and server/openapi.md matches actual endpoints.
- Exercise CLI loop against server to observe checkout/heartbeat/complete transitions.
- Verify UI filters/badges and dependency display in browser.
- Validate Docker compose spin-up with healthcheck success.
- Use curl with If-None-Match to confirm 304 handling for live files.

## Idempotence and Recovery

Leases expire automatically based on LEASE_SECONDS; ensure new constants support configurable recovery windows.

Live file PUTs overwrite atomically using SHA storage; repeated uploads remain safe.

Branch-specific changes avoid shared files; if rollback needed, revert branch or close PR without affecting others.

Docker compose and CLI commands can be rerun; ensure scripts check for existing resources before recreation.

## Artifacts and Notes

Attach test outputs, curl transcripts, and screenshots (UI) to PRs and link within ExecPlan.

Record mirrored ExecPlan URL and final validation evidence here once available.

## Interfaces and Dependencies

REST endpoints in server/app.py (/api/tasks, /api/plan, /api/files, /live/{path}, /health).

Lease helpers (checkout_task, heartbeat, complete, abandon, plan_version).

SQLAlchemy models Task, TaskDependency, Lease, FileEntry.

Python client class SwitchboardClient for CLI integration.

HTMX/Tailwind UI structure in web/index.html.

Docker runtime files (ops/docker-compose.yml, server/Dockerfile).

Please copy this plan into the repository file, commit it, and publish it to the live docs endpoint before starting the implementation milestones. Update the living sections as progress is made.

## Testing

No automated tests were executed in this planning-only QA review.
