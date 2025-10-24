#!/usr/bin/env python3
"""
Demonstration script showing why the fix is needed and how it works.

This script doesn't run against the actual codebase, but demonstrates
the conceptual difference between the broken and fixed versions.
"""

from typing import Protocol, Any
from dataclasses import dataclass


# Mock classes to demonstrate the issue
@dataclass
class AsyncSession:
    """Mock AsyncSession (SQLAlchemy)."""
    def execute(self, stmt: Any) -> Any:
        return "query result"


class TaskService:
    """Mock TaskService from PR #73."""
    
    def __init__(self, session: AsyncSession):
        self.session = session
    
    async def list_tasks(self):
        """List all tasks - this method exists on TaskService."""
        return [{"id": 1, "title": "Task 1"}]
    
    async def plan_version_snapshot(self):
        """Get plan version snapshot - this method exists on TaskService."""
        return type('obj', (object,), {'value': 1, 'updated_at': '2025-10-24'})()


# The problematic _serialize_plan function (as changed in PR #73)
async def _serialize_plan(service: TaskService) -> dict[str, Any]:
    """
    This function expects a TaskService parameter.
    
    It calls service.list_tasks() and service.plan_version_snapshot()
    which are methods that exist on TaskService but NOT on AsyncSession.
    """
    tasks = await service.list_tasks()  # ← Requires TaskService
    snapshot = await service.plan_version_snapshot()  # ← Requires TaskService
    
    return {
        "version": snapshot.value,
        "updated_at": snapshot.updated_at,
        "tasks": tasks,
    }


def build_task_service(session: AsyncSession) -> TaskService:
    """Helper to create TaskService from session."""
    return TaskService(session)


# =============================================================================
# DEMONSTRATION: THE BUG
# =============================================================================

async def broken_get_plan_endpoint():
    """
    This is the BROKEN version (before fix).
    It passes AsyncSession to _serialize_plan.
    """
    print("=" * 70)
    print("BROKEN VERSION (Before Fix)")
    print("=" * 70)
    
    session = AsyncSession()
    
    try:
        # This is what the code did before the fix:
        plan_dict = await _serialize_plan(session)  # ❌ WRONG!
        print("✗ This should have failed but didn't in this mock")
    except AttributeError as e:
        print(f"✓ Got expected error: {e}")
        print("  → AsyncSession doesn't have list_tasks() method")
    
    print()


async def broken_ws_plan_handler():
    """
    This is the BROKEN WebSocket version (before fix).
    """
    print("=" * 70)
    print("BROKEN WS VERSION (Before Fix)")
    print("=" * 70)
    
    session = AsyncSession()
    
    try:
        # This is what the WebSocket code did before the fix:
        plan_payload = await _serialize_plan(session)  # ❌ WRONG!
        print("✗ This should have failed but didn't in this mock")
    except AttributeError as e:
        print(f"✓ Got expected error: {e}")
        print("  → AsyncSession doesn't have plan_version_snapshot() method")
    
    print()


# =============================================================================
# DEMONSTRATION: THE FIX
# =============================================================================

async def fixed_get_plan_endpoint():
    """
    This is the FIXED version (after fix).
    It uses TaskService dependency instead of AsyncSession.
    """
    print("=" * 70)
    print("FIXED VERSION (After Fix)")
    print("=" * 70)
    
    # In the real code, this comes from: Depends(get_task_service)
    # Instead of: Depends(get_session)
    service = TaskService(AsyncSession())  # ✓ CORRECT!
    
    try:
        plan_dict = await _serialize_plan(service)  # ✓ CORRECT!
        print(f"✓ Success! Got plan: {plan_dict}")
        print("  → TaskService has list_tasks() and plan_version_snapshot() methods")
    except AttributeError as e:
        print(f"✗ Unexpected error: {e}")
    
    print()


async def fixed_ws_plan_handler():
    """
    This is the FIXED WebSocket version (after fix).
    """
    print("=" * 70)
    print("FIXED WS VERSION (After Fix)")
    print("=" * 70)
    
    session = AsyncSession()
    
    try:
        # Fixed version creates TaskService from session first:
        service = build_task_service(session)  # ✓ CORRECT!
        plan_payload = await _serialize_plan(service)  # ✓ CORRECT!
        print(f"✓ Success! Got plan payload: {plan_payload}")
        print("  → Created TaskService from session, then passed to _serialize_plan")
    except AttributeError as e:
        print(f"✗ Unexpected error: {e}")
    
    print()


# =============================================================================
# SUMMARY
# =============================================================================

def print_summary():
    print("=" * 70)
    print("SUMMARY OF THE FIX")
    print("=" * 70)
    print()
    print("THE PROBLEM:")
    print("  _serialize_plan() was changed to accept TaskService parameter")
    print("  But two endpoints still passed AsyncSession to it")
    print()
    print("THE SYMPTOM:")
    print("  AttributeError: 'AsyncSession' object has no attribute 'list_tasks'")
    print()
    print("THE FIX:")
    print("  1. /api/plan endpoint:")
    print("     Before: async def get_plan(session: AsyncSession = Depends(get_session))")
    print("     After:  async def get_plan(service: TaskService = Depends(get_task_service))")
    print()
    print("  2. /ws/plan WebSocket:")
    print("     Before: plan_payload = await _serialize_plan(session)")
    print("     After:  service = build_task_service(session)")
    print("             plan_payload = await _serialize_plan(service)")
    print()
    print("=" * 70)


# =============================================================================
# MAIN
# =============================================================================

async def main():
    """Run all demonstrations."""
    print("\n")
    print("╔" + "═" * 68 + "╗")
    print("║" + " " * 15 + "PR #73 FIX DEMONSTRATION" + " " * 30 + "║")
    print("╚" + "═" * 68 + "╝")
    print()
    
    await broken_get_plan_endpoint()
    await broken_ws_plan_handler()
    await fixed_get_plan_endpoint()
    await fixed_ws_plan_handler()
    print_summary()


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
