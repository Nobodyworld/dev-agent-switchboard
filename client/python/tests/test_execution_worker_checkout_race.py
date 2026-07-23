"""Post-checkout admission races must dispose owned server leases safely."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncGenerator, Callable
from pathlib import Path
from unittest.mock import patch

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from client.python.execution_worker.client import (
    ExecutionClient,
    ExecutionOwnershipLostError,
)
from client.python.execution_worker.config import WorkerConfig
from client.python.execution_worker.worker import LocalWorker
from client.python.tests.execution_worker_test_support import work_order_payload
from client.python.tests.test_execution_worker_runtime import _config, _FakeClient
from client.python.tests.test_execution_worker_server_smoke import (
    _AsgiSession,
    _repository,
    _request,
)
from server.api import AppConfig, create_app
from server.api.dependencies import get_session
from server.db import Base
from server.execution.registry import get_trusted_manifest
from server.models import ExecutionLease, ExecutionWorker

_TOKEN = "worker-test-token"  # noqa: S105 - matches isolated API fixture
_LOCAL_ACTIVE_RUN = 99


class _CheckoutCallbackClient(_FakeClient):
    def __init__(self, order: dict[str, object]) -> None:
        manifest = get_trusted_manifest("worker-smoke", "1")
        assert manifest is not None
        super().__init__(order, manifest)
        self.on_checkout: Callable[[], None] | None = None
        self.lose_completion = False

    def checkout(self) -> dict[str, object]:
        payload = super().checkout()
        if self.on_checkout is not None:
            self.on_checkout()
        return payload

    def complete_run(self, _run_id: int, **payload: object) -> dict[str, object]:
        self.completed.append(dict(payload))
        if self.lose_completion:
            raise ExecutionOwnershipLostError(409)
        return {"id": 7, "status": payload["status"]}


def _unit_worker(tmp_path: Path) -> tuple[LocalWorker, _CheckoutCallbackClient]:
    manifest = get_trusted_manifest("worker-smoke", "1")
    assert manifest is not None
    client = _CheckoutCallbackClient(work_order_payload("a" * 40, manifest))
    worker = LocalWorker(
        _config(tmp_path, tmp_path / "canonical"),
        client,  # type: ignore[arg-type]
    )
    return worker, client


def test_shutdown_inside_checkout_completes_cancelled_without_side_effects(
    tmp_path: Path,
) -> None:
    worker, client = _unit_worker(tmp_path)
    client.on_checkout = worker.request_shutdown

    with (
        patch("client.python.execution_worker.worker.create_worktree") as create,
        patch("client.python.execution_worker.runner.subprocess.Popen") as popen,
    ):
        assert worker.poll_once() is True

    create.assert_not_called()
    popen.assert_not_called()
    assert len(client.completed) == 1
    assert client.completed[0]["status"] == "cancelled"
    assert client.completed[0]["terminal_reason"] == "worker_shutdown_before_start"
    assert client.completed[0]["cleanup_status"] == "not_started"
    assert worker._active_run_id is None


def test_shutdown_immediately_after_checkout_disposes_lease_once(
    tmp_path: Path,
) -> None:
    worker, client = _unit_worker(tmp_path)
    original_begin = LocalWorker._begin_run

    def shutdown_then_admit(instance: LocalWorker, run_id: int) -> str | None:
        instance.request_shutdown()
        return original_begin(instance, run_id)

    with (
        patch.object(
            LocalWorker,
            "_begin_run",
            autospec=True,
            side_effect=shutdown_then_admit,
        ),
        patch("client.python.execution_worker.worker.create_worktree") as create,
        patch("client.python.execution_worker.runner.subprocess.Popen") as popen,
    ):
        assert worker.poll_once() is True

    create.assert_not_called()
    popen.assert_not_called()
    assert len(client.completed) == 1
    assert client.completed[0]["terminal_reason"] == "worker_shutdown_before_start"


def test_local_concurrency_rejection_disposes_lease_and_preserves_local_state(
    tmp_path: Path,
) -> None:
    worker, client = _unit_worker(tmp_path)
    worker._active_run_id = _LOCAL_ACTIVE_RUN

    with (
        patch("client.python.execution_worker.worker.create_worktree") as create,
        patch("client.python.execution_worker.runner.subprocess.Popen") as popen,
    ):
        assert worker.poll_once() is True

    create.assert_not_called()
    popen.assert_not_called()
    assert len(client.completed) == 1
    assert (
        client.completed[0]["terminal_reason"]
        == "local_concurrency_rejected_after_checkout"
    )
    assert client.completed[0]["cleanup_status"] == "not_started"
    assert worker._active_run_id == _LOCAL_ACTIVE_RUN


def test_ownership_loss_while_disposing_admission_rejection_exits_safely(
    tmp_path: Path,
) -> None:
    worker, client = _unit_worker(tmp_path)
    client.on_checkout = worker.request_shutdown
    client.lose_completion = True

    assert worker.poll_once() is True

    assert len(client.completed) == 1
    assert worker._active_run_id is None


class _ServerRaceClient(ExecutionClient):
    def __init__(
        self, *args: object, on_checkout: Callable[[], None], **kwargs: object
    ):
        super().__init__(*args, **kwargs)  # type: ignore[arg-type]
        self._on_checkout = on_checkout

    def checkout(self) -> dict[str, object]:
        result = super().checkout()
        self._on_checkout()
        return result


@pytest.mark.parametrize("mode", ["shutdown", "concurrency"])
def test_server_backed_rejection_releases_capacity_for_second_worker(  # noqa: PLR0915
    tmp_path: Path, mode: str
) -> None:
    canonical, requested_sha, _ = _repository(tmp_path)
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / f'{mode}.db'}")
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    app = create_app(AppConfig(include_ui=False))

    async def isolated_session() -> AsyncGenerator[AsyncSession, None]:
        async with sessions() as session:
            yield session

    app.dependency_overrides[get_session] = isolated_session

    async def prepare() -> None:
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)

    def queue_order() -> int:
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
        return int(created["id"])

    asyncio.run(prepare())
    try:
        first_order = queue_order()
        config = WorkerConfig(
            base_url="http://switchboard.test",
            worker_id=f"race-worker-{mode}",
            display_name="Race worker",
            admin_token=_TOKEN,
            worker_root=tmp_path / "worker-root",
            evidence_root=tmp_path / "evidence-root",
            repositories={"Nobodyworld/dev-agent-switchboard": canonical},
        )

        def callback() -> None:
            return None

        client = _ServerRaceClient(
            config.base_url,
            config.worker_id,
            config.admin_token,
            session=_AsgiSession(app),  # type: ignore[arg-type]
            on_checkout=lambda: callback(),
        )
        worker = LocalWorker(config, client)
        if mode == "shutdown":
            callback = worker.request_shutdown
        else:
            worker._active_run_id = _LOCAL_ACTIVE_RUN
        worker.start()

        with (
            patch("client.python.execution_worker.worker.create_worktree") as create,
            patch("client.python.execution_worker.runner.subprocess.Popen") as popen,
        ):
            assert worker.poll_once() is True
        create.assert_not_called()
        popen.assert_not_called()

        runs = _request(app, "GET", f"/api/execution/runs?work_order_id={first_order}")
        assert len(runs) == 1
        assert runs[0]["status"] == "cancelled"
        expected_reason = (
            "worker_shutdown_before_start"
            if mode == "shutdown"
            else "local_concurrency_rejected_after_checkout"
        )
        assert runs[0]["terminal_reason"] == expected_reason
        assert runs[0]["cleanup_status"] == "not_started"

        async def capacity_proof() -> tuple[int, int]:
            async with sessions() as session:
                leases = await session.scalar(
                    select(func.count()).select_from(ExecutionLease)
                )
                active = await session.scalar(
                    select(ExecutionWorker.active_run_count).where(
                        ExecutionWorker.worker_id == config.worker_id
                    )
                )
            return int(leases), int(active)

        assert asyncio.run(capacity_proof()) == (0, 0)

        second_order = queue_order()
        second_config = WorkerConfig(
            base_url="http://switchboard.test",
            worker_id=f"second-worker-{mode}",
            display_name="Second worker",
            admin_token=_TOKEN,
            worker_root=tmp_path / "second-worker-root",
            evidence_root=tmp_path / "second-evidence-root",
            repositories={"Nobodyworld/dev-agent-switchboard": canonical},
        )
        with ExecutionClient(
            second_config.base_url,
            second_config.worker_id,
            second_config.admin_token,
            session=_AsgiSession(app),  # type: ignore[arg-type]
        ) as second_client:
            second_worker = LocalWorker(second_config, second_client)
            second_worker.start()
            checkout = second_client.checkout()
            run = checkout["run"]
            assert isinstance(run, dict)
            assert run["work_order_id"] == second_order
            second_client.complete_run(
                int(run["id"]),
                status="cancelled",
                terminal_reason="test_cleanup",
                cleanup_status="not_started",
            )
        assert asyncio.run(capacity_proof())[0] == 0
    finally:
        app.dependency_overrides.clear()
        asyncio.run(engine.dispose())
