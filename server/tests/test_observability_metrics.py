import pytest

from server.domain import TaskAnalytics
from server.observability import metrics
from server.observability.metrics import (
    describe_task_metrics,
    record_task_analytics_metrics,
)


@pytest.fixture(autouse=True)
def reset_metrics_state():
    metrics._reset_for_testing()
    yield
    metrics._reset_for_testing()


@pytest.mark.skipif(metrics.Gauge is None, reason="prometheus_client not installed")
def test_record_task_analytics_metrics_updates_gauges(monkeypatch):
    monkeypatch.setenv("SWITCHBOARD_ENABLE_METRICS", "1")

    analytics = TaskAnalytics(
        total_tasks=5,
        pending_tasks=2,
        in_progress_tasks=1,
        completed_tasks=2,
        ready_tasks=3,
        blocked_tasks=2,
        with_dependencies=4,
        without_dependencies=1,
        dependency_edges=7,
        missing_dependency_tasks=1,
        missing_dependency_edges=2,
        average_dependencies=1.4,
    )

    updated = record_task_analytics_metrics(analytics=analytics)
    assert updated is True

    snapshot = describe_task_metrics()
    assert snapshot["enabled"] is True
    assert snapshot["status"]["total"] == pytest.approx(5.0)
    assert snapshot["status"]["pending"] == pytest.approx(2.0)
    assert snapshot["dependency_edges"] == pytest.approx(7.0)
    assert snapshot["average_dependencies"] == pytest.approx(1.4)
    assert snapshot["missing"]["tasks"] == pytest.approx(1.0)
    assert snapshot["last_updated_at"] is not None


def test_metrics_describe_disabled_when_env_false(monkeypatch):
    monkeypatch.delenv("SWITCHBOARD_ENABLE_METRICS", raising=False)

    analytics = TaskAnalytics(
        total_tasks=1,
        pending_tasks=1,
        in_progress_tasks=0,
        completed_tasks=0,
        ready_tasks=0,
        blocked_tasks=1,
        with_dependencies=0,
        without_dependencies=1,
        dependency_edges=0,
        missing_dependency_tasks=0,
        missing_dependency_edges=0,
        average_dependencies=0.0,
    )

    updated = record_task_analytics_metrics(analytics=analytics)
    if metrics.Gauge is None:
        pytest.skip("prometheus_client not installed")
    assert updated is False
    snapshot = describe_task_metrics()
    assert snapshot["enabled"] is False
    assert snapshot["status"] == {}
    assert snapshot["last_updated_at"] is None
