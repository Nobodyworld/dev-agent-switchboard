# Fix for PR #73: Update plan endpoints to pass TaskService to _serialize_plan

## Overview

This directory contains documentation and reference implementation for fixing issue: "Update plan endpoints to pass TaskService to _serialize_plan" which was identified in code review of PR #73.

## Problem Statement

PR #73 (commit `3d6d237d6d99247cbe3705d2e2bce81d0f01debf`) introduced a `TaskService` layer and updated `_serialize_plan()` to accept a `TaskService` parameter instead of `AsyncSession`. However, two call sites were not updated:

1. `/api/plan` endpoint (line ~787)
2. `/ws/plan` WebSocket handler (line ~800)

When these endpoints are hit, they will raise:
```
AttributeError: 'AsyncSession' object has no attribute 'list_tasks'
```

## Solution Files

### 1. FIX_PLAN_ENDPOINTS.md
Comprehensive documentation explaining:
- The issue in detail
- Step-by-step solution
- Before/after code comparisons
- Verification steps

### 2. PLAN_ENDPOINTS_FIX.patch
A unified diff patch file that can be directly applied to PR #73's `server/app.py`:
```bash
cd /path/to/switchboard
git checkout codex/align-project-with-clean-architecture-principles
patch -p1 < PLAN_ENDPOINTS_FIX.patch
```

### 3. FIXED_ENDPOINTS_REFERENCE.py
Reference implementation showing the corrected code with detailed comments explaining each fix.

### 4. test_plan_endpoint_fixes.py  
Test cases that should be added to PR #73 after applying the fixes. These tests verify:
- The `/api/plan` endpoint works correctly
- The `/ws/plan` WebSocket initializes properly
- `_serialize_plan()` is called with `TaskService` correctly

## How to Apply the Fix

### Option A: Manual Application (Recommended)
1. Checkout PR #73's branch:
   ```bash
   git fetch origin codex/align-project-with-clean-architecture-principles
   git checkout codex/align-project-with-clean-architecture-principles
   ```

2. Open `server/app.py` and make these two changes:

   **Change 1** (around line 787):
   ```python
   # Before:
   async def get_plan(session: AsyncSession = Depends(get_session)):
       plan_dict = await _serialize_plan(session)
   
   # After:
   async def get_plan(service: TaskService = Depends(get_task_service)):
       plan_dict = await _serialize_plan(service)
   ```

   **Change 2** (around line 800):
   ```python
   # Before:
   async with AsyncSessionLocal() as session:
       plan_payload = await _serialize_plan(session)
   
   # After:
   async with AsyncSessionLocal() as session:
       service = build_task_service(session)
       plan_payload = await _serialize_plan(service)
   ```

3. Test the changes:
   ```bash
   # Run existing tests
   pytest server/tests/ -v
   
   # Test the specific endpoints
   make run  # In one terminal
   curl http://localhost:8000/api/plan  # In another terminal
   ```

### Option B: Apply Patch File
```bash
git checkout codex/align-project-with-clean-architecture-principles
patch -p1 < PLAN_ENDPOINTS_FIX.patch
```

## Verification

After applying the fixes, verify:

1. **The `/api/plan` endpoint works:**
   ```bash
   curl http://localhost:8000/api/plan
   ```
   Should return a JSON object with `version`, `updated_at`, and `tasks` fields.

2. **The WebSocket initializes:**
   Connect to `ws://localhost:8000/ws/plan` - should receive initial plan snapshot without errors.

3. **Tests pass:**
   ```bash
   pytest server/tests/ -v
   ```

4. **No AttributeError is raised** when accessing these endpoints.

## Why This Fix Is Needed

The `_serialize_plan()` function signature was changed in PR #73:
```python
# New signature:
async def _serialize_plan(service: TaskService) -> dict[str, Any]:
    tasks = await service.list_tasks()  # Calls method on TaskService
    snapshot = await service.plan_version_snapshot()  # Calls method on TaskService
    # ...
```

An `AsyncSession` object doesn't have `list_tasks()` or `plan_version_snapshot()` methods, so passing it causes an `AttributeError`. The fix ensures these endpoints create and pass a `TaskService` instance instead.

## Impact

- **Severity:** High - Both endpoints are completely broken without this fix
- **Affected APIs:** `/api/plan` and `/ws/plan`  
- **User Impact:** Any client trying to fetch the plan or connect to the plan WebSocket will fail
- **Fix Complexity:** Low - Only 2 lines need to be changed

## Related Files in PR #73

- `server/app.py` - Contains the endpoints that need fixing
- `server/application/task_service.py` - Defines the `TaskService` class  
- `server/application/factory.py` - Provides `build_task_service()` helper

## Questions?

This fix documentation was created to help apply the necessary changes to PR #73 before it's merged. If you have questions about the fix or need clarification, please reference:
- The original issue: "Update plan endpoints to pass TaskService to _serialize_plan"
- PR #73: "Optimize task service data access and tests"
- Commit: `3d6d237d6d99247cbe3705d2e2bce81d0f01debf`
