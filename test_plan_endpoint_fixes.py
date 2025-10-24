"""
Test cases to verify the _serialize_plan endpoint fixes.

These tests should be added to server/tests/ in PR #73 after applying the fixes.
They verify that:
1. The /api/plan endpoint works correctly with TaskService
2. The /ws/plan WebSocket initializes correctly with TaskService
"""

import pytest
from fastapi.testclient import TestClient

# These imports would work in PR #73's codebase:
# from server.app import app
# from server.application import TaskService, build_task_service
# from server.db import AsyncSessionLocal


class TestPlanEndpointFixes:
    """Tests for the corrected plan endpoints."""

    def test_get_plan_returns_valid_plan_structure(self):
        """Verify /api/plan endpoint returns expected structure."""
        # This would work with PR #73's code:
        # client = TestClient(app)
        # response = client.get("/api/plan")
        #
        # assert response.status_code == 200
        # data = response.json()
        # assert "version" in data
        # assert "updated_at" in data
        # assert "tasks" in data
        # assert isinstance(data["tasks"], list)
        pass  # Placeholder for actual test

    def test_get_plan_uses_task_service_not_session(self):
        """Verify /api/plan uses TaskService dependency."""
        # This test would verify that the endpoint signature is correct:
        # from server.app import get_plan
        # import inspect
        #
        # sig = inspect.signature(get_plan)
        # params = list(sig.parameters.values())
        # assert len(params) == 1
        # assert params[0].name == "service"
        # # Check that the annotation is TaskService, not AsyncSession
        # assert "TaskService" in str(params[0].annotation)
        pass  # Placeholder for actual test

    @pytest.mark.asyncio
    async def test_serialize_plan_called_with_task_service(self):
        """Verify _serialize_plan receives TaskService, not AsyncSession."""
        # from server.app import _serialize_plan
        # from server.application import TaskService
        # from server.db import AsyncSessionLocal
        #
        # async with AsyncSessionLocal() as session:
        #     service = build_task_service(session)
        #     # This should work without AttributeError:
        #     result = await _serialize_plan(service)
        #
        #     assert isinstance(result, dict)
        #     assert "version" in result
        #     assert "updated_at" in result
        #     assert "tasks" in result
        pass  # Placeholder for actual test

    @pytest.mark.asyncio
    async def test_ws_plan_initializes_without_error(self):
        """Verify WebSocket /ws/plan can send initial plan snapshot."""
        # from server.app import app
        # from fastapi.testclient import TestClient
        #
        # with TestClient(app) as client:
        #     with client.websocket_connect("/ws/plan") as websocket:
        #         # Should receive initial plan snapshot without error
        #         data = websocket.receive_json()
        #         assert data["type"] == "plan_snapshot"
        #         assert "version" in data
        #         assert "plan" in data
        pass  # Placeholder for actual test


class TestTaskServiceIntegration:
    """Integration tests verifying TaskService is properly used."""

    @pytest.mark.asyncio
    async def test_list_tasks_method_exists_on_service(self):
        """Verify TaskService has list_tasks() method."""
        # from server.application import TaskService, build_task_service
        # from server.db import AsyncSessionLocal
        #
        # async with AsyncSessionLocal() as session:
        #     service = build_task_service(session)
        #     assert hasattr(service, "list_tasks")
        #     tasks = await service.list_tasks()
        #     assert isinstance(tasks, (list, tuple))
        pass  # Placeholder for actual test

    @pytest.mark.asyncio
    async def test_plan_version_snapshot_method_exists_on_service(self):
        """Verify TaskService has plan_version_snapshot() method."""
        # from server.application import TaskService, build_task_service
        # from server.db import AsyncSessionLocal
        #
        # async with AsyncSessionLocal() as session:
        #     service = build_task_service(session)
        #     assert hasattr(service, "plan_version_snapshot")
        #     snapshot = await service.plan_version_snapshot()
        #     assert hasattr(snapshot, "value")
        #     assert hasattr(snapshot, "updated_at")
        pass  # Placeholder for actual test


class TestErrorCasesBeforeFix:
    """Tests demonstrating the error that occurs without the fix."""

    @pytest.mark.skip(reason="Demonstrates the bug - only run before applying fix")
    @pytest.mark.asyncio
    async def test_serialize_plan_with_session_raises_attribute_error(self):
        """Show that passing AsyncSession to _serialize_plan raises AttributeError."""
        # from server.app import _serialize_plan
        # from server.db import AsyncSessionLocal
        #
        # async with AsyncSessionLocal() as session:
        #     # This SHOULD raise: AttributeError: 'AsyncSession' object has no attribute 'list_tasks'
        #     with pytest.raises(AttributeError, match="'AsyncSession' object has no attribute 'list_tasks'"):
        #         await _serialize_plan(session)  # Wrong! Passing session instead of service
        pass  # Placeholder for actual test


# =============================================================================
# HOW TO USE THESE TESTS
# =============================================================================
#
# 1. After applying the fixes to server/app.py in PR #73:
#    - Uncomment the test code
#    - Save this file as server/tests/test_plan_endpoint_fixes.py
#
# 2. Run the tests:
#    pytest server/tests/test_plan_endpoint_fixes.py -v
#
# 3. All tests should pass, verifying:
#    - The endpoints use TaskService correctly
#    - The _serialize_plan function works with TaskService
#    - The WebSocket initializes without errors
#
# 4. The TestErrorCasesBeforeFix class can be used to verify the bug exists
#    before applying the fix (by temporarily uncommenting and running with
#    the unfixed code).
