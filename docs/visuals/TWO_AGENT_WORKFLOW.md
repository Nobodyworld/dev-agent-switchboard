# Two-Agent Workflow Sequence

This diagram shows the core Switchboard coordination pattern: how two agents safely work on dependent tasks through lease-based ownership and live state synchronization.

## Scenario

**Initial State:**
- Task A: "Prepare data" → ready (no dependencies)
- Task B: "Process results" → blocked (depends on Task A)
- Task C: "Report" → blocked (depends on Task B)

## Execution Flow

```mermaid
sequenceDiagram
    participant A1 as Agent 1
    participant API as Switchboard API
    participant Plan as Task Plan
    participant WS as WebSocket
    participant DB as Dashboard
    participant A2 as Agent 2

    Note over Plan: Initial: A=ready, B=blocked(→A), C=blocked(→B)

    A1->>API: POST /checkout (Agent 1)
    API->>Plan: Find ready task
    Plan-->>API: Task A (ready)
    API->>API: Create lease for A (expiry: +60s)
    API-->>A1: Task A payload + lease_id + deadline

    Note over API: Task A locked to Agent 1
    A1->>API: Do work...

    A1->>API: POST /heartbeat (keep alive)
    API->>Plan: Refresh lease expiry
    API-->>A1: {"ok": true}

    Note over API: Lease extended to +60s

    A2->>API: POST /checkout (Agent 2 - too early)
    API->>Plan: Find ready task
    Plan-->>API: None (A is leased, B blocked)
    API-->>A2: {"task": null, "reason": "no_ready_tasks"}

    Note over A2: Agent 2 waits...

    A1->>API: POST /complete task A
    API->>Plan: Mark Task A complete
    Plan->>Plan: Unlock Task B (A complete)
    Plan->>Plan: Increment version → v2
    API->>API: Delete lease for A
    API->>WS: Broadcast plan.version=v2
    API-->>A1: {"ok": true, "task_id": "A"}

    WS->>DB: Plan updated! Refresh
    DB->>DB: Reload task graph
    DB->>DB: Show B now ready

    A2->>API: POST /checkout (Agent 2 - now ready)
    API->>Plan: Find ready task
    Plan-->>API: Task B (now ready)
    API->>API: Create lease for B
    API-->>A2: Task B payload + lease_id + deadline

    Note over DB: Dashboard shows:<br/>A=complete, B=in_progress, C=blocked(→B)

    A2->>API: POST /heartbeat (keep alive)
    API->>Plan: Refresh lease expiry
    API-->>A2: {"ok": true}

    A2->>API: POST /complete task B
    API->>Plan: Mark Task B complete
    Plan->>Plan: Unlock Task C (B complete)
    Plan->>Plan: Increment version → v3
    API->>API: Delete lease for B
    API->>WS: Broadcast plan.version=v3
    API-->>A2: {"ok": true, "task_id": "B"}

    WS->>DB: Plan updated! Refresh
    DB->>DB: Show C now ready

    Note over DB: All agents can see current state:<br/>A=complete, B=complete, C=ready
```

## Key Guarantees

| Guarantee | How Enforced |
|-----------|---|
| **Only one agent works on a task** | Checkout creates an exclusive lease; concurrent attempts fail |
| **Agent must keep heartbeat** | Lease expires if heartbeat stops; other agents can reclaim task |
| **Tasks unlock correctly** | Completion marks task done and checks dependents; DAG ensures proper ordering |
| **Dashboard stays in sync** | WebSocket broadcasts plan.version; clients refresh state |
| **No split-brain** | Single database source of truth; all agents read from same server |

## Test Coverage

- Regression tests: [server/tests/test_task_lifecycle.py](../../server/tests/test_task_lifecycle.py)
- WebSocket plan broadcasts: [server/tests/test_websocket_plan.py](../../server/tests/test_websocket_plan.py)
- UI state sync: [web/tests/test_ui.py](../../web/tests/test_ui.py)

---

This pattern scales to N agents and arbitrary dependency graphs. The lease mechanism prevents duplication, and the broadcast ensures coordination without polling.
