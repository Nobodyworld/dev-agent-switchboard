# TASKLIST: Task Compilation

- *Never remove SPEC.md, STYLE-GUIDE.md, or TASKLIST.md from the repository root.*

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
