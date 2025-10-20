"""Database configuration helpers for the Switchboard server."""

from __future__ import annotations

import os
from collections.abc import AsyncGenerator, Mapping
from pathlib import Path
from typing import Any

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

class DatabaseConfigurationError(RuntimeError):
    """Raised when environment configuration for the database is invalid."""


TRUE_VALUES = {"1", "true", "t", "yes", "y", "on"}
FALSE_VALUES = {"0", "false", "f", "no", "n", "off"}


def _parse_bool(value: str, *, param: str) -> bool:
    normalized = value.strip().lower()
    if normalized in TRUE_VALUES:
        return True
    if normalized in FALSE_VALUES:
        return False
    raise DatabaseConfigurationError(f"{param} must be a boolean value; got {value!r}.")


def _parse_int(value: str, *, param: str, minimum: int = 0) -> int:
    try:
        parsed = int(value)
    except ValueError as exc:  # pragma: no cover - defensive guard
        raise DatabaseConfigurationError(
            f"{param} must be an integer; got {value!r}."
        ) from exc
    if parsed < minimum:
        raise DatabaseConfigurationError(
            f"{param} must be >= {minimum}; got {parsed}."
        )
    return parsed


def _parse_float(value: str, *, param: str, minimum: float = 0.0) -> float:
    try:
        parsed = float(value)
    except ValueError as exc:  # pragma: no cover - defensive guard
        raise DatabaseConfigurationError(
            f"{param} must be a float; got {value!r}."
        ) from exc
    if parsed < minimum:
        raise DatabaseConfigurationError(
            f"{param} must be >= {minimum}; got {parsed}."
        )
    return parsed


def engine_options_from_env(env: Mapping[str, str] | None = None) -> dict[str, Any]:
    """Return keyword arguments for :func:`create_async_engine` based on environment."""

    source = dict(env or os.environ)
    options: dict[str, Any] = {"echo": False, "future": True}

    if (echo := source.get("DATABASE_ECHO")) is not None:
        options["echo"] = _parse_bool(echo, param="DATABASE_ECHO")

    if (pool_pre_ping := source.get("DATABASE_POOL_PRE_PING")) is not None:
        options["pool_pre_ping"] = _parse_bool(
            pool_pre_ping, param="DATABASE_POOL_PRE_PING"
        )

    if (pool_size := source.get("DATABASE_POOL_SIZE")) is not None:
        options["pool_size"] = _parse_int(
            pool_size, param="DATABASE_POOL_SIZE", minimum=1
        )

    if (max_overflow := source.get("DATABASE_MAX_OVERFLOW")) is not None:
        options["max_overflow"] = _parse_int(
            max_overflow, param="DATABASE_MAX_OVERFLOW", minimum=0
        )

    if (pool_timeout := source.get("DATABASE_POOL_TIMEOUT")) is not None:
        options["pool_timeout"] = _parse_float(
            pool_timeout, param="DATABASE_POOL_TIMEOUT", minimum=0.0
        )

    if (pool_recycle := source.get("DATABASE_POOL_RECYCLE")) is not None:
        options["pool_recycle"] = _parse_int(
            pool_recycle, param="DATABASE_POOL_RECYCLE", minimum=0
        )

    return options


ENGINE_OPTIONS = engine_options_from_env()
engine = create_async_engine(DATABASE_URL, **ENGINE_OPTIONS)

AsyncSessionLocal = sessionmaker(
    bind=engine, class_=AsyncSession, expire_on_commit=False
)

Base = declarative_base()


__all__ = [
    "DATABASE_URL",
    "ENGINE_OPTIONS",
    "FILES_ROOT",
    "STORAGE_ROOT",
    "AsyncSession",
    "AsyncSessionLocal",
    "Base",
    "DatabaseConfigurationError",
    "engine",
    "engine_options_from_env",
    "get_session",
]


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """Yield an :class:`AsyncSession` suitable for FastAPI dependency injection."""

    async with AsyncSessionLocal() as session:
        yield session
