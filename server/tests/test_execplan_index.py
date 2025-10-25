import asyncio
import datetime as dt

import sqlalchemy as sa
import yaml
from httpx import ASGITransport, AsyncClient

# TODO(P3, 2d) - Modernize these tests to use pytest-asyncio fixtures instead of
# manual asyncio.run wrappers.
from server.app import app
from server.db import AsyncSessionLocal
from server.models import ExecPlan

HTTP_OK = 200
HTTP_NOT_MODIFIED = 304


def _sample_plan() -> ExecPlan:
    return ExecPlan(
        plan_id="alpha",
        title="Alpha Plan",
        summary="Coordinate alpha release",
        status="active",
        lifecycle_created_at=dt.datetime(2024, 1, 1, 12, 0, 0, tzinfo=dt.timezone.utc),
        lifecycle_updated_at=dt.datetime(2024, 1, 2, 12, 0, 0, tzinfo=dt.timezone.utc),
        lifecycle_target_completion=dt.datetime(
            2024, 2, 1, 0, 0, 0, tzinfo=dt.timezone.utc
        ),
        owners=[{"agent_id": "owner-1", "role": "lead"}],
        tags=["release", "priority:high"],
        scope={
            "repositories": [
                {
                    "name": "switchboard",
                    "path_filters": {"include": ["server/**"], "exclude": []},
                }
            ]
        },
        links={
            "details": {
                "format": "markdown",
                "url": "https://example.com/plans/alpha",
            },
            "api": {"url": "https://example.com/api/execplans/alpha"},
        },
        metrics={"tasks_total": 5, "tasks_completed": 2},
        changelog_token="test-token",  # noqa: S106 - fixture token
        extensions=[{"name": "switchboard:beta", "url": "https://example.com/beta"}],
    )


def test_execplan_index_empty_registry_defaults():
    async def scenario():
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/api/execplans/index")
            assert response.status_code == HTTP_OK
            data = response.json()

            assert data["version"] == 1
            assert data["registry_id"] == "switchboard-default"
            assert data["plans"] == []
            assert "generated_at" in data
            assert data["source"]["url"] == "http://test/api/execplans/index"
            assert data["source"]["etag"] == response.headers["ETag"]
            assert "Last-Modified" in response.headers

    asyncio.run(scenario())


def test_execplan_index_includes_plan_metadata_and_yaml():
    async def scenario():
        async with AsyncSessionLocal() as session:
            session.add(_sample_plan())
            await session.commit()

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            json_response = await client.get("/api/execplans/index")
            assert json_response.status_code == HTTP_OK
            body = json_response.json()
            assert body["plans"], "Expected plan metadata to be returned"
            plan = body["plans"][0]
            assert plan["plan_id"] == "alpha"
            assert plan["links"]["details"]["url"] == "https://example.com/plans/alpha"
            assert body["source"]["etag"] == json_response.headers["ETag"]

            yaml_response = await client.get(
                "/api/execplans/index", headers={"Accept": "application/yaml"}
            )
            assert yaml_response.status_code == HTTP_OK
            assert yaml_response.headers["content-type"].startswith("application/yaml")
            parsed = yaml.safe_load(yaml_response.text)
            assert parsed["plans"][0]["plan_id"] == "alpha"

            cached = await client.get(
                "/api/execplans/index",
                headers={"If-None-Match": json_response.headers["ETag"]},
            )
            assert cached.status_code == HTTP_NOT_MODIFIED
            assert cached.headers["ETag"] == json_response.headers["ETag"]

    asyncio.run(scenario())


def test_execplan_index_etag_updates_on_mutation():
    async def scenario():
        async with AsyncSessionLocal() as session:
            plan = _sample_plan()
            session.add(plan)
            await session.commit()

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            first = await client.get("/api/execplans/index")
            assert first.status_code == HTTP_OK
            first_tag = first.headers["ETag"]

        async with AsyncSessionLocal() as session:
            plan = (await session.execute(
                sa.select(ExecPlan).where(ExecPlan.plan_id == "alpha")
            )).scalar_one()
            plan.summary = "Updated summary"
            await session.commit()

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            second = await client.get("/api/execplans/index")
            assert second.status_code == HTTP_OK
            assert second.headers["ETag"] != first_tag

    asyncio.run(scenario())
