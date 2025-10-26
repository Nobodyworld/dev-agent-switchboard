import asyncio
import inspect
import os
import shutil
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

try:
    from server.db import Base, engine
    from server.file_store import FILES_ROOT, ensure_root
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


def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line(
        "markers",
        "asyncio: execute test coroutine via asyncio.run",
    )


@pytest.hookimpl(tryfirst=True)
def pytest_pyfunc_call(pyfuncitem: pytest.Function) -> bool | None:
    """Execute ``@pytest.mark.asyncio`` tests with fixture arguments safely."""

    if pyfuncitem.get_closest_marker("asyncio") is None:
        return None

    signature = inspect.signature(pyfuncitem.obj)
    kwargs = {
        name: pyfuncitem.funcargs[name]
        for name in signature.parameters
        if name in pyfuncitem.funcargs
    }

    missing_required = [
        name
        for name, parameter in signature.parameters.items()
        if parameter.default is inspect._empty
        and parameter.kind in (inspect.Parameter.POSITIONAL_OR_KEYWORD, inspect.Parameter.KEYWORD_ONLY)
        and name not in kwargs
    ]
    if missing_required:
        # Delegate back to pytest so it can surface a helpful error message.
        return None

    outcome = pyfuncitem.obj(**kwargs)
    if not inspect.isawaitable(outcome):  # pragma: no cover - defensive guardrail
        return None

    asyncio.run(outcome)
    return True


@pytest.fixture(autouse=True)
def clean_state():
    asyncio.run(_reset_database())
    _reset_files()
    yield
    asyncio.run(_reset_database())
    _reset_files()
