import hashlib
from pathlib import Path
from typing import Tuple

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .db import FILES_ROOT as CONFIGURED_FILES_ROOT
from .models import FileEntry

FILES_ROOT = Path(CONFIGURED_FILES_ROOT)


def ensure_root() -> None:
    FILES_ROOT.mkdir(parents=True, exist_ok=True)


def full_path(rel_path: str) -> Path:
    rel = rel_path.strip("/")
    candidate = (FILES_ROOT / rel).resolve()
    try:
        candidate.relative_to(FILES_ROOT)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="invalid path") from exc
    return candidate


async def put_file(session: AsyncSession, rel_path: str, data: bytes) -> Tuple[str, int]:
    ensure_root()
    path = full_path(rel_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("wb") as f:
        f.write(data)
    sha = hashlib.sha256(data).hexdigest()
    size = len(data)
    entry = (await session.execute(select(FileEntry).where(FileEntry.path == rel_path))).scalar_one_or_none()
    if entry:
        entry.sha256 = sha
        entry.size = size
        await session.merge(entry)
    else:
        entry = FileEntry(path=rel_path, sha256=sha, size=size)
        session.add(entry)
    return sha, size
