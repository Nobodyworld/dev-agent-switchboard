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
            "execution_worker_routing_profiles",
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
            await connection.run_sync(Task.__table__.create)
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
async def test_main_manifest_schema_survives_repeated_startup(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    database = tmp_path / "main-manifest-schema.db"
    engine = create_async_engine(f"sqlite+aiosqlite:///{database}")
    factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with engine.begin() as connection:
            await connection.execute(
                text(
                    "CREATE TABLE execution_command_manifests ("
                    "id INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT, "
                    "name VARCHAR(128) NOT NULL, "
                    "version VARCHAR(64) NOT NULL, "
                    "schema_version INTEGER NOT NULL, "
                    "digest VARCHAR(64) NOT NULL UNIQUE, "
                    "description TEXT NOT NULL, "
                    "trusted_registry_source VARCHAR(512) NOT NULL, "
                    "required_capabilities JSON NOT NULL, "
                    "fixed_step_metadata JSON NOT NULL, "
                    "environment_policy JSON NOT NULL, "
                    "network_policy VARCHAR(32) NOT NULL, "
                    "repository_write_policy VARCHAR(32) NOT NULL, "
                    "timeout_seconds INTEGER NOT NULL, "
                    "artifact_declarations JSON NOT NULL, "
                    "created_at DATETIME NOT NULL, "
                    "CONSTRAINT uq_execution_manifest_identity "
                    "UNIQUE (name, version), "
                    "CONSTRAINT ck_execution_manifest_read_only "
                    "CHECK (repository_write_policy = 'read_only')"
                    ")"
                )
            )
            await connection.execute(
                text(
                    "CREATE INDEX ix_execution_command_manifests_name "
                    "ON execution_command_manifests (name)"
                )
            )

        monkeypatch.setattr(lifecycle_module, "engine", engine)
        monkeypatch.setattr(lifecycle_module, "AsyncSessionLocal", factory)

        async with lifecycle_module.lifespan(FastAPI()):
            pass
        async with factory() as session:
            repository = ExecutionRepository(session)
            first = await repository.get_manifest("validate-switchboard", "1")
            first_listing = await repository.list_manifests()
        assert first is not None
        assert first in first_listing
        assert (
            sum(
                manifest.name == first.name and manifest.version == first.version
                for manifest in first_listing
            )
            == 1
        )

        async with lifecycle_module.lifespan(FastAPI()):
            pass
        async with factory() as session:
            repository = ExecutionRepository(session)
            second = await repository.get_manifest("validate-switchboard", "1")
            second_listing = await repository.list_manifests()
        assert second is not None
        assert second.id == first.id
        assert second.digest == first.digest
        assert (
            sum(
                manifest.name == second.name and manifest.version == second.version
                for manifest in second_listing
            )
            == 1
        )

        async with engine.begin() as connection:
            (
                tables,
                manifest_columns,
                worker_columns,
                order_columns,
                run_columns,
            ) = await connection.run_sync(_routing_schema)
        assert "updated_at" not in manifest_columns
        assert "execution_worker_routing_profiles" in tables
        assert "last_checkout_poll_at" in worker_columns
        assert {"routing_policy", "route_selected_worker_id"}.issubset(order_columns)
        assert {"routing_policy", "route_profile_revision"}.issubset(run_columns)
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
                text("CREATE TABLE github_validation_requests (id INTEGER PRIMARY KEY)")
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


@pytest.mark.asyncio
async def test_existing_execution_tables_gain_reuse_columns_and_indexes(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    database = tmp_path / "existing-execution.db"
    engine = create_async_engine(f"sqlite+aiosqlite:///{database}")
    factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with engine.begin() as connection:
            await connection.execute(
                text("CREATE TABLE execution_work_orders (id INTEGER PRIMARY KEY)")
            )
            await connection.execute(
                text(
                    "CREATE TABLE execution_runs ("
                    "id INTEGER PRIMARY KEY, worker_id VARCHAR(128), "
                    "status VARCHAR(32))"
                )
            )
        monkeypatch.setattr(lifecycle_module, "engine", engine)
        monkeypatch.setattr(lifecycle_module, "AsyncSessionLocal", factory)

        async with lifecycle_module.lifespan(FastAPI()):
            pass

        async with engine.begin() as connection:
            work_order_columns, run_columns, indexes = await connection.run_sync(
                _reuse_schema
            )
        assert {"reuse_policy", "execution_policy_hash"}.issubset(work_order_columns)
        assert {
            "reuse_identity",
            "reuse_identity_hash",
            "reused_from_run_id",
            "source_evidence_fingerprint",
            "reuse_decision",
            "reuse_reason",
            "reuse_candidate_metadata",
            "evidence_retention_expires_at",
        }.issubset(run_columns)
        assert {
            "ix_execution_run_exact_reuse_candidate",
            "ix_execution_runs_reused_from_run_id",
            "ix_execution_runs_evidence_retention_expires_at",
        }.issubset(indexes)
        assert {
            "routing_policy",
            "maximum_cost_units",
            "required_quota_units",
            "route_schema_version",
            "route_selected_worker_id",
            "route_profile_revision",
            "route_estimated_cost_units",
            "route_reserved_quota_units",
            "route_quota_state",
            "route_eligible_candidate_count",
            "route_explicit_pin_applied",
            "route_reason",
            "route_decided_at",
        }.issubset(work_order_columns)
        assert {
            "route_schema_version",
            "routing_policy",
            "route_profile_revision",
            "route_estimated_cost_units",
            "route_required_quota_units",
            "route_reserved_quota_units",
            "route_quota_state",
            "route_eligible_candidate_count",
            "route_explicit_pin_applied",
            "route_reason",
            "route_decided_at",
        }.issubset(run_columns)
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_prior_worker_schema_gains_switchboard_only_repository_list_once(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    database = tmp_path / "prior-worker-repositories.db"
    engine = create_async_engine(f"sqlite+aiosqlite:///{database}")
    factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with engine.begin() as connection:
            await connection.execute(
                text(
                    "CREATE TABLE execution_workers ("
                    "id INTEGER PRIMARY KEY, worker_id VARCHAR(128) NOT NULL, "
                    "last_checkout_poll_at DATETIME)"
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
        async with engine.begin() as connection:
            first = (
                await connection.execute(
                    text(
                        "SELECT repository_full_names FROM execution_workers "
                        "WHERE id = 1"
                    )
                )
            ).scalar_one()
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
            second = (
                await connection.execute(
                    text(
                        "SELECT repository_full_names FROM execution_workers "
                        "WHERE id = 1"
                    )
                )
            ).scalar_one()
        assert "repository_full_names" in columns
        assert first == '["Nobodyworld/dev-agent-switchboard"]'
        assert second == first
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


def _reuse_schema(sync_connection) -> tuple[set[str], set[str], set[str]]:
    inspector = inspect(sync_connection)
    return (
        {column["name"] for column in inspector.get_columns("execution_work_orders")},
        {column["name"] for column in inspector.get_columns("execution_runs")},
        {index["name"] for index in inspector.get_indexes("execution_runs")},
    )


def _routing_schema(
    sync_connection,
) -> tuple[set[str], set[str], set[str], set[str], set[str]]:
    inspector = inspect(sync_connection)
    tables = set(inspector.get_table_names())
    return (
        tables,
        {
            column["name"]
            for column in inspector.get_columns("execution_command_manifests")
        },
        {column["name"] for column in inspector.get_columns("execution_workers")},
        {column["name"] for column in inspector.get_columns("execution_work_orders")},
        {column["name"] for column in inspector.get_columns("execution_runs")},
    )
