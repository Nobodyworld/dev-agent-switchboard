# Switchboard API Guide

This document is a human-readable snapshot of the FastAPI application's OpenAPI definition. It summarizes the endpoints, data models, and example interactions available in the `server/app.py` application. The canonical machine-readable schema is still available from the running service at `/openapi.json`.

## Conventions

- **Base URL:** `http://<host>` (replace `<host>` with the actual server address).
- **Content Types:** JSON unless otherwise specified. Binary uploads use the raw request body.
- **Authentication:** None; callers are expected to identify themselves via the `agent_id` query parameter where required.
- **Validation Errors:** FastAPI returns HTTP 422 with a body that matches the `HTTPValidationError` schema.

## Data Models

| Model | Description |
| ----- | ----------- |
| `AgentIn` | Payload used to register an agent. |
| `TaskIn` | Payload for creating tasks. |
| `TaskOut` | Task representation returned by most task endpoints. |
| `CheckoutOut` | Response for task checkout attempts. |
| `PlanOut` | Snapshot of the current task plan, including all tasks. |
| `CompleteIn` | Payload for submitting completion notes. |

### `AgentIn`

```json
{
  "agent_name": "codex-42"
}
```

| Field | Type | Description |
| ----- | ---- | ----------- |
| `agent_name` | string | Human-readable or unique agent identifier. |

### `TaskIn`

```json
{
  "title": "Write docs",
  "description": "Draft endpoint guide",
  "depends_on": [1, 2]
}
```

| Field | Type | Description |
| ----- | ---- | ----------- |
| `title` | string | Task title (required). |
| `description` | string | Optional description (defaults to empty string). |
| `depends_on` | array&lt;int&gt; | Task IDs that must be completed first (defaults to empty array). |

### `TaskOut`

```json
{
  "id": 3,
  "title": "Write docs",
  "description": "Draft endpoint guide",
  "status": "pending",
  "depends_on": [1, 2]
}
```

| Field | Type | Description |
| ----- | ---- | ----------- |
| `id` | integer | Unique task ID. |
| `title` | string | Task title. |
| `description` | string | Task description. |
| `status` | string | Current status (`pending`, `in_progress`, or `completed`). |
| `depends_on` | array&lt;int&gt; | IDs of prerequisite tasks. |

### `CheckoutOut`

```json
{
  "task": {
    "id": 3,
    "title": "Write docs",
    "description": "Draft endpoint guide",
    "status": "in_progress",
    "depends_on": [1, 2]
  },
  "reason": null
}
```

If no task is available, `task` is `null` and `reason` is set to `"no_available_tasks"`.

### `PlanOut`

```json
{
  "version": 1700000000,
  "updated_at": "2024-05-01T12:34:56Z",
  "tasks": [
    {
      "id": 1,
      "title": "Create skeleton",
      "description": "Bootstrap project",
      "status": "completed",
      "depends_on": []
    }
  ]
}
```

| Field | Type | Description |
| ----- | ---- | ----------- |
| `version` | integer | Monotonic counter that increases whenever tasks or live files change. |
| `updated_at` | string (RFC3339 timestamp) | Last time the plan version changed. Use this to confirm data freshness. |
| `tasks` | array&lt;TaskOut&gt; | All tasks in the plan. |

### `CompleteIn`

```json
{
  "notes": "Document written and reviewed"
}
```

| Field | Type | Description |
| ----- | ---- | ----------- |
| `notes` | string | Completion notes (defaults to empty string). |

## Plan Version Semantics

Clients rely on the `PlanOut.version` field to detect when the plan has changed. The server now persists this value in a dedicat
ed `plan_versions` table that stores a single monotonic counter. The counter starts at `0` and increments within the same transa
ction whenever:

- Tasks are created, updated (for example via checkout, completion, or abandonment), or deleted.
- Live files are uploaded via `PUT /api/files/{path}`.

Because the counter lives in its own table and is only incremented, each change produces a strictly increasing version number.
This guarantees that clients observing plan updates over REST or WebSocket can safely compare version numbers to determine whet
her they have the latest state.

### `HTTPValidationError`

Example:

```json
{
  "detail": [
    {
      "loc": ["body", "agent_name"],
      "msg": "Field required",
      "type": "missing"
    }
  ]
}
```

## REST Endpoints

### `GET /`

Render the HTML dashboard for the current task board.

- **Response:** `200 OK` with `text/html` body containing the rendered dashboard.

### `POST /api/agents`

Register an agent if it does not already exist.

