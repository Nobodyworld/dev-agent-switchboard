"""Startup compatibility tests for additive execution-plane tables."""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from sqlalchemy import inspect, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from server.api import lifecycle as lifecycle_module
from server.execution.repository import ExecutionRepository
from server.models import (
    CommandManifest,
    ExecutionWorkOrder,
    GitHubValidationRequest,
    Task,
)


@pytest.mark.asyncio
async def test_fresh_database_creates_execution_tables_and_seeds_manifest(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    database = tmp_path / "fresh-execution.db"
    engine = create_async_engine(f"sqlite+aiosqlite:///{database}")
    factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        monkeypatch.setattr(lifecycle_module, "engine", engine)
        monkeypatch.setattr(lifecycle_module, "AsyncSessionLocal", factory)
        async with lifecycle_module.lifespan(FastAPI()):
            pass
        async with engine.begin() as connection:
            tables = await connection.run_sync(_table_names)
        assert {
            "execution_command_manifests",
            "execution_work_orders",
            "execution_workers",
            "execution_runs",
            "execution_leases",
            "github_validation_requests",
        }.issubset(tables)

        async with factory() as session:
            repository = ExecutionRepository(session)
            manifest = await repository.get_manifest("validate-switchboard", "1")
            assert manifest is not None
            assert manifest.name == "validate-switchboard"
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_existing_core_database_starts_with_additive_execution_tables(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    database = tmp_path / "existing-core.db"
    engine = create_async_engine(f"sqlite+aiosqlite:///{database}")
    factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with engine.begin() as connection:
            await connection.run_sync(
                lambda sync_connection: Task.__table__.create(sync_connection)
            )
        monkeypatch.setattr(lifecycle_module, "engine", engine)
        monkeypatch.setattr(lifecycle_module, "AsyncSessionLocal", factory)
        async with lifecycle_module.lifespan(FastAPI()):
            pass
        async with engine.begin() as connection:
            tables = await connection.run_sync(_table_names)
        assert "tasks" in tables
        assert "execution_work_orders" in tables
        assert "github_validation_requests" in tables

        async with factory() as session:
            repository = ExecutionRepository(session)
            stored = await repository.get_manifest("validate-switchboard", "1")
            assert stored is not None
            assert stored.digest
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_existing_adapter_table_gains_actor_and_claim_columns(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    database = tmp_path / "existing-adapter.db"
    engine = create_async_engine(f"sqlite+aiosqlite:///{database}")
    factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with engine.begin() as connection:
            await connection.execute(
                text(
                    "CREATE TABLE github_validation_requests "
                    "(id INTEGER PRIMARY KEY)"
                )
            )
        monkeypatch.setattr(lifecycle_module, "engine", engine)
        monkeypatch.setattr(lifecycle_module, "AsyncSessionLocal", factory)

        async with lifecycle_module.lifespan(FastAPI()):
            pass

        async with engine.begin() as connection:
            columns = await connection.run_sync(
                lambda sync_connection: {
                    column["name"]
                    for column in inspect(sync_connection).get_columns(
                        "github_validation_requests"
                    )
                }
            )
        assert {
            "github_actor_id",
            "github_actor_node_id",
            "publication_claim_token",
            "publication_claimed_at",
            "publication_claim_expires_at",
        }.issubset(columns)
    finally:
        await engine.dispose()


def test_execution_models_are_new_tables_not_task_columns() -> None:
    assert "repository_full_name" not in Task.__table__.columns
    assert "commit_sha" not in Task.__table__.columns
    assert "commit_sha" in ExecutionWorkOrder.__table__.columns
    assert "digest" in CommandManifest.__table__.columns
    assert "idempotency_key" in GitHubValidationRequest.__table__.columns
    assert "github_actor_id" in GitHubValidationRequest.__table__.columns
    assert "publication_claim_token" in GitHubValidationRequest.__table__.columns


def _table_names(sync_connection) -> set[str]:
    return set(inspect(sync_connection).get_table_names())
