import asyncio
import datetime as dt
import shutil
import sys
from collections.abc import Callable, Iterator
from pathlib import Path

import pytest
from fastapi import FastAPI

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

configuration_service_module = None
try:
    from server import db, file_store
    from server.api import AppConfig, create_app
    from server.application import factory as application_factory
    from server.application import (
        configuration_service as _configuration_service_module,
    )
    from server.db import Base, engine
    from server.middleware import reset_all_rate_limit_middleware
    from server.settings import reload_rate_limit_settings
except ModuleNotFoundError as exc:  # pragma: no cover - exercised when deps missing
    pytest.skip(
        f"Server dependencies unavailable: {exc}",
        allow_module_level=True,
    )
else:
    configuration_service_module = _configuration_service_module


async def _reset_database() -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)


def _reset_files(*, recreate: bool = True) -> None:
    root = Path(file_store.FILES_ROOT)
    if root.exists():
        shutil.rmtree(root)
    if recreate:
        file_store.ensure_root()


def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line(
        "markers",
        "asyncio: execute test coroutine via asyncio.run",
    )
    config.addinivalue_line("markers", "unit: unit-level tests")
    config.addinivalue_line("markers", "integration: integration tests")
    config.addinivalue_line("markers", "e2e: end-to-end tests")


@pytest.fixture
def files_root(
    tmp_path_factory: pytest.TempPathFactory,
    monkeypatch: pytest.MonkeyPatch,
) -> Path:
    root = Path(tmp_path_factory.mktemp("live-files"))
    monkeypatch.setenv("FILES_ROOT", str(root))
    monkeypatch.setattr(db, "FILES_ROOT", root, raising=False)
    monkeypatch.setattr(file_store, "FILES_ROOT", root, raising=False)
    if configuration_service_module is not None:
        monkeypatch.setattr(
            configuration_service_module,
            "FILES_ROOT",
            root,
            raising=False,
        )
    return root


@pytest.fixture(autouse=True)
def clean_state(files_root: Path):
    _ = files_root
    reload_rate_limit_settings()
    reset_all_rate_limit_middleware()
    asyncio.run(_reset_database())
    _reset_files()
    yield
    reset_all_rate_limit_middleware()
    asyncio.run(_reset_database())
    _reset_files(recreate=False)


@pytest.fixture(autouse=True)
def freeze_execution_reuse_clock(
    request: pytest.FixtureRequest,
    monkeypatch: pytest.MonkeyPatch,
) -> Iterator[None]:
    """Keep fixed reuse evidence inside its synthetic retention window."""

    if request.module.__name__.rsplit(".", maxsplit=1)[-1] != "test_execution_reuse":
        yield
        return

    # The module's synthetic evidence is fixed at this instant. Freeze the
    # injected service clock so its 14-day retention contract never date-rots.
    fixed_now = dt.datetime(2026, 7, 30, 12, tzinfo=dt.UTC).replace(tzinfo=None)
    monkeypatch.setattr(application_factory, "utcnow_naive", lambda: fixed_now)
    monkeypatch.setattr(request.module, "utcnow_naive", lambda: fixed_now)
    yield


@pytest.fixture
def app_factory() -> Callable[[AppConfig | None], FastAPI]:
    def factory(config: AppConfig | None = None) -> FastAPI:
        return create_app(config)

    return factory


@pytest.fixture
def app_instance(app_factory: Callable[[AppConfig | None], FastAPI]) -> FastAPI:
    return app_factory()