- **Request Body:** `AgentIn`.
- **Response 200 Example:**

```json
{
  "ok": true,
  "agent_id": "codex-42"
}
```

### `GET /api/tasks`

List tasks, optionally filtered by status.

- **Query Parameters:**
  - `status` *(optional string)* — filter by exact status.
- **Response 200 Example:**

```json
[
  {
    "id": 1,
    "title": "Create skeleton",
    "description": "Bootstrap project",
    "status": "completed",
    "depends_on": []
  },
  {
    "id": 2,
    "title": "Write docs",
    "description": "Draft endpoint guide",
    "status": "pending",
    "depends_on": [1]
  }
]
```

### `POST /api/tasks`

Create a new task.

- **Request Body:** `TaskIn`.
- **Response 200 Example:**

```json
{
  "id": 3,
  "title": "Write docs",
  "description": "Draft endpoint guide",
  "status": "pending",
  "depends_on": [1]
}
```

### `DELETE /api/tasks/{task_id}`

Delete a task, remove any dependencies pointing to or from it, and clear related leases. Dependent tasks automatically lose the deleted prerequisite and remain pending until reconfigured.

- **Path Parameters:** `task_id` *(integer)*.
- **Response 200 Example:**

```json
{
  "ok": true
}
```

### `POST /api/tasks/checkout`

Lease the next available task for an agent.

- **Query Parameters:** `agent_id` *(string, required)*.
- **Response 200 Examples:**
  - Success:

    ```json
    {
      "task": {
        "id": 2,
        "title": "Write docs",
        "description": "Draft endpoint guide",
        "status": "in_progress",
        "depends_on": [1]
      },
      "reason": null
    }
    ```

  - No task available:

    ```json
    {
      "task": null,
      "reason": "no_available_tasks"
    }
    ```

### `POST /api/tasks/{task_id}/heartbeat`

Extend the lease for an in-progress task.

- **Path Parameters:** `task_id` *(integer)*.
- **Query Parameters:** `agent_id` *(string, required)*.
- **Response 200 Example:**

```json
{
  "ok": true
}
```

### `POST /api/tasks/{task_id}/complete`

Mark a task as completed and release its lease.

- **Path Parameters:** `task_id` *(integer)*.
- **Query Parameters:** `agent_id` *(string, required)*.
- **Request Body:** `CompleteIn`.
- **Response 200 Example:**

```json
{
  "ok": true,
  "notes": "Document written and reviewed"
}
```

### `POST /api/tasks/{task_id}/abandon`

Return a task to the pending state and release its lease.

- **Path Parameters:** `task_id` *(integer)*.
- **Query Parameters:** `agent_id` *(string, required)*.
- **Response 200 Example:**

```json
{
  "ok": true
}
```

### `GET /api/plan`

Retrieve the full task plan, including the current version counter and last-updated timestamp.

- **Response 200 Example:** `PlanOut` payload (see above).

### `PUT /api/files/{path}`

Upload or update a live artifact tracked by Switchboard.

- **Path Parameters:** `path` *(string, accepts nested paths)*.
- **Request Body:** Raw file content (binary or text).
- **Response 200 Example:**

```json
{
  "ok": true,
  "sha256": "9d5b8a...",
  "size": 128,
  "url": "/live/docs/plan.md"
}
```

### `GET /live/{path}`

Download a previously uploaded artifact.

- **Path Parameters:** `path` *(string, accepts nested paths)*.
- **Success Response:** File contents with the appropriate content type.
- **404 Response Example:**

```json
{
  "error": "not_found"
}
```

### `GET /health`

Simple health probe.

- **Response:** Plain text `OK`.

## WebSocket Endpoint

### `GET ws://<host>/ws/plan`

Subscribe to plan updates. The server immediately sends a hello message and echoes `{"type": "pong"}` responses for received messages. Clients should keep the connection alive to receive future plan version notifications.

Example exchange:

```text
<- {"type":"hello","msg":"connected"}
-> "ping"
<- {"type":"pong"}
```

## Error Handling

FastAPI validation errors conform to the `HTTPValidationError` schema. For example, omitting the `agent_id` query parameter when required yields:

```json
{
  "detail": [
    {
      "type": "missing",
      "loc": ["query", "agent_id"],
      "msg": "Field required"
    }
  ]
}
```

## Keeping This Document in Sync

When the FastAPI application changes, regenerate or review `/openapi.json` from the running service and update the corresponding sections here so that field names, parameter lists, and example payloads remain accurate.
