"""Application lifespan management for Switchboard."""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from sqlalchemy import inspect as sa_inspect, text

from server.db import AsyncSessionLocal, Base, engine
from server.execution.registry import iter_trusted_manifests
from server.execution.repository import ExecutionRepository
from server.file_store import ensure_root
from server.settings import get_settings_bundle


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:  # noqa: PLR0915
    """Create the database schema and storage roots on application startup."""

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

        def ensure_completed_notes_column(sync_conn) -> None:
            inspector = sa_inspect(sync_conn)
            columns = {column["name"] for column in inspector.get_columns("tasks")}
            if "completed_notes" not in columns:
                # TODO(P2, 2d) - Move this schema migration into a formal Alembic
                # revision to avoid runtime DDL.
                sync_conn.execute(
                    text("ALTER TABLE tasks ADD COLUMN completed_notes TEXT")
                )

        await conn.run_sync(ensure_completed_notes_column)

        def ensure_github_publication_columns(sync_conn) -> None:
            inspector = sa_inspect(sync_conn)
            if "github_validation_requests" not in inspector.get_table_names():
                return
            columns = {
                column["name"]
                for column in inspector.get_columns("github_validation_requests")
            }
            additions = {
                "github_actor_id": "BIGINT",
                "github_actor_node_id": "VARCHAR(128)",
                # Bandit 1.9.4 mistakes this SQL type metadata for a password.
                "publication_claim_token": "VARCHAR(64)",  # nosec B105
                "publication_claimed_at": "DATETIME",
                "publication_claim_expires_at": "DATETIME",
            }
            for name, sql_type in additions.items():
                if name not in columns:
                    # TODO(P2, 2d) - Move compatibility DDL into a formal
                    # migration once startup applies Alembic revisions.
                    sync_conn.execute(
                        text(
                            "ALTER TABLE github_validation_requests "
                            f"ADD COLUMN {name} {sql_type}"
                        )
                    )

        await conn.run_sync(ensure_github_publication_columns)

        def ensure_execution_reuse_columns(sync_conn) -> None:
            inspector = sa_inspect(sync_conn)
            table_names = set(inspector.get_table_names())
            if "execution_work_orders" in table_names:
                work_order_columns = {
                    column["name"]
                    for column in inspector.get_columns("execution_work_orders")
                }
                work_order_additions = {
                    "reuse_policy": ("VARCHAR(32) NOT NULL DEFAULT 'never'"),
                    "execution_policy_hash": (
                        "VARCHAR(64) NOT NULL DEFAULT "
                        "'0000000000000000000000000000000000000000000000000000000000000000'"
                    ),
                }
                for name, sql_type in work_order_additions.items():
                    if name not in work_order_columns:
                        sync_conn.execute(
                            text(
                                "ALTER TABLE execution_work_orders "
                                f"ADD COLUMN {name} {sql_type}"
                            )
                        )
            if "execution_runs" in table_names:
                run_columns = {
                    column["name"] for column in inspector.get_columns("execution_runs")
                }
                run_additions = {
                    "reuse_identity": "JSON",
                    "reuse_identity_hash": "VARCHAR(64)",
                    "reused_from_run_id": "INTEGER",
                    "source_evidence_fingerprint": "VARCHAR(64)",
                    "reuse_decision": ("VARCHAR(32) NOT NULL DEFAULT 'not_requested'"),
                    "reuse_reason": "VARCHAR(64)",
                    "reuse_candidate_metadata": "JSON",
                    "evidence_retention_expires_at": "DATETIME",
                }
                for name, sql_type in run_additions.items():
                    if name not in run_columns:
                        sync_conn.execute(
                            text(
                                "ALTER TABLE execution_runs "
                                f"ADD COLUMN {name} {sql_type}"
                            )
                        )
                sync_conn.execute(
                    text(
                        "CREATE INDEX IF NOT EXISTS "
                        "ix_execution_run_exact_reuse_candidate "
                        "ON execution_runs "
                        "(reuse_identity_hash, worker_id, status)"
                    )
                )
                sync_conn.execute(
                    text(
                        "CREATE INDEX IF NOT EXISTS "
                        "ix_execution_runs_reused_from_run_id "
                        "ON execution_runs (reused_from_run_id)"
                    )
                )
                sync_conn.execute(
                    text(
                        "CREATE INDEX IF NOT EXISTS "
                        "ix_execution_runs_evidence_retention_expires_at "
                        "ON execution_runs (evidence_retention_expires_at)"
                    )
                )

        await conn.run_sync(ensure_execution_reuse_columns)

        def ensure_execution_routing_schema(sync_conn) -> None:  # noqa: PLR0912
            inspector = sa_inspect(sync_conn)
            table_names = set(inspector.get_table_names())
            if "execution_workers" in table_names:
                worker_columns = {
                    column["name"]
                    for column in inspector.get_columns("execution_workers")
                }
                if "last_checkout_poll_at" not in worker_columns:
                    sync_conn.execute(
                        text(
                            "ALTER TABLE execution_workers "
                            "ADD COLUMN last_checkout_poll_at DATETIME"
                        )
                    )
                sync_conn.execute(
                    text(
                        "CREATE INDEX IF NOT EXISTS "
                        "ix_execution_workers_last_checkout_poll_at "
                        "ON execution_workers (last_checkout_poll_at)"
                    )
                )

            if "execution_work_orders" in table_names:
                columns = {
                    column["name"]
                    for column in inspector.get_columns("execution_work_orders")
                }
                additions = {
                    "routing_policy": (
                        "VARCHAR(32) NOT NULL DEFAULT 'first_available'"
                    ),
                    "maximum_cost_units": "INTEGER",
                    "required_quota_units": "INTEGER NOT NULL DEFAULT 0",
                    "route_schema_version": "INTEGER",
                    "route_selected_worker_id": "VARCHAR(128)",
                    "route_profile_revision": "INTEGER",
                    "route_estimated_cost_units": "INTEGER",
                    "route_reserved_quota_units": "INTEGER NOT NULL DEFAULT 0",
                    "route_quota_state": "VARCHAR(32)",
                    "route_eligible_candidate_count": "INTEGER",
                    "route_explicit_pin_applied": "BOOLEAN NOT NULL DEFAULT 0",
                    "route_reason": "VARCHAR(64)",
                    "route_decided_at": "DATETIME",
                }
                for name, sql_type in additions.items():
                    if name not in columns:
                        sync_conn.execute(
                            text(
                                "ALTER TABLE execution_work_orders "
                                f"ADD COLUMN {name} {sql_type}"
                            )
                        )

            if "execution_runs" in table_names:
                columns = {
                    column["name"] for column in inspector.get_columns("execution_runs")
                }
                additions = {
                    "route_schema_version": "INTEGER NOT NULL DEFAULT 1",
                    "routing_policy": (
                        "VARCHAR(32) NOT NULL DEFAULT 'first_available'"
                    ),
                    "route_profile_revision": "INTEGER",
                    "route_estimated_cost_units": "INTEGER",
                    "route_required_quota_units": "INTEGER NOT NULL DEFAULT 0",
                    "route_reserved_quota_units": "INTEGER NOT NULL DEFAULT 0",
                    "route_quota_state": (
                        "VARCHAR(32) NOT NULL DEFAULT 'not_required'"
                    ),
                    "route_eligible_candidate_count": "INTEGER NOT NULL DEFAULT 1",
                    "route_explicit_pin_applied": "BOOLEAN NOT NULL DEFAULT 0",
                    "route_reason": ("VARCHAR(64) NOT NULL DEFAULT 'routing_selected'"),
                    "route_decided_at": "DATETIME",
                }
                for name, sql_type in additions.items():
                    if name not in columns:
                        sync_conn.execute(
                            text(
                                "ALTER TABLE execution_runs "
                                f"ADD COLUMN {name} {sql_type}"
                            )
                        )
                if {"assigned_at", "created_at"}.issubset(columns):
                    timestamp_expression = text(
                        "UPDATE execution_runs SET route_decided_at = "
                        "COALESCE(route_decided_at, assigned_at, created_at, "
                        "CURRENT_TIMESTAMP)"
                    )
                elif "assigned_at" in columns:
                    timestamp_expression = text(
                        "UPDATE execution_runs SET route_decided_at = "
                        "COALESCE(route_decided_at, assigned_at, CURRENT_TIMESTAMP)"
                    )
                elif "created_at" in columns:
                    timestamp_expression = text(
                        "UPDATE execution_runs SET route_decided_at = "
                        "COALESCE(route_decided_at, created_at, CURRENT_TIMESTAMP)"
                    )
                else:
                    timestamp_expression = text(
                        "UPDATE execution_runs SET route_decided_at = "
                        "COALESCE(route_decided_at, CURRENT_TIMESTAMP)"
                    )
                sync_conn.execute(timestamp_expression)

            work_order_columns = (
                {
                    column["name"]
                    for column in inspector.get_columns("execution_work_orders")
                }
                if "execution_work_orders" in table_names
                else set()
            )
            run_columns = (
                {column["name"] for column in inspector.get_columns("execution_runs")}
                if "execution_runs" in table_names
                else set()
            )
            if {"id", "assigned_at"}.issubset(work_order_columns) and {
                "work_order_id",
                "worker_id",
                "id",
            }.issubset(run_columns):
                sync_conn.execute(
                    text(
                        "UPDATE execution_work_orders "
                        "SET route_schema_version = COALESCE(route_schema_version, 1), "
                        "route_selected_worker_id = COALESCE("
                        "route_selected_worker_id, (SELECT worker_id FROM "
                        "execution_runs "
                        "WHERE execution_runs.work_order_id = execution_work_orders.id "
                        "ORDER BY execution_runs.id DESC LIMIT 1)), "
                        "route_quota_state = COALESCE(route_quota_state, "
                        "'not_required'), "
                        "route_eligible_candidate_count = COALESCE("
                        "route_eligible_candidate_count, 1), "
                        "route_reason = COALESCE(route_reason, 'routing_selected'), "
                        "route_decided_at = COALESCE(route_decided_at, assigned_at) "
                        "WHERE EXISTS (SELECT 1 FROM execution_runs "
                        "WHERE execution_runs.work_order_id = execution_work_orders.id)"
                    )
                )

        await conn.run_sync(ensure_execution_routing_schema)

    async with AsyncSessionLocal() as session:
        repository = ExecutionRepository(session)
        await repository.ensure_manifests(iter_trusted_manifests())
        await session.commit()

    ensure_root()
    startup_logger = logging.getLogger(__name__)
    settings_bundle = get_settings_bundle()
    rate_settings = settings_bundle.rate_limit
    lease_settings = settings_bundle.lease
    startup_logger.info(
        (
            "Loaded configuration: rate_limit_enabled=%s requests=%s window=%s "
            "lease_seconds=%s"
        ),
        rate_settings.enabled,
        rate_settings.requests,
        rate_settings.window_seconds,
        lease_settings.duration_seconds,
    )
    yield
