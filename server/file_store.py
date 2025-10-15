
import hashlib, os, datetime as dt
from typing import Tuple
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from fastapi import HTTPException
from .models import FileEntry

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
    if entry:
        entry.sha256 = sha
        entry.size = size
        await session.merge(entry)
    else:
        entry = FileEntry(path=rel_path, sha256=sha, size=size)
        session.add(entry)
    return sha, size
