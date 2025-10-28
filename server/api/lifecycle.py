"""Application lifespan management for Switchboard."""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from sqlalchemy import inspect as sa_inspect, text

from server.db import Base, engine
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
