import os
from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker, declarative_base

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


async def get_session() -> AsyncSession:
    async with AsyncSessionLocal() as session:
        yield session
