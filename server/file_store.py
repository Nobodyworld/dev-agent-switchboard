"""Helpers for interacting with the persisted live-file store."""

from __future__ import annotations

import datetime as dt
import hashlib
import os
from collections.abc import Callable
from pathlib import Path, PurePosixPath
from typing import NamedTuple, Optional, Tuple

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .db import AsyncSessionLocal, FILES_ROOT as CONFIGURED_FILES_ROOT
from .models import FileEntry
from .time_utils import utcnow

FILES_ROOT = Path(CONFIGURED_FILES_ROOT)

__all__ = [
    "FILES_ROOT",
    "FileWriteResult",
    "ensure_root",
    "full_path",
    "put_file",
    "etag_for_path",
]


class FileWriteResult(NamedTuple):
    """Metadata describing a file write performed via :func:`put_file`."""

    sha256: str
    size: int


def ensure_root() -> None:
    """Ensure the backing directory for live files exists."""

    FILES_ROOT.mkdir(parents=True, exist_ok=True)


def full_path(rel_path: str) -> Path:
    """Return a safe filesystem path for a user-provided relative path."""

    trimmed = rel_path.strip()
    if not trimmed:
        raise HTTPException(status_code=400, detail="invalid path")

    if "\\" in trimmed:
        raise HTTPException(status_code=400, detail="invalid path")

    relative = PurePosixPath(trimmed)
    if relative.is_absolute():
        raise HTTPException(status_code=400, detail="invalid path")

    root = FILES_ROOT.resolve()
    candidate = (root / relative).resolve()
    try:
        candidate.relative_to(root)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="invalid path") from exc
    return candidate


UTCNOW: Callable[[], dt.datetime] = utcnow


def _now() -> dt.datetime:
    """Return the current UTC timestamp."""

    return UTCNOW()


async def put_file(
    session: AsyncSession, rel_path: str, data: bytes
) -> FileWriteResult:
    """Persist ``data`` to ``rel_path`` and update or create the tracking entry."""

    ensure_root()
    path = full_path(rel_path)
    path.parent.mkdir(parents=True, exist_ok=True)

    path.write_bytes(data)

    sha = hashlib.sha256(data).hexdigest()
    size = len(data)
    entry = (
        await session.execute(select(FileEntry).where(FileEntry.path == rel_path))
    ).scalar_one_or_none()
    now = _now()
    if entry:
        entry.sha256 = sha
        entry.size = size
        entry.updated_at = now
    else:
        entry = FileEntry(path=rel_path, sha256=sha, size=size, updated_at=now)
        session.add(entry)
    await session.flush()
    return FileWriteResult(sha, size)


async def _ensure_entry_sha(
    session: AsyncSession, rel_path: str
) -> Tuple[Optional[str], bool]:
    """Return the SHA for ``rel_path`` and whether the database entry was updated."""

    entry = (
        await session.execute(select(FileEntry).where(FileEntry.path == rel_path))
    ).scalar_one_or_none()
    if entry and entry.sha256:
        return entry.sha256, False

    file_path = full_path(rel_path)
    if not os.path.exists(file_path):
        return None, False

    try:
        data = file_path.read_bytes()
    except FileNotFoundError:
        return None, False

    sha = hashlib.sha256(data).hexdigest()
    size = len(data)
    now = _now()

    if entry is None:
        entry = FileEntry(path=rel_path, sha256=sha, size=size, updated_at=now)
        session.add(entry)
    else:
        entry.sha256 = sha
        entry.size = size
        entry.updated_at = now

    return sha, True


async def etag_for_path(
    rel_path: str, session: Optional[AsyncSession] = None
) -> Optional[str]:
    """Return a quoted ETag for the given relative path if the file exists."""

    file_path = full_path(rel_path)
    if not os.path.exists(file_path):
        return None

    async def _resolve(target_session: AsyncSession) -> Tuple[Optional[str], bool]:
        return await _ensure_entry_sha(target_session, rel_path)

    if session is not None:
        sha, mutated = await _resolve(session)
        if sha is None:
            return None
        if mutated:
            await session.flush()
        return f'"{sha}"'

    async with AsyncSessionLocal() as owned_session:
        sha, mutated = await _resolve(owned_session)
        if sha is None:
            return None
        if mutated:
            await owned_session.commit()
        return f'"{sha}"'
