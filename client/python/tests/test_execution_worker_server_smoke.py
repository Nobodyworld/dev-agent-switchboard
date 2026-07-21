# ruff: noqa: S603, S607
"""Server-backed, harmless ``worker-smoke@1`` acceptance coverage."""

from __future__ import annotations

import asyncio
import json
import subprocess
from collections.abc import AsyncGenerator
from pathlib import Path
from unittest.mock import patch
from urllib.parse import urlsplit

import httpx
from fastapi import FastAPI
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from client.python.execution_worker.client import ExecutionClient
from client.python.execution_worker.config import WorkerConfig
from client.python.execution_worker.worker import LocalWorker
from server.api import AppConfig, create_app
from server.api.dependencies import get_session
from server.db import Base
from server.models import ExecutionLease, ExecutionRun, ExecutionWorker

_TOKEN = "worker-test-token"  # noqa: S105 - non-secret test fixture
_HTTP_ERROR_STATUS = 400


def _git(path: Path, *argv: str) -> str:
    return subprocess.run(
        ["git", "-C", str(path), *argv],
        check=True,
        shell=False,
        capture_output=True,
        text=True,
    ).stdout.strip()


def _repository(tmp_path: Path) -> tuple[Path, str, str]:
    repository = tmp_path / "canonical"
    subprocess.run(["git", "init", str(repository)], check=True, shell=False)
    _git(repository, "config", "user.email", "worker@example.test")
    _git(repository, "config", "user.name", "Worker Test")
    (repository / "README.md").write_text("first\n", encoding="utf-8")
    _git(repository, "add", "README.md")
    _git(repository, "commit", "-m", "first")
    first = _git(repository, "rev-parse", "HEAD")
    (repository / "README.md").write_text("second\n", encoding="utf-8")
    _git(repository, "commit", "-am", "second")
    return repository, first, _git(repository, "status", "--porcelain=v1")


class _AsgiSession:
    """Minimal synchronous requests-session adapter over the real FastAPI API."""

    def __init__(self, app: FastAPI) -> None:
        self._app = app

    def request(self, method: str, url: str, **kwargs: object) -> _AsgiResponse:
        split_url = urlsplit(url)
        request_target = split_url.path
        if split_url.query:
            request_target = f"{request_target}?{split_url.query}"

        async def send() -> tuple[int, bytes, dict[str, str], str]:
            transport = httpx.ASGITransport(app=self._app)
            async with httpx.AsyncClient(
                transport=transport, base_url="http://switchboard.test"
            ) as client:
                raw = await client.request(
                    method,
                    request_target,
                    headers=kwargs.get("headers"),
                    json=kwargs.get("json"),
                )
                return raw.status_code, raw.content, dict(raw.headers), str(raw.url)

        status_code, content, headers, response_url = asyncio.run(send())
        return _AsgiResponse(status_code, content, headers, response_url)

    def close(self) -> None:
        return None


class _AsgiResponse:
    """Small response surface consumed by the synchronous execution client."""

    def __init__(
        self,
        status_code: int,
        content: bytes,
        headers: dict[str, str],
        url: str,
    ) -> None:
        self.status_code = status_code
        self._content = content
        self.headers = headers
        self.url = url

    @property
    def text(self) -> str:
        return self._content.decode("utf-8", errors="replace")

    def json(self) -> dict:
        return json.loads(self.text)

    def raise_for_status(self) -> None:
        if self.status_code >= _HTTP_ERROR_STATUS:
            raise RuntimeError(f"unexpected execution API status: {self.status_code}")


class _CountingAsgiSession(_AsgiSession):
    """Track ambiguous-write-sensitive completion calls over the real API."""

    def __init__(self, app: FastAPI) -> None:
        super().__init__(app)
        self.completion_calls = 0

    def request(self, method: str, url: str, **kwargs: object) -> _AsgiResponse:
        if method.lower() == "post" and url.endswith("/complete"):
            self.completion_calls += 1
        return super().request(method, url, **kwargs)


def _request(
    app: FastAPI, method: str, path: str, payload: object | None = None
) -> dict:
    response = _AsgiSession(app).request(
        method,
        f"http://switchboard.test{path}",
        json=payload,
        headers={"Authorization": f"Bearer {_TOKEN}"},
    )
    if response.status_code >= _HTTP_ERROR_STATUS:
        raise AssertionError(
            f"execution API {method} {path} returned {response.status_code}: "
            f"{response.text}"
        )
    decoded = response.json()
    if decoded == {}:
        raise AssertionError(
            f"execution API {method} {path} returned empty JSON with "
            f"status {response.status_code}, headers {dict(response.headers)}, and "
            f"content {response.text[:120]!r}"
        )
    return decoded


