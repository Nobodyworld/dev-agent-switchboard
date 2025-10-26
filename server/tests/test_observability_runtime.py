from datetime import datetime, timezone

from server.observability import (
    get_runtime_snapshot,
    register_runtime_metadata,
    runtime as runtime_module,
)


def test_runtime_snapshot_includes_environment_metadata(monkeypatch):
    monkeypatch.setenv("SWITCHBOARD_ENVIRONMENT", "production")
    monkeypatch.setenv("SWITCHBOARD_COMMIT_SHA", "abc123")
    monkeypatch.setattr(runtime_module, "_EXTRA_METADATA", {})
    anchor = datetime(2024, 1, 1, tzinfo=timezone.utc)
    monkeypatch.setattr(runtime_module, "_STARTED_AT", anchor, raising=False)
    register_runtime_metadata(region="us-east-1")
    snapshot = get_runtime_snapshot(version="1.2.3")

    assert snapshot.version == "1.2.3"
    assert snapshot.environment == "production"
    assert snapshot.commit_sha == "abc123"
    assert snapshot.started_at == anchor
    assert snapshot.started_at.tzinfo is timezone.utc
    assert snapshot.uptime_seconds >= 0
    assert snapshot.metadata == {"region": "us-east-1"}

    payload = snapshot.model_dump()
    assert payload["started_at"] == anchor.isoformat()
    assert payload["uptime_seconds"] >= 0
    assert payload["pid"] == snapshot.pid
    assert payload["version"] == "1.2.3"
    assert payload["environment"] == "production"
    assert payload["commit_sha"] == "abc123"
    assert payload["metadata"] == {"region": "us-east-1"}
