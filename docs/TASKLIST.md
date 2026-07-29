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
  - Progress: 2026-06-27 — configurable streaming limit implemented and symlink-escape regression added; Linux execution remains required and is tracked by issue #104.
- [x] Run and record release-quality gates from a clean Python 3.11 environment — TK-20260627-005
  - Completed: 2026-06-27 — historical clean-environment evidence recorded; current validation results belong in active PRs, living ExecPlans, and `PUBLIC_RELEASE_AUDIT.md`, while the protected matrix now includes strict Mypy.
- [x] Reconcile README repository-essential links and replace stale status claims — TK-20260627-006
  - Completed: 2026-06-27 — corrected docs paths, marked the 2025 report historical, and established the public status and release-audit records.
- [x] Implement the versioned execution control plane with explicit approval, workers, runs, leases, and trusted manifest identities — TK-20260713-001
  - Completed: 2026-07-13 — PR: #116 — issue #112 merged at `765b7167457e523b9edc0b230039ed407060274b`.
- [x] Implement the outbound trusted local worker with exact-SHA disposable worktrees and fixed reviewed argv — TK-20260716-001
  - Completed: 2026-07-16 — PR: #119 — issue #113 merged at `f549ab7bb2efc274dc2d79e12502d5653ddc8886`.
- [x] Merge the reviewed exact-SHA compact evidence workflow after explicit owner authorization — TK-20260722-001
  - Completed: 2026-07-23 — PR: #120 — issue #114 squash-merged at `dcb8e283f8445dd76f215a98023197d8ed5acab3` after connector review and a fully green protected matrix.
- [ ] Select one immutable release-candidate SHA and complete Linux, clean-clone, Docker, and final audit gates — TK-20260722-002
  - Tracked by issues #95 and #104; formal release and production deployment remain unauthorized.
- [ ] Implement the outbound GitHub exact-PR validation and compact-result adapter — TK-20260722-003
  - Tracked by issue #122; implementation is unblocked from the #120 merge and fresh execution must remain supported.
- [ ] Implement exact evidence reuse with worker-local availability proof — TK-20260722-004
  - Tracked by issue #121; implementation is unblocked from the #120 merge and remains opt-in after fresh execution.
