
# AGENTS

This repository defines how coding agents should behave when interacting with the Switchboard.

## ExecPlans

When writing complex features or significant refactors, use an **ExecPlan** (as described in `.agent/PLANS.md`) from design through implementation.

Shorthand in prompts: **ExecPlan**. Example: “Create an ExecPlan for implementing hierarchical task unlocks and follow it to completion.”

## Agent Rules of Engagement

1. **Register** yourself via `POST /api/agents` with a unique `agent_id` (your chosen name).
2. **Discover tasks** via `GET /api/plan` or `GET /api/tasks?status=available`.
3. **Checkout** exactly one task at a time using `POST /api/tasks/checkout?agent_id=<id>`.
4. **Heartbeat** every 60 seconds with `POST /api/tasks/{task_id}/heartbeat?agent_id=<id>` until complete.
5. **Complete** with `POST /api/tasks/{task_id}/complete?agent_id=<id>` and include notes.
6. **Abandon** if you cannot proceed: `POST /api/tasks/{task_id}/abandon?agent_id=<id>`.
7. **Watch plan updates** via WebSocket: `ws://<host>/ws/plan`.
8. **Publish artifacts** by `PUT /api/files/<path>` and reference them by `GET /live/<path>`.
9. When work is complex, author or update an **ExecPlan** in `.agent/PLANS.md` and mirror it via the live files API to keep a single public URL accessible to any LLM.

Agents must behave idempotently: retries are allowed; leases automatically expire if heartbeats stop.
