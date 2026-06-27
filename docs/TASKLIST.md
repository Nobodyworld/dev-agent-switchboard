# TASKLIST: Task Compilation

- *Keep SPEC.md, STYLE-GUIDE.md, and TASKLIST.md in this `docs/` directory and preserve their README links.*

Use this file to compile and track all tasks that need to be completed for this repository. Check off items as they are finished. Keep each task on a single line. Check off already completed tasks and keep things in chronological order when updating and adding to the file. Follow the template entry below.

Keep entries one line, oldest first. When completing a task, check it off and append a one-line completion note indented underneath (date + PR/link + 1–2 sentence summary).

## Template (single line + optional completion note)

```text
- [ ] Short task description — TK-YYYYMMDD-###
```

Completion note (indented, one line):

```text
  - Completed: YYYY-MM-DD — PR: <url> — short summary
```

---

## Tasks

- [x] Implement queue prioritisation policy in `checkout_task` so higher-priority work is served first - task-queue-prioritisation-policy - Completed 2025-10-30 (reference: docs/reports/operations-report.md)
- [x] Export Prometheus-ready readiness metrics from `/health/ready` for alerting - task-health-metrics-export - Completed 2025-10-30 (reference: docs/reports/operations-report.md)
- [x] Add automatic runner abandonment controls (e.g., `--max-heartbeats`) to the local runner CLI - task-runner-abandonment-workflow - Completed 2025-10-30 (reference: docs/reports/operations-report.md)
- [x] Make validation package discovery deterministic, correct the CI coverage target, and protect configured live-file writes — TK-20260627-001
  - Completed: 2026-06-27 — PR: pending — added the scripts package boundary, fixed coverage module notation, and enforced the existing admin-token policy on live-file uploads.
- [x] Add atomic concurrent checkout guarantees and regression tests across supported databases — TK-20260627-002
  - Completed: 2026-06-27 — PR: pending — added a conditional pending-task claim, eliminated first-read system-state writes, and proved a two-agent race produces exactly one lease.
- [x] Verify lease ownership, expiry races, and dependency unlocking with objective integration tests — TK-20260627-003
  - Completed: 2026-06-27 — PR: pending — rejected wrong-agent lifecycle actions, prevented expired-heartbeat revival, and validated expiry re-checkout plus dependency unlocking in the passing integration suite.
- [ ] Validate live-file symlink safety and enforce a configurable upload-size limit — TK-20260627-004
  - Progress: 2026-06-27 — configurable streaming limit implemented and symlink-escape regression added; local Windows symlink creation was unavailable, so Linux execution remains required.
- [x] Run and record all release gates from a clean Python 3.11 environment — TK-20260627-005
  - Completed: 2026-06-27 — PR: pending — Python 3.11.14 produced 226 passed/2 skipped, passing Ruff, Bandit, TODO, coverage, and pip-audit gates; strict mypy still reports 76 existing errors.
- [x] Reconcile README repository-essential links and replace stale status claims — TK-20260627-006
  - Completed: 2026-06-27 — PR: pending — corrected docs paths, marked the 2025 report historical, and published the current hardening status.
