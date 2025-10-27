import json
from argparse import Namespace
from http import HTTPStatus

import pytest
from fastapi.testclient import TestClient
from scripts import dev

from server.app import app
from server.db import AsyncSessionLocal
from server.observability.overview import collect_observability_overview


@pytest.mark.asyncio
async def test_collect_observability_overview_includes_builtin_hooks(files_root):
    _ = files_root
    async with AsyncSessionLocal() as session:
        overview = await collect_observability_overview(
            session, app_version=app.version
        )
    payload = overview.as_payload()

    assert payload["contract"]["api_version"]
    assert any(
        descriptor["name"] == "builtin.plan_latency"
        for descriptor in payload["extensions"]
    )
    latency_entry = next(
        entry
        for entry in payload["observability_hooks"]
        if entry["extension"] == "builtin.plan_latency"
    )
    assert "active" in latency_entry


def test_observability_overview_endpoint(files_root):
    _ = files_root
    client = TestClient(app)
    response = client.get("/api/observability/overview")
    assert response.status_code == HTTPStatus.OK
    payload = response.json()
    assert payload["correlation_hints"]["request_id_header"]
    assert any(
        entry["extension"] == "builtin.plan_latency"
        for entry in payload["observability_hooks"]
    )


def test_cli_observability_overview_writes_json(tmp_path, files_root):
    _ = files_root
    output = tmp_path / "overview.json"
    dev.cmd_observability_overview(Namespace(pretty=True, output=str(output)))
    data = json.loads(output.read_text(encoding="utf-8"))
    assert "telemetry" in data
    assert "extensions" in data
