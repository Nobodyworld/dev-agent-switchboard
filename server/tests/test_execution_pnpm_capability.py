"""Focused pnpm worker-capability and persistence compatibility coverage."""

from __future__ import annotations

from http import HTTPStatus

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy import inspect, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from server.api import lifecycle as lifecycle_module
from server.app import app
from server.execution.capabilities import match_worker_capabilities
from server.execution.entities import WorkerRegistration
from server.execution.enums import NetworkPolicy, WorkerStatus
from server.execution.schemas import WorkerRegistrationIn


def _worker(*, pnpm_version: str | None = None) -> WorkerRegistration:
    return WorkerRegistration(
        worker_id="pnpm-worker",
        display_name="pnpm-worker",
        operating_system="linux",
        architecture="x86_64",
        python_version="3.11.9",
        node_version="v24.12.0",
        docker_available=False,
        browsers=(),
        gpu_available=False,
        unity_available=False,
        desktop_available=False,
        capabilities={"git_available": True},
        max_concurrency=1,
        network_policy_capability=NetworkPolicy.WORKER_RESTRICTED,
        repository_write_capability=False,
        status=WorkerStatus.ONLINE,
        pnpm_version=pnpm_version,
    )


def test_pnpm_exact_requirement_and_node_v_prefix_are_enforced() -> None:
    requirements = {
        "node": {"minimum": "24.12.0"},
        "pnpm": {"exact": "10.18.1"},
    }
    compatible = match_worker_capabilities(
        _worker(pnpm_version="10.18.1"),
        manifest_requirements=requirements,
        requested_requirements={},
        network_policy=NetworkPolicy.WORKER_RESTRICTED,
    )
    assert compatible.eligible is True
    assert compatible.reasons == ()

    for version in (None, "10.18.0", "10.18.2"):
        incompatible = match_worker_capabilities(
            _worker(pnpm_version=version),
            manifest_requirements=requirements,
            requested_requirements={},
            network_policy=NetworkPolicy.WORKER_RESTRICTED,
        )
        assert incompatible.eligible is False
        assert incompatible.reasons == ("pnpm_version_mismatch_or_missing",)


def test_legacy_worker_payload_omits_nullable_pnpm_version() -> None:
    legacy = WorkerRegistrationIn.model_validate(
        {
            "worker_id": "legacy-worker",
            "display_name": "legacy-worker",
            "operating_system": "linux",
            "architecture": "x86_64",
        }
    )

    assert legacy.pnpm_version is None
    assert _worker().pnpm_version is None


def test_worker_registration_normalizes_or_rejects_runtime_probe_output() -> None:
    registration = WorkerRegistrationIn.model_validate(
        {
            "worker_id": "runtime-normalization-worker",
            "display_name": "Runtime normalization worker",
            "operating_system": "linux",
            "architecture": "x86_64",
            "python_version": "3.13.1",
            "node_version": "v24.12.0",
            "pnpm_version": "10.18.1",
        }
    )

    assert registration.node_version == "24.12.0"
    with pytest.raises(ValueError, match="semantic"):
        WorkerRegistrationIn.model_validate(
            {
                "worker_id": "invalid-runtime-worker",
                "display_name": "Invalid runtime worker",
                "operating_system": "linux",
                "architecture": "x86_64",
                "pnpm_version": "secret-shaped-output",
            }
        )


@pytest.mark.asyncio
async def test_worker_registration_exposes_pnpm_version() -> None:
    payload = {
        "worker_id": "api-pnpm-worker",
        "display_name": "API pnpm worker",
        "operating_system": "linux",
        "architecture": "x86_64",
        "python_version": "3.11.9",
        "node_version": "v24.12.0",
        "pnpm_version": "10.18.1",
    }
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        registered = await client.post("/api/execution/workers", json=payload)
        assert registered.status_code == HTTPStatus.OK
        assert registered.json()["pnpm_version"] == "10.18.1"

        legacy = await client.post(
            "/api/execution/workers",
            json={**payload, "worker_id": "api-legacy-worker", "pnpm_version": None},
        )
        assert legacy.status_code == HTTPStatus.OK
        assert legacy.json()["pnpm_version"] is None


@pytest.mark.asyncio
async def test_prior_worker_schema_gains_nullable_pnpm_column_once(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    database = tmp_path / "prior-worker-pnpm.db"
    engine = create_async_engine(f"sqlite+aiosqlite:///{database}")
    factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with engine.begin() as connection:
            await connection.execute(
                text(
                    "CREATE TABLE execution_workers ("
                    "id INTEGER PRIMARY KEY, worker_id VARCHAR(128) NOT NULL)"
                )
            )
            await connection.execute(
                text(
                    "INSERT INTO execution_workers (id, worker_id) "
                    "VALUES (1, 'legacy-worker')"
                )
            )
        monkeypatch.setattr(lifecycle_module, "engine", engine)
        monkeypatch.setattr(lifecycle_module, "AsyncSessionLocal", factory)

        async with lifecycle_module.lifespan(FastAPI()):
            pass
        async with lifecycle_module.lifespan(FastAPI()):
            pass

        async with engine.begin() as connection:
            columns = await connection.run_sync(
                lambda sync_connection: {
                    column["name"]
                    for column in inspect(sync_connection).get_columns(
                        "execution_workers"
                    )
                }
            )
            version = (
                await connection.execute(
                    text("SELECT pnpm_version FROM execution_workers WHERE id = 1")
                )
            ).scalar_one()
        assert "pnpm_version" in columns
        assert version is None
    finally:
        await engine.dispose()
