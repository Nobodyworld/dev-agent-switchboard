"""Database configuration helpers for the Switchboard server."""

from __future__ import annotations

import os
from pathlib import Path
from typing import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import declarative_base, sessionmaker

DEFAULT_DATABASE_URL = "sqlite+aiosqlite:///./switchboard.db"

_BASE_DIR = Path(__file__).resolve().parent
_DEFAULT_STORAGE_ROOT = (_BASE_DIR.parent / "storage").resolve()

DATABASE_URL = os.getenv("DATABASE_URL", DEFAULT_DATABASE_URL)
STORAGE_ROOT = (
    Path(os.getenv("STORAGE_ROOT", str(_DEFAULT_STORAGE_ROOT))).expanduser().resolve()
)
_files_root_env = os.getenv("FILES_ROOT")
if _files_root_env:
    FILES_ROOT = Path(_files_root_env).expanduser().resolve()
else:
    FILES_ROOT = (STORAGE_ROOT / "files").resolve()

engine = create_async_engine(DATABASE_URL, echo=False, future=True)

AsyncSessionLocal = sessionmaker(
    bind=engine, class_=AsyncSession, expire_on_commit=False
)

Base = declarative_base()


__all__ = [
    "AsyncSession",
    "AsyncSessionLocal",
    "Base",
    "DATABASE_URL",
    "FILES_ROOT",
    "STORAGE_ROOT",
    "engine",
    "get_session",
]


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """Yield an :class:`AsyncSession` suitable for FastAPI dependency injection."""

    async with AsyncSessionLocal() as session:
        yield session
