import hashlib, os, datetime as dt
from typing import Optional, Tuple
from sqlalchemy import select, insert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import IntegrityError
from fastapi import HTTPException
from .models import FileEntry
from .db import AsyncSessionLocal

FILES_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "storage", "files"))

def ensure_root():
    os.makedirs(FILES_ROOT, exist_ok=True)

def full_path(rel_path: str) -> str:
    rel = rel_path.strip("/")
    if ".." in rel:
        raise HTTPException(status_code=400, detail="invalid path")
    return os.path.join(FILES_ROOT, rel)

async def put_file(session: AsyncSession, rel_path: str, data: bytes) -> Tuple[str, int]:
    ensure_root()
    path = full_path(rel_path)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as f:
        f.write(data)
    sha = hashlib.sha256(data).hexdigest()
    size = len(data)
    entry = (await session.execute(select(FileEntry).where(FileEntry.path == rel_path))).scalar_one_or_none()
    now = dt.datetime.utcnow()
    if entry:
        entry.sha256 = sha
        entry.size = size
        entry.updated_at = now
    else:
        entry = FileEntry(path=rel_path, sha256=sha, size=size, updated_at=now)
        session.add(entry)
    await session.flush()
    return sha, size


async def _ensure_entry_sha(session: AsyncSession, rel_path: str) -> Tuple[Optional[str], bool]:
    """Return the SHA for ``rel_path`` and whether the database entry was updated."""

    entry = (await session.execute(select(FileEntry).where(FileEntry.path == rel_path))).scalar_one_or_none()
    if entry and entry.sha256:
        return entry.sha256, False

    file_path = full_path(rel_path)
    if not os.path.exists(file_path):
        return None, False

    try:
        with open(file_path, "rb") as handle:
            data = handle.read()
    except FileNotFoundError:
        return None, False

    sha = hashlib.sha256(data).hexdigest()
    size = len(data)
    now = dt.datetime.utcnow()

    if entry is None:
        entry = FileEntry(path=rel_path, sha256=sha, size=size, updated_at=now)
        session.add(entry)
    else:
        entry.sha256 = sha
        entry.size = size
        entry.updated_at = now

    return sha, True


async def etag_for_path(rel_path: str, session: Optional[AsyncSession] = None) -> Optional[str]:
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
