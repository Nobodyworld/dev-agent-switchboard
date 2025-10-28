from dataclasses import dataclass
from types import SimpleNamespace

from server.extensions.contracts import PlanBroadcastContext, TaskHookContext

DIRECT_TASK_ID = 21
TASK_FROM_AGENT_ID = 34
TASK_FROM_RESULT_ID = 55
TASK_FROM_RESULT_TASK_ID = 89

PLAN_VERSION = 3
READY_TASKS = 5
BLOCKED_TASKS = 2
MAPPING_READY_TASKS = 1
MAPPING_BLOCKED_TASKS = 0


def test_task_hook_context_agent_resolution_paths():
    direct = TaskHookContext(event="on_complete", payload={"agent_id": "alpha"})
    assert direct.agent_id == "alpha"

    from_agent = TaskHookContext(
        event="on_checkout",
        payload={"agent": SimpleNamespace(agent_id="bravo")},
    )
    assert from_agent.agent_id == "bravo"

    from_result = TaskHookContext(
        event="on_complete",
        payload={"result": SimpleNamespace(agent_id="charlie")},
    )
    assert from_result.agent_id == "charlie"


def test_task_hook_context_task_resolution_paths():
    direct = TaskHookContext(event="on_complete", payload={"task_id": DIRECT_TASK_ID})
    assert direct.task_id == DIRECT_TASK_ID

    from_task = TaskHookContext(
        event="on_update",
        payload={"task": SimpleNamespace(id=TASK_FROM_AGENT_ID)},
    )
    assert from_task.task_id == TASK_FROM_AGENT_ID

    from_result_id = TaskHookContext(
        event="on_complete",
        payload={"result": SimpleNamespace(task_id=TASK_FROM_RESULT_ID)},
    )
    assert from_result_id.task_id == TASK_FROM_RESULT_ID

    from_result_task = TaskHookContext(
        event="on_complete",
        payload={
            "result": SimpleNamespace(
                task=SimpleNamespace(id=TASK_FROM_RESULT_TASK_ID)
            ),
        },
    )
    assert from_result_task.task_id == TASK_FROM_RESULT_TASK_ID


@dataclass(slots=True)
class _Analytics:
    ready_tasks: int
    blocked_tasks: int


def test_plan_broadcast_context_analytics_behaviour():
    analytics = _Analytics(ready_tasks=READY_TASKS, blocked_tasks=BLOCKED_TASKS)
    context = PlanBroadcastContext(
        version=PLAN_VERSION,
        plan={"tasks": []},
        delta={"added": []},
        analytics=analytics,
    )
    payload = context.as_payload()
    assert payload["version"] == PLAN_VERSION
    assert payload["plan_keys"] == ["tasks"]
    assert payload["delta_keys"] == ["added"]
    assert payload["analytics"] == {
        "ready_tasks": READY_TASKS,
        "blocked_tasks": BLOCKED_TASKS,
    }
    assert context.ready_tasks == READY_TASKS
    assert context.blocked_tasks == BLOCKED_TASKS

    mapping_context = PlanBroadcastContext(
        version=None,
        plan=None,
        delta=None,
        analytics={
            "ready_tasks": MAPPING_READY_TASKS,
            "blocked_tasks": MAPPING_BLOCKED_TASKS,
        },
    )
    assert mapping_context.analytics_as_dict() == {
        "ready_tasks": MAPPING_READY_TASKS,
        "blocked_tasks": MAPPING_BLOCKED_TASKS,
    }
    assert mapping_context.as_payload()["analytics"] == {
        "ready_tasks": MAPPING_READY_TASKS,
        "blocked_tasks": MAPPING_BLOCKED_TASKS,
    }
