# Automation Roles

This catalog enumerates agent-friendly responsibilities that build on the
Switchboard stewardship tooling.

## Metrics Steward
- **Trigger** – Run after major merges or before releases.
- **Actions** – Execute `scripts/audit_metrics.py --force` to refresh
  `reports/system_metrics.json`, `reports/complexity.txt`, and
  `reports/perf_metrics.json`; file follow-up tasks if coverage or complexity
  regress.【F:scripts/audit_metrics.py†L1-L220】【F:reports/system_metrics.json†L1-L16】
- **Artifacts** – Updated metrics in `reports/` plus appended notes in
  `docs/reports/stewards-report.md`.

## Schema Custodian
- **Trigger** – Whenever API payloads change (e.g., new fields in
  `server/schema.py`).
- **Actions** – Update `docs/message-schema.md`, run the documentation tests
  (`pytest docs` when available), and broadcast plan deltas if new task fields
  appear.【F:server/schema.py†L1-L200】【F:docs/message-schema.md†L1-L120】
- **Artifacts** – Refreshed schema docs and release note annotations.

## Broadcast Guardian
- **Trigger** – After plan or websocket changes.
- **Actions** – Use the `PLAN_BROADCASTER` helpers inside `server/app.py` to send
  synthetic plan updates, verifying dashboard and clients process the
  `PlanOut` contract; capture traces via `/api/observability/telemetry`.
  【F:server/app.py†L500-L580】【F:server/observability/telemetry.py†L1-L220】
- **Artifacts** – QA notes, telemetry snapshots, and optional plan fixtures.

## Documentation Curator
- **Trigger** – Onboarding new agents or delivering releases.
- **Actions** – Ensure `docs/guides/automation.md`, `RELEASE_NOTES.md`, and
  `docs/reports/stewards-report.md` reflect the latest tooling; verify coverage thresholds and
  automation entry points remain consistent.【F:docs/guides/automation.md†L1-L80】【F:RELEASE_NOTES.md†L1-L80】【F:docs/reports/stewards-report.md†L1-L120】
- **Artifacts** – Updated documentation with explicit references to agent-safe
  tasks (# agent-entrypoint / # agent-safe-task markers).
