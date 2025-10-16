import asyncio
import os
import shutil
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

try:
    from server.db import Base, engine  # noqa: E402
    from server.file_store import FILES_ROOT, ensure_root  # noqa: E402
except ModuleNotFoundError as exc:  # pragma: no cover - exercised when deps missing
    pytest.skip(
        f"Server dependencies unavailable: {exc}",
        allow_module_level=True,
    )


async def _reset_database() -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)


def _reset_files() -> None:
    if os.path.exists(FILES_ROOT):
        shutil.rmtree(FILES_ROOT)
    ensure_root()


@pytest.fixture(autouse=True)
def clean_state():
    asyncio.run(_reset_database())
    _reset_files()
    yield
    asyncio.run(_reset_database())
    _reset_files()