def test_server_backed_worker_smoke_executes_exact_sha_and_releases_lease(
    tmp_path: Path,
) -> None:
    canonical, requested_sha, status_before = _repository(tmp_path)
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'worker-smoke.db'}")
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    app = create_app(AppConfig(include_ui=False))

    async def isolated_session() -> AsyncGenerator[AsyncSession, None]:
        async with sessions() as session:
            yield session

    app.dependency_overrides[get_session] = isolated_session

    async def prepare() -> None:
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)

    asyncio.run(prepare())
    try:
        created = _request(
            app,
            "POST",
            "/api/execution/work-orders",
            {
                "repository_full_name": "Nobodyworld/dev-agent-switchboard",
                "commit_sha": requested_sha,
                "manifest": {"name": "worker-smoke", "version": "1"},
                "timeout_seconds": 120,
            },
        )
        approved = _request(
            app,
            "POST",
            f"/api/execution/work-orders/{created['id']}/approve",
            {},
        )
        assert approved["status"] == "queued"

        config = WorkerConfig(
            base_url="http://switchboard.test",
            worker_id="server-smoke-worker",
            display_name="Server smoke worker",
            admin_token=_TOKEN,
            worker_root=tmp_path / "worker-root",
            repositories={"Nobodyworld/dev-agent-switchboard": canonical},
            heartbeat_interval_seconds=0.05,
        )
        with ExecutionClient(
            config.base_url,
            config.worker_id,
            config.admin_token,
            session=_AsgiSession(app),  # type: ignore[arg-type]
        ) as client:
            worker = LocalWorker(config, client)
            worker.start()
            assert worker.poll_once() is True

        runs = _request(
            app, "GET", f"/api/execution/runs?work_order_id={created['id']}"
        )
        assert len(runs) == 1
        run = runs[0]
        assert run["status"] == "succeeded", {
            key: run[key]
            for key in (
                "status",
                "terminal_reason",
                "cleanup_status",
                "result_summary",
                "evidence_metadata",
            )
        }
        assert requested_sha in run["result_summary"]
        assert run["cleanup_status"] == "succeeded"

        run_directory = next((tmp_path / "worker-root").glob("run-*"))
        assert (run_directory / "ownership.json").is_file()
        assert (run_directory / "result.json").is_file()
        record = json.loads((run_directory / "result.json").read_text(encoding="utf-8"))
        assert record["result_summary"]["checked_out_sha"] == requested_sha
        assert (run_directory / "logs" / "python-version.stdout.log").exists()
        assert (run_directory / "logs" / "git-head.stdout.log").read_text(
            encoding="utf-8"
        ).strip() == requested_sha
        assert not (run_directory / "checkout").exists()
        assert _git(canonical, "rev-parse", "HEAD") != requested_sha
        assert _git(canonical, "status", "--porcelain=v1") == status_before

        async def database_proof() -> tuple[int, int, int]:
            async with sessions() as session:
                workers = await session.scalar(
                    select(func.count()).select_from(ExecutionWorker)
                )
                leases = await session.scalar(
                    select(func.count()).select_from(ExecutionLease)
                )
                persisted_runs = await session.scalar(
                    select(func.count()).select_from(ExecutionRun)
                )
            return int(workers), int(leases), int(persisted_runs)

        assert asyncio.run(database_proof()) == (1, 0, 1)
    finally:
        app.dependency_overrides.clear()
        asyncio.run(engine.dispose())


def test_server_backed_local_record_failure_completes_once_and_releases_lease(
    tmp_path: Path,
) -> None:
    canonical, requested_sha, _ = _repository(tmp_path)
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'record-fail.db'}")
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    app = create_app(AppConfig(include_ui=False))

    async def isolated_session() -> AsyncGenerator[AsyncSession, None]:
        async with sessions() as session:
            yield session

    app.dependency_overrides[get_session] = isolated_session

    async def prepare() -> None:
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)

    asyncio.run(prepare())
    try:
        created = _request(
            app,
            "POST",
            "/api/execution/work-orders",
            {
                "repository_full_name": "Nobodyworld/dev-agent-switchboard",
                "commit_sha": requested_sha,
                "manifest": {"name": "worker-smoke", "version": "1"},
                "timeout_seconds": 120,
            },
        )
        _request(
            app,
            "POST",
            f"/api/execution/work-orders/{created['id']}/approve",
            {},
        )
        config = WorkerConfig(
            base_url="http://switchboard.test",
            worker_id="record-failure-worker",
            display_name="Record failure worker",
            admin_token=_TOKEN,
            worker_root=tmp_path / "worker-root",
            repositories={"Nobodyworld/dev-agent-switchboard": canonical},
            heartbeat_interval_seconds=0.05,
        )
        session = _CountingAsgiSession(app)
        with ExecutionClient(
            config.base_url,
            config.worker_id,
            config.admin_token,
            session=session,  # type: ignore[arg-type]
        ) as client:
            worker = LocalWorker(config, client)
            worker.start()
            with patch.object(
                LocalWorker, "_write_run_record", side_effect=OSError("disk")
            ):
                assert worker.poll_once() is True

        runs = _request(
            app, "GET", f"/api/execution/runs?work_order_id={created['id']}"
        )
        assert len(runs) == 1
        run = runs[0]
        assert run["status"] == "failed"
        assert run["terminal_reason"] == "local_result_record_failed"
        assert "local_record_failed:OSError" in run["cleanup_status"]
        assert session.completion_calls == 1

        async def capacity_proof() -> tuple[int, int]:
            async with sessions() as database:
                leases = await database.scalar(
                    select(func.count()).select_from(ExecutionLease)
                )
                active = await database.scalar(
                    select(ExecutionWorker.active_run_count).where(
                        ExecutionWorker.worker_id == config.worker_id
                    )
                )
            return int(leases), int(active)

        assert asyncio.run(capacity_proof()) == (0, 0)
    finally:
        app.dependency_overrides.clear()
        asyncio.run(engine.dispose())
