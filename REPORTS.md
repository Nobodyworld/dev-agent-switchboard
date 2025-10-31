# REPORTS: Agent PR Logging Template

-*NEVER REMOVE TASK.md, TASKSLIST.md, REPORTS.md, or URGENT.md FROM THE ROOT*

Use this file to log completed pull requests in chronological order. Each entry should follow the format below.

## PR History

### YYYY-MM-DD - [PR Title](PR_URL)

**Task Report Unique Identifier**: Unique entry identifier for hyperlinking from TASKLIST.md.
**Task Unique Identifier**: Hyperlink to TASKLIST.md task.
**Description**: Brief description of what was accomplished
**References**: Related issues, tasks, or context
**Problems Solved**: Key issues addressed
**Next Steps**: Follow-up work or considerations

### 2025-10-30 - [feat: prioritise checkout and resilience improvements](#)

**Task Report Unique Identifier**: report-task-queue-prioritisation-policy
**Task Unique Identifier**: [task-queue-prioritisation-policy](TASKSLIST.md#task-queue-prioritisation-policy)
**Description**: Added persistent task priority metadata, API schema updates, and repository ordering so higher-priority work is dispatched first while preserving compatibility with targeted checkouts and analytics.
**References**: `server/models.py`, `server/application/task_service.py`, `server/api/routers/tasks.py`, `server/tests/test_task_service.py`
**Problems Solved**: Checkout now honours explicit task priority, ensuring urgent jobs are assigned ahead of older, lower-priority items without regressing dependency handling.
**Next Steps**: Consider exposing administrative endpoints to reprioritise existing tasks dynamically.

### 2025-10-30 - [feat: prioritise checkout and resilience improvements](#)

**Task Report Unique Identifier**: report-task-health-metrics-export
**Task Unique Identifier**: [task-health-metrics-export](TASKSLIST.md#task-health-metrics-export)
**Description**: Instrumented readiness probes with Prometheus counters and gauges, exposed diagnostics summaries, and verified behaviour via integration tests.
**References**: `server/observability/health.py`, `server/tests/test_health.py`
**Problems Solved**: Operators can now alert on repeated readiness failures and inspect probe results programmatically, closing the observability gap for `/health/ready`.
**Next Steps**: Evaluate exporting the readiness metrics catalog through the admin metrics endpoint for external dashboards.

### 2025-10-30 - [feat: prioritise checkout and resilience improvements](#)

**Task Report Unique Identifier**: report-task-runner-abandonment-workflow
**Task Unique Identifier**: [task-runner-abandonment-workflow](TASKSLIST.md#task-runner-abandonment-workflow)
**Description**: Added a `--max-heartbeats` option to the CLI, extended runtime configuration, and improved heartbeat loop ergonomics to automatically abandon idle tasks after a configurable limit.
**References**: `client/python/switchboard_cli.py`, `client/python/runtime_config.py`, `client/python/tests/test_cli.py`
**Problems Solved**: Prevents unattended runners from holding leases indefinitely by letting operators cap heartbeat attempts and ensuring clean abandonment.
**Next Steps**: Surface max-heartbeat defaults in server settings so orchestration can recommend safe limits.

---

*This file serves as a chronological record of agent work and accomplishments.*
