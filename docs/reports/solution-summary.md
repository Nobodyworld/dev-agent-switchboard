# Solution Summary: Update plan endpoints to pass TaskService to _serialize_plan

## Issue Reference
- **Issue:** Update plan endpoints to pass TaskService to _serialize_plan
- **Related PR:** #73 - Optimize task service data access and tests
- **PR Commit:** `3d6d237d6d99247cbe3705d2e2bce81d0f01debf`
- **Priority:** P1 (High) - Both endpoints completely broken

## Problem Description

PR #73 introduced a layered architecture with `TaskService` and updated `_serialize_plan()` to expect a `TaskService` parameter instead of `AsyncSession`. However, two call sites were not updated:

1. **`/api/plan` endpoint** (line ~787): Passes `AsyncSession` to `_serialize_plan()`
2. **`/ws/plan` WebSocket** (line ~800): Passes `AsyncSession` to `_serialize_plan()`

### Runtime Error
```python
AttributeError: 'AsyncSession' object has no attribute 'list_tasks'
```

Both APIs fail before returning any data.

## Solution Overview

### Fix #1: `/api/plan` endpoint
**Change the dependency injection:**
```python
# Before:
async def get_plan(session: AsyncSession = Depends(get_session)):
    plan_dict = await _serialize_plan(session)  # ❌


# After:
async def get_plan(service: TaskService = Depends(get_task_service)):
    plan_dict = await _serialize_plan(service)  # ✓
```

### Fix #2: `/ws/plan` WebSocket
**Create TaskService from session:**
```python
# Before:
async with AsyncSessionLocal() as session:
    plan_payload = await _serialize_plan(session)  # ❌

# After:
async with AsyncSessionLocal() as session:
    service = build_task_service(session)  # ✓
    plan_payload = await _serialize_plan(service)  # ✓
```

## Solution Files in This Branch

| File | Purpose |
|------|---------|
| **README_FIX.md** | Master guide with complete usage instructions |
| **FIX_PLAN_ENDPOINTS.md** | Detailed technical documentation |
| **PLAN_ENDPOINTS_FIX.patch** | Unified diff patch (ready to apply) |
| **FIXED_ENDPOINTS_REFERENCE.py** | Reference implementation with annotations |
| **test_plan_endpoint_fixes.py** | Test suite to verify fixes |
| **demonstrate_fix.py** | Runnable demonstration script |
| **SOLUTION_SUMMARY.md** | This file |

## Quick Start

### Option 1: Run the Demonstration
```bash
python3 demonstrate_fix.py
```
Shows the problem and solution in action.

### Option 2: Apply the Patch
```bash
git checkout codex/align-project-with-clean-architecture-principles
patch -p1 < PLAN_ENDPOINTS_FIX.patch
pytest server/tests/ -v
```

### Option 3: Manual Fix
Open `server/app.py` in PR #73's branch and make the 2-line changes documented in **README_FIX.md**.

## Verification Steps

After applying the fix:

1. **Test `/api/plan` endpoint:**
   ```bash
   curl http://localhost:8000/api/plan
   ```
   Should return: `{"version": 1, "updated_at": "...", "tasks": [...]}`

2. **Test WebSocket:**
   Connect to `ws://localhost:8000/ws/plan`
   Should receive initial plan snapshot without errors

3. **Run tests:**
   ```bash
   pytest server/tests/test_plan_endpoint_fixes.py -v
   ```

## Impact Assessment

- **Severity:** 🔴 High
- **Affected Endpoints:** 2
  - `GET /api/plan`
  - `WS /ws/plan`
- **User Impact:** Critical - endpoints completely non-functional
- **Fix Complexity:** 🟢 Low - 2 lines of code
- **Risk:** 🟢 Low - Straightforward dependency fix

## Technical Context

### Why This Happens
`_serialize_plan()` internally calls:
```python
tasks = await service.list_tasks()  # TaskService method
snapshot = await service.plan_version_snapshot()  # TaskService method
```

`AsyncSession` doesn't have these methods, hence the `AttributeError`.

### Why TaskService?
PR #73 introduced clean architecture layers:
- **Domain:** Pure business logic
- **Application:** `TaskService` coordinates operations
- **Infrastructure:** `SqlAlchemyTaskRepository` handles persistence

The `TaskService` provides high-level operations like `list_tasks()` that the endpoints need.

## Architecture Alignment

After the fix:
- ✅ All endpoints use `TaskService` for business operations
- ✅ Session management stays at infrastructure layer
- ✅ Consistent dependency injection pattern
- ✅ Clean separation of concerns

## Next Steps

1. **For PR #73 Author:**
   - Apply patch or manual changes
   - Run tests
   - Push updated commit

2. **For Code Reviewers:**
   - Verify fixes in next PR #73 revision
   - Check that tests pass
   - Approve PR when fixed

3. **For Future:**
   - Consider adding linting rule to catch parameter type mismatches
   - Add integration tests for all endpoints using `_serialize_plan()`

## Questions or Issues?

Reference:
- This branch: `copilot/update-plan-endpoints-service`
- Original PR: #73 (`codex/align-project-with-clean-architecture-principles`)
- Files in this branch for complete documentation

---

**Last Updated:** 2025-10-24
**Status:** Solution documented and ready to apply
**Blockers:** None - all necessary information provided
