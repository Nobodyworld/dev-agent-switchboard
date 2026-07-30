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
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
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
                "publication_claim_token": "VARCHAR(64)",
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
