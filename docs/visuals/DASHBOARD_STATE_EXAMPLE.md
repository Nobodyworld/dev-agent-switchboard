# Dashboard State During Two-Agent Workflow

This shows what the operator UI displays as agents progress through dependent tasks.

## Phase 1: Agent 1 Leases Task A

```
Switchboard Dashboard
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

📊 Task Plan (Version: 1)
├─ 🟢 Task A: "Prepare data"
│  Status: IN_PROGRESS
│  Leased by: Agent-1
│  Lease expires: 2026-07-01 10:30:45 UTC (+45 seconds remaining)
│  Assigned to: Agent-1
│
├─ 🔴 Task B: "Process results"
│  Status: BLOCKED
│  Blocked by: Task A (IN_PROGRESS)
│  Dependency: A → B
│
└─ ⚫ Task C: "Generate report"
   Status: BLOCKED
   Blocked by: Task B (BLOCKED)
   Dependency: B → C

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Real-time Heartbeat Monitor:
• Agent-1: Task A heartbeat OK (60 seconds ago, next due in 15s)
• Agent-2: Waiting for checkout...

Plan Version Change Log:
  v1 [Current] ← Initial state loaded
```

## Phase 2: Agent 1 Completes Task A

```
Switchboard Dashboard
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

📊 Task Plan (Version: 2) ← UPDATED VIA WEBSOCKET ✨
├─ ✅ Task A: "Prepare data"
│  Status: COMPLETE
│  Completed by: Agent-1
│  Completion notes: "Data prepared and validated"
│
├─ 🟢 Task B: "Process results"
│  Status: READY ← UNLOCKED! NOW AVAILABLE
│  No lease (ready for checkout)
│  Ready at: 2026-07-01 10:29:00 UTC
│
└─ 🔴 Task C: "Generate report"
   Status: BLOCKED
   Blocked by: Task B (READY)
   Dependency: B → C

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Real-time Heartbeat Monitor:
• Agent-1: Task A completed ✓
• Agent-2: [Attempting checkout...]

Plan Version Change Log:
  v2 [Current] ← Agent-1 completed Task A
  v1         ← Initial state loaded
```

## Phase 3: Agent 2 Leases Task B

```
Switchboard Dashboard
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

📊 Task Plan (Version: 3)
├─ ✅ Task A: "Prepare data"
│  Status: COMPLETE
│  Completed by: Agent-1
│
├─ 🟢 Task B: "Process results"
│  Status: IN_PROGRESS
│  Leased by: Agent-2
│  Lease expires: 2026-07-01 10:31:05 UTC (+60 seconds remaining)
│
└─ 🔴 Task C: "Generate report"
   Status: BLOCKED
   Blocked by: Task B (IN_PROGRESS)
   Dependency: B → C

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Real-time Heartbeat Monitor:
• Agent-1: Task A complete (idle)
• Agent-2: Task B heartbeat OK (now in progress)

Plan Version Change Log:
  v3 [Current] ← Agent-2 leased Task B
  v2         ← Agent-1 completed Task A
  v1         ← Initial state loaded
```

## Phase 4: Agent 2 Completes Task B

```
Switchboard Dashboard
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

📊 Task Plan (Version: 4) ← UPDATED VIA WEBSOCKET ✨
├─ ✅ Task A: "Prepare data"
│  Status: COMPLETE
│  Completed by: Agent-1
│
├─ ✅ Task B: "Process results"
│  Status: COMPLETE
│  Completed by: Agent-2
│  Completion notes: "Results processed successfully"
│
└─ 🟢 Task C: "Generate report"
   Status: READY ← UNLOCKED! NOW AVAILABLE
   No lease (ready for checkout)
   Ready at: 2026-07-01 10:30:30 UTC

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Real-time Heartbeat Monitor:
• Agent-1: Task A complete (idle)
• Agent-2: Task B completed ✓

Plan Version Change Log:
  v4 [Current] ← Agent-2 completed Task B
  v3         ← Agent-2 leased Task B
  v2         ← Agent-1 completed Task A
  v1         ← Initial state loaded
```

## Key Observations

1. **Real-time Synchronization**: Dashboard updates immediately via WebSocket when plan version changes
2. **Lease Visibility**: Operators can see who holds which lease and when it expires
3. **Dependency Tracking**: Blocked tasks show exactly which task is blocking them
4. **Completion Evidence**: Task notes and completion timestamps are recorded
5. **No Polling**: Clients don't need to refresh; all updates push to connected WebSocket clients

---

See [Two-Agent Workflow](./TWO_AGENT_WORKFLOW.md) for the detailed sequence diagram.
