# Switchboard Architecture

## System Components

```
┌─────────────────────────────────────────────────────────────────────┐
│                          Switchboard System                          │
├─────────────────────────────────────────────────────────────────────┤
│                                                                      │
│  ┌──────────────────┐         ┌──────────────────┐                 │
│  │   Agent 1        │         │   Agent 2        │                 │
│  │  (Python CLI)    │         │  (Python CLI)    │                 │
│  └────────┬─────────┘         └────────┬─────────┘                 │
│           │                            │                            │
│           │  REST + Lease Heartbeat   │                            │
│           │  Checkout, Complete        │                            │
│           └────────────────┬───────────┘                            │
│                            │                                        │
│        ┌──────────────────────────────────────────┐                │
│        │      FastAPI Server (port 8000)         │                │
│        ├──────────────────────────────────────────┤                │
│        │  • POST /api/tasks/checkout              │                │
│        │  • POST /api/tasks/{task_id}/heartbeat   │                │
│        │  • POST /api/tasks/{task_id}/complete    │                │
│        │  • POST /api/tasks/{task_id}/abandon     │                │
│        │  • PUT /api/files/<path> (uploads)       │                │
│        │  • GET /live/<path> (downloads)          │                │
│        │  • WS /ws/plan (live updates)            │                │
│        └──────────────────────────────────────────┘                │
│                ↓                                 ↓                   │
│         ┌─────────────┐              ┌──────────────────┐          │
│         │  SQLite DB  │              │  Live File Store │          │
│         │ • Tasks     │              │  (filesystem)    │          │
│         │ • Leases    │              │                  │          │
│         │ • Deps      │              │ Reference docs   │          │
│         └─────────────┘              └──────────────────┘          │
│                                                                      │
│  ┌──────────────────────────────────────────────────────────────┐  │
│  │  Dashboard UI (HTMX + Tailwind)                            │  │
│  │  • Real-time plan state via WebSocket                      │  │
│  │  • Task dependency graph visualization                     │  │
│  │  • Lease ownership & expiry tracking                       │  │
│  │  • Live task heartbeat monitoring                          │  │
│  └──────────────────────────────────────────────────────────────┘  │
│                                                                      │
└─────────────────────────────────────────────────────────────────────┘
```

## Data Flow: Task Lease & Completion

```
1. Checkout Flow:
   Agent 1 → POST /api/tasks/checkout → Check plan DAG
                                       → Find ready task (no blockers)
                                       → Create lease with expiry
                                       → Return task + deadline

2. Heartbeat:
   Agent 1 → POST /api/tasks/{task_id}/heartbeat → Refresh lease expiry
                                                  → Keep task locked

3. Completion:
   Agent 1 → POST /api/tasks/{task_id}/complete → Mark task done
                                                 → Delete lease
                                                 → Increment plan version
                                                 → Broadcast to dashboard & agents
                                                 → Unlock dependent tasks

4. Dashboard Update:
   WebSocket ← plan version → Dashboard
     /ws/plan    increment      reloads &
     broadcast               refreshes UI
```

## Key Security Controls

| Control | Implementation |
|---------|---|
| **Path Containment** | `file_store.py` uses `pathlib.Path.resolve()` to resolve symlinks and validate paths stay within `FILES_ROOT` via `relative_to()` |
| **Lease Ownership** | Only lease holder can update task state; concurrent checkout attempts are rejected |
| **Token Protection** | Privileged operations (live-file writes, maintenance) require `SWITCHBOARD_ADMIN_TOKEN` header when configured; open if not configured |
| **Upload Size** | Live-file uploads bounded by `SWITCHBOARD_MAX_LIVE_FILE_BYTES` before buffering |
| **Expiry Enforcement** | Leases auto-expire after `SWITCHBOARD_LEASE_SECONDS`; agents must heartbeat to extend |
| **Concurrent Checkout** | Task checkout is atomic; only one agent holds a lease at a time |

---

See [architecture.md](../architecture/architecture.md) for detailed API sequences and database schema.
