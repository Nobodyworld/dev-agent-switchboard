# Fix for _serialize_plan Call Sites in PR #73

## Issue
PR #73 (commit `3d6d237d6d99247cbe3705d2e2bce81d0f01debf`) introduced `TaskService` and updated `_serialize_plan` to accept a `TaskService` parameter instead of `AsyncSession`. However, two call sites were not updated:

1. `/api/plan` endpoint (line 787-791)
2. `ws_plan` WebSocket handler (line 800-801)

## Problem
When these endpoints are hit, they will raise:
```
AttributeError: 'AsyncSession' object has no attribute 'list_tasks'
```

## Solution

### Fix #1: Update `/api/plan` endpoint

**Before (line 787-791):**
```python
@app.get("/api/plan", response_model=PlanOut)
async def get_plan(session: AsyncSession = Depends(get_session)):
    """Return the full task plan, including version metadata."""

    plan_dict = await _serialize_plan(session)
    if hasattr(PlanOut, "model_validate"):
        return PlanOut.model_validate(plan_dict)  # type: ignore[attr-defined]
    return PlanOut(**plan_dict)
```

**After:**
```python
@app.get("/api/plan", response_model=PlanOut)
async def get_plan(service: TaskService = Depends(get_task_service)):
    """Return the full task plan, including version metadata."""

    plan_dict = await _serialize_plan(service)
    if hasattr(PlanOut, "model_validate"):
        return PlanOut.model_validate(plan_dict)  # type: ignore[attr-defined]
    return PlanOut(**plan_dict)
```

### Fix #2: Update `ws_plan` WebSocket handler

**Before (line 796-810):**
```python
@app.websocket("/ws/plan")
async def ws_plan(ws: WebSocket):
    """Stream plan updates to connected web clients via WebSocket."""

    await ws.accept()
    await PLAN_BROADCASTER.add(ws)
    try:
        async with AsyncSessionLocal() as session:
            plan_payload = await _serialize_plan(session)
        initial_payload: PlanBroadcastPayload = {
            "type": "plan_snapshot",
            "version": plan_payload.get("version", 0),
            "plan": plan_payload,
        }
        ok = await _send_ws_payload(ws, initial_payload, timeout=PLAN_SEND_TIMEOUT)
        if not ok:
            return
        # ... rest of function
```

**After:**
```python
@app.websocket("/ws/plan")
async def ws_plan(ws: WebSocket):
    """Stream plan updates to connected web clients via WebSocket."""

    await ws.accept()
    await PLAN_BROADCASTER.add(ws)
    try:
        async with AsyncSessionLocal() as session:
            service = build_task_service(session)
            plan_payload = await _serialize_plan(service)
        initial_payload: PlanBroadcastPayload = {
            "type": "plan_snapshot",
            "version": plan_payload.get("version", 0),
            "plan": plan_payload,
        }
        ok = await _send_ws_payload(ws, initial_payload, timeout=PLAN_SEND_TIMEOUT)
        if not ok:
            return
        # ... rest of function
```

## Changes Required
1. In `get_plan`: Change parameter from `session: AsyncSession = Depends(get_session)` to `service: TaskService = Depends(get_task_service)` and pass `service` to `_serialize_plan()`
2. In `ws_plan`: Create a `TaskService` from the session using `service = build_task_service(session)` before calling `_serialize_plan(service)`

## Verification
After applying these fixes:
1. The `/api/plan` endpoint should return the full plan without errors
2. The `/ws/plan` WebSocket should successfully send the initial plan snapshot
3. Both endpoints should properly utilize the `TaskService` layer as intended by the architecture

## Testing
```bash
# Start the server
make run

# Test the /api/plan endpoint
curl http://localhost:8000/api/plan

# Test the WebSocket (requires a WebSocket client)
# Should successfully connect and receive initial plan snapshot
```
