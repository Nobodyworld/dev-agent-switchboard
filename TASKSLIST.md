# TASKLIST: Task Compilation

-*NEVER REMOVE SPEC.md, STYLE-GUIDE.md, or TASKLIST.md FROM THE ROOT*

Use this file to compile and track all tasks that need to be completed for this repository. Check off items as they are finished. Keep each task on a single line. Check off already completed tasks and keep things in chronological order when updating and adding to the file. Follow Template Entry below.

Keep entries one-line, oldest-first. When completing a task, check it off and append a one-line completion note indented underneath (date + PR/link + 1â€“2 sentence summary).

## Template (single-line + optional completion note)

```text
- [ ] Short task description â€” TK-YYYYMMDD-###
```

Completion note (indented, one line):

```text
  - Completed: YYYY-MM-DD â€” PR: <url> â€” short summary
```

---

## Tasks

- [x] Implement queue prioritisation policy in `checkout_task` so higher-priority work is served first - task-queue-prioritisation-policy - Completed 2025-10-30 (link: REPORTS.md#report-task-queue-prioritisation-policy)
- [x] Export Prometheus-ready readiness metrics from `/health/ready` for alerting - task-health-metrics-export - Completed 2025-10-30 (link: REPORTS.md#report-task-health-metrics-export)
- [x] Add automatic runner abandonment controls (e.g., `--max-heartbeats`) to the local runner CLI - task-runner-abandonment-workflow - Completed 2025-10-30 (link: REPORTS.md#report-task-runner-abandonment-workflow)
