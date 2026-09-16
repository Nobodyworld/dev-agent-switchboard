# ruff: noqa: PLR2004 - explicit fixture counts and HTTP status assertions
"""Scoped credentials: lifecycle, complete route boundary, persistence and migration."""

from __future__ import annotations

import asyncio
import hashlib
import secrets
import subprocess
import sys
from dataclasses import replace
from types import SimpleNamespace

import pytest
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient
from sqlalchemy import inspect, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from client.python.execution_worker.client import WorkerExecutionClient
from client.python.execution_worker.worker import LocalWorker
from client.python.tests.test_execution_worker_runtime import _config, _git, _repository
from server.api import lifecycle
from server.api.dependencies import require_admin_token, require_worker_token
from server.api.routers import (
    execution,
    github_execution,
    worker_credentials,
    worker_execution,
)
from server.db import AsyncSessionLocal, Base
from server.execution import credentials, registry
from server.execution.evidence import compute_reuse_identity_hash
from server.execution.text_policy import validate_no_absolute_local_path
from server.models import ExecutionWorker, WorkerCredential
from server.settings import reload_admin_token
from server.tests.test_execution_reuse import _identity
from server.time_utils import utcnow_naive


@pytest.fixture
def api(app_instance, monkeypatch, request):
    if getattr(request, "param", None) == "active-process":
        original = registry.get_trusted_manifest("worker-smoke", "1")
        step = registry.TrustedStep(
            id="credential-loss-step",
            title="Bounded credential loss process",
            argv=(sys.executable, "-c", "import time; time.sleep(30)"),
            required=True,
            timeout_seconds=30,
            output_summary_limit=4096,
        )
        manifest = replace(
            original,
            execution_steps=(step,),
            fixed_step_metadata=[step.safe_metadata()],
        )
        monkeypatch.setattr(
            registry,
            "_TRUSTED_MANIFESTS",
            tuple(
                manifest if item is original else item
                for item in registry.iter_trusted_manifests()
            ),
        )
    monkeypatch.setenv("SWITCHBOARD_ADMIN_TOKEN", "synthetic-administrator-value")
    reload_admin_token()
    with TestClient(app_instance) as client:
        client.headers["Authorization"] = "Bearer synthetic-administrator-value"
        yield client


def issue(api, worker_id="worker-a"):
    result = api.post(f"/api/execution/worker-credentials/{worker_id}/issue", json={})
    assert result.status_code == 200
    assert result.headers["cache-control"] == "no-store"
    return result.json()


def worker_headers(issued):
    return {"Authorization": f"Bearer {issued['worker_token']}"}


def test_issuance_rotation_revocation_and_no_plaintext(api, caplog):
    issued = issue(api)
    token = issued["worker_token"]
    assert credentials.TOKEN_PATTERN.fullmatch(token)
    assert (
        api.post(
            "/api/execution/worker-credentials/worker-a/issue", json={}
        ).status_code
        == 409
    )
    metadata = api.get("/api/execution/worker-credentials/worker-a").json()
    assert "worker_token" not in metadata and "verifier" not in metadata

    async def persisted():
        async with AsyncSessionLocal() as session:
            return (
                (await session.execute(select(WorkerCredential.__table__)))
                .mappings()
                .all()
            )

    rows = asyncio.run(persisted())
    assert len(rows) == 1
    assert token not in str(rows) and token.split(".")[-1] not in str(rows)
    assert (
        rows[0]["verifier"] == hashlib.sha256(token.split(".")[-1].encode()).hexdigest()
    )
    assert (
        api.post(
            "/api/execution/worker/checkout",
            json={"worker_id": "worker-a"},
            headers=worker_headers(issued),
        ).status_code
        == 200
    )
    rotated = api.post(
        "/api/execution/worker-credentials/worker-a/rotate",
        json={"credential_id": issued["credential_id"]},
    ).json()
    assert rotated["worker_token"] != token
    assert len(asyncio.run(persisted())) == 1
    assert (
        api.post(
            "/api/execution/worker/checkout",
            json={"worker_id": "worker-a"},
            headers=worker_headers(issued),
        ).status_code
        == 401
    )
    assert (
        api.post(
            "/api/execution/worker-credentials/worker-a/rotate",
            json={"credential_id": issued["credential_id"]},
        ).status_code
        == 409
    )
    payload = {"credential_id": rotated["credential_id"]}
    first = api.post("/api/execution/worker-credentials/worker-a/revoke", json=payload)
    second = api.post("/api/execution/worker-credentials/worker-a/revoke", json=payload)
    assert first.status_code == second.status_code == 200
    assert first.json() == second.json()
    assert (
        api.post(
            "/api/execution/worker/checkout",
            json={"worker_id": "worker-a"},
            headers=worker_headers(rotated),
        ).status_code
        == 401
    )
    assert token not in caplog.text and rotated["worker_token"] not in caplog.text


def test_provisioned_worker_is_visible_but_unavailable_until_registration(api):
    issued = issue(api)
    response = api.get("/api/execution/workers?limit=100&offset=0")
    assert response.status_code == 200
    assert response.json()["total"] == 1
    item = response.json()["items"][0]
    assert item["worker_id"] == "worker-a"
    assert item["repository_full_names"] == []
    assert item["status"] == "offline"
    assert item["activity_state"] == "unavailable"
    assert item["active_run_count"] == 0
    assert item["repository_write_capability"] is False
    assert issued["worker_token"] not in response.text
    registration = {
        "worker_id": "worker-a",
        "display_name": "Worker A",
        "operating_system": "windows",
        "architecture": "amd64",
        "repository_full_names": [],
    }
    headers = worker_headers(issued)
    assert (
        api.post(
            "/api/execution/worker/workers", json=registration, headers=headers
        ).status_code
        == 422
    )
    registration["repository_full_names"] = ["Nobodyworld/dev-agent-switchboard"]
    assert (
        api.post(
            "/api/execution/worker/workers", json=registration, headers=headers
        ).status_code
        == 200
    )
    registered = api.get("/api/execution/workers?limit=100&offset=0")
    assert registered.status_code == 200
    assert registered.json()["total"] == 1
    item = registered.json()["items"][0]
    assert item["repository_full_names"] == registration["repository_full_names"]
    assert item["status"] == "online"


@pytest.mark.parametrize(
    "kind",
    [
        "wrong",
        "unknown",
        "malformed",
        "admin",
        "duplicate",
        "mixed",
        "whitespace",
        "missing",
    ],
)
def test_bad_authentication_is_bounded(api, kind):
    issued = issue(api)
    token = issued["worker_token"]
    if kind == "wrong":
        token = token[:-1] + ("a" if token[-1] != "a" else "b")
    if kind == "unknown":
        token = f"swb_w1.{secrets.token_hex(16)}.{secrets.token_hex(32)}"
    if kind == "malformed":
        token = token[:-1]
    if kind == "admin":
        token = api.headers["Authorization"].removeprefix("Bearer ")
    if kind == "whitespace":
        token += " "
    if kind == "missing":
        token = ""
    headers = [("Authorization", f"Bearer {token}")]
    if kind == "duplicate":
        headers.append(headers[0])
    if kind == "mixed":
        headers.append(("X-Switchboard-Admin-Token", "synthetic-administrator-value"))
    response = api.post(
        "/api/execution/worker/checkout",
        json={"worker_id": "worker-a"},
        headers=headers,
    )
    assert response.status_code == 401
    assert response.json() == {"detail": "worker_authentication_failed"}


def test_cross_worker_path_body_query_and_run(api):
    issued = issue(api)
    issue(api, "worker-b")
    headers = worker_headers(issued)
    for path, body in [
        ("/api/execution/worker/checkout", {"worker_id": "worker-b"}),
        ("/api/execution/worker/workers/worker-b/heartbeat", {}),
        (
            "/api/execution/worker/checkout?worker_id=worker-b",
            {"worker_id": "worker-a"},
        ),
        (
            "/api/execution/worker/checkout?worker_id=worker-a&worker_id=worker-b",
            {"worker_id": "worker-a"},
        ),
    ]:
        assert api.post(path, json=body, headers=headers).status_code == 403
    for path in ["runs/999", "work-orders/999", "manifests/worker-smoke/1?run_id=999"]:
        assert (
            api.get(f"/api/execution/worker/{path}", headers=headers).status_code == 403
        )


def test_worker_cannot_call_any_administrator_execution_route(api):
    issued = issue(api)
    routers = (
        execution.router,
        github_execution.router,
        worker_credentials.router,
        worker_execution.router,
    )
    routes = [r for router in routers for r in router.routes if isinstance(r, APIRoute)]
    assert {r.path_format for r in routes} == {
        p for p in api.app.openapi()["paths"] if p.startswith("/api/execution")
    }
    worker_routes = [r for r in routes if r.path.startswith("/api/execution/worker/")]
    assert len(worker_routes) == 9
    for route in routes:
        dependencies = {d.call for d in route.dependant.dependencies}
        if route in worker_routes:
            assert require_worker_token in dependencies
            assert require_admin_token not in dependencies
            continue
        assert require_admin_token in dependencies
        path = route.path
        for name in route.param_convertors:
            path = path.replace("{" + name + "}", "1").replace(
                "{" + name + ":path}", "example/repo"
            )
        for method in route.methods:
            response = api.request(
                method, path, json={}, headers=worker_headers(issued)
            )
            assert response.status_code == 401, (method, path, response.status_code)
    for path in ["/api/system/state", "/api/agents", "/api/files/example"]:
        assert api.post(path, json={}, headers=worker_headers(issued)).status_code in {
            401,
            404,
            405,
        }


def test_secret_input_errors_and_text_policy_are_bounded(api):
    issued = issue(api)
    token = issued["worker_token"]
    for path in [
        "/api/execution/worker-credentials/worker-a/issue",
        "/api/execution/worker/checkout",
    ]:
        headers = worker_headers(issued) if path.endswith("checkout") else None
        response = api.post(path, json={"secret": token}, headers=headers)
        assert response.status_code == 422
        assert token not in response.text
    with pytest.raises(ValueError, match="credential"):
        validate_no_absolute_local_path(token)


def test_issuance_requires_configured_admin(api, monkeypatch):
    monkeypatch.delenv("SWITCHBOARD_ADMIN_TOKEN")
    reload_admin_token()
    api.headers.pop("Authorization")
    assert (
        api.post(
            "/api/execution/worker-credentials/worker-a/issue", json={}
        ).status_code
        == 503
    )
    assert (
        api.get(
            "/api/execution/catalog", headers={"Authorization": "Bearer swb_w1.invalid"}
        ).status_code
        == 401
    )
    assert (
        api.get(
            "/api/execution/catalog",
            headers={"Authorization": "Bearer synthetic-demo-sentinel"},
        ).status_code
        == 200
    )


@pytest.mark.asyncio
async def test_prior_schema_and_repeated_startup_preserve_verifier(
    tmp_path, monkeypatch
):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'previous.db'}")
    factory = async_sessionmaker(engine, expire_on_commit=False)
    monkeypatch.setattr(lifecycle, "engine", engine)
    monkeypatch.setattr(lifecycle, "AsyncSessionLocal", factory)
    try:
        async with engine.begin() as connection:
            await connection.run_sync(
                lambda conn: Base.metadata.create_all(
                    conn,
                    tables=[
                        table
                        for table in Base.metadata.sorted_tables
                        if table.name != "execution_worker_credentials"
                    ],
                )
            )
        async with factory() as session:
            session.add(
                ExecutionWorker(
                    worker_id="prior-worker",
                    display_name="Preserved prior worker",
                    last_heartbeat_at=utcnow_naive(),
                    operating_system="windows",
                    architecture="amd64",
                    capabilities={"prior_capability": True},
                    repository_full_names=["Nobodyworld/dev-agent-switchboard"],
                )
            )
            await session.commit()
        async with lifecycle.lifespan(None):
            pass
        async with factory() as session:
            row, token = await credentials.issue(session, "prior-worker")
            verifier = row.verifier
            await session.commit()
        for _ in range(2):
            async with lifecycle.lifespan(None):
                pass
        async with factory() as session:
            row = await session.get(WorkerCredential, "prior-worker")
            assert row.verifier == verifier
            worker = (
                await session.execute(
                    select(ExecutionWorker).where(
                        ExecutionWorker.worker_id == "prior-worker"
                    )
                )
            ).scalar_one()
            assert worker.display_name == "Preserved prior worker"
            assert worker.capabilities == {"prior_capability": True}
            assert worker.repository_full_names == ["Nobodyworld/dev-agent-switchboard"]
            assert await credentials.authenticate(session, token) is not None
        async with engine.begin() as connection:
            columns = await connection.run_sync(
                lambda conn: inspect(conn).get_columns("execution_worker_credentials")
            )
            assert {c["name"] for c in columns} == {
                "worker_id",
                "credential_id",
                "verifier",
                "created_at",
                "rotated_at",
                "revoked_at",
            }
    finally:
        await engine.dispose()


def test_known_other_worker_assignment_and_registration_are_denied(api):
    first, second = issue(api), issue(api, "worker-b")
    registration = {
        "worker_id": "worker-b",
        "display_name": "Worker B",
        "operating_system": "windows",
        "architecture": "amd64",
        "python_version": "3.13.7",
    }
    assert (
        api.post(
            "/api/execution/worker/workers",
            json=registration,
            headers=worker_headers(first),
        ).status_code
        == 403
    )
    assert (
        api.post(
            "/api/execution/worker/workers",
            json=registration,
            headers=worker_headers(second),
        ).status_code
        == 200
    )
    order = api.post(
        "/api/execution/work-orders",
        json={
            "repository_full_name": "Nobodyworld/dev-agent-switchboard",
            "commit_sha": "a" * 40,
            "manifest": {"name": "validate-switchboard", "version": "1"},
        },
    ).json()
    assert (
        api.post(
            f"/api/execution/work-orders/{order['id']}/approve", json={}
        ).status_code
        == 200
    )
    assigned = api.post(
        "/api/execution/worker/checkout",
        json={"worker_id": "worker-b"},
        headers=worker_headers(second),
    ).json()
    run_id = assigned["run"]["id"]
    for path in [
        f"runs/{run_id}",
        f"work-orders/{order['id']}",
        f"manifests/validate-switchboard/1?run_id={run_id}",
    ]:
        assert (
            api.get(
                f"/api/execution/worker/{path}", headers=worker_headers(first)
            ).status_code
            == 403
        )
        assert (
            api.get(
                f"/api/execution/worker/{path}", headers=worker_headers(second)
            ).status_code
            == 200
        )
    identity = _identity(SimpleNamespace(**order))
    for suffix, body in [
        (
            "reuse-candidate",
            {
                "worker_id": "worker-a",
                "reuse_identity": identity.model_dump(mode="json"),
                "reuse_identity_hash": compute_reuse_identity_hash(identity),
            },
        ),
        ("heartbeat", {"worker_id": "worker-a"}),
        ("complete", {"worker_id": "worker-a", "status": "failed"}),
    ]:
        assert (
            api.post(
                f"/api/execution/worker/runs/{run_id}/{suffix}",
                json=body,
                headers=worker_headers(first),
            ).status_code
            == 403
        )
    assert (
        api.post(
            f"/api/execution/worker/runs/{run_id}/heartbeat",
            json={"worker_id": "worker-a"},
            headers=worker_headers(second),
        ).status_code
        == 403
    )


@pytest.mark.asyncio
async def test_concurrent_rotation_has_one_winner_and_no_overlapping_credentials():
    async with AsyncSessionLocal() as session:
        row, previous = await credentials.issue(session, "concurrent-worker")
        expected_id = row.credential_id
        await session.commit()

    async def attempt():
        async with AsyncSessionLocal() as session:
            try:
                _row, token = await credentials.rotate(
                    session, "concurrent-worker", expected_id
                )
                await session.commit()
                return token
            except credentials.CredentialConflictError:
                await session.rollback()
                return None

    results = await asyncio.gather(attempt(), attempt())
    winners = [token for token in results if token is not None]
    assert len(winners) == 1
    async with AsyncSessionLocal() as session:
        assert await credentials.authenticate(session, previous) is None
        assert await credentials.authenticate(session, winners[0]) is not None


def test_valid_and_unknown_secret_use_constant_time_comparison(api, monkeypatch):
    issued = issue(api)
    calls = []
    compare = credentials.hmac.compare_digest

    def checked(left, right):
        calls.append((len(left), len(right)))
        return compare(left, right)

    monkeypatch.setattr(credentials.hmac, "compare_digest", checked)
    for token in [
        issued["worker_token"],
        f"swb_w1.{secrets.token_hex(16)}.{secrets.token_hex(32)}",
    ]:
        api.post(
            "/api/execution/worker/checkout",
            json={"worker_id": "worker-a"},
            headers={"Authorization": f"Bearer {token}"},
        )
    assert calls == [(64, 64), (64, 64)]


@pytest.mark.parametrize("api", ["active-process"], indirect=True)
@pytest.mark.parametrize("transition", ["rotate", "revoke"])
def test_credential_transition_cancels_real_active_process(
    api, tmp_path, monkeypatch, transition
):
    canonical, sha = _repository(tmp_path)
    manifest = registry.get_trusted_manifest("worker-smoke", "1")
    step = manifest.execution_steps[0]
    issued = issue(api, "worker-1")
    client = WorkerExecutionClient(
        "http://testserver", "worker-1", issued["worker_token"], session=api
    )
    config = _config(tmp_path, canonical, worker_token=issued["worker_token"])
    worker = LocalWorker(config, client)
    worker.start()
    order_response = api.post(
        "/api/execution/work-orders",
        json={
            "repository_full_name": "Nobodyworld/dev-agent-switchboard",
            "commit_sha": sha,
            "timeout_seconds": 120,
            "manifest": {"name": "worker-smoke", "version": "1"},
        },
    )
    assert order_response.status_code == 200, order_response.text
    order = order_response.json()
    assert (
        api.post(
            f"/api/execution/work-orders/{order['id']}/approve", json={}
        ).status_code
        == 200
    )
    launched = []
    real_popen = subprocess.Popen

    def revoke_after_process_started(argv, *args, **kwargs):
        process = real_popen(argv, *args, **kwargs)
        if tuple(argv) == step.argv:
            launched.append(process)
            assert process.poll() is None
            response = api.post(
                f"/api/execution/worker-credentials/worker-1/{transition}",
                json={"credential_id": issued["credential_id"]},
            )
            assert response.status_code == 200
        return process

    monkeypatch.setattr(subprocess, "Popen", revoke_after_process_started)
    try:
        assert worker.poll_once() is True
        assert len(launched) == 1, [
            (run["status"], run["terminal_reason"])
            for run in api.get(
                f"/api/execution/runs?work_order_id={order['id']}"
            ).json()
        ]
        assert launched[0].poll() is not None
        assert worker.shutting_down
        assert worker.poll_once() is False
        runs = api.get(f"/api/execution/runs?work_order_id={order['id']}").json()
        assert len(runs) == 1
        assert runs[0]["status"] == "running"
        assert runs[0]["finished_at"] is None
        assert list(config.worker_root.glob("run-*")) == []
        retained = config.evidence_root / f"run-{runs[0]['id']}" / "result.json"
        assert retained.is_file()
        assert issued["worker_token"] not in retained.read_text(encoding="utf-8")
        assert _git(canonical, "rev-parse", "HEAD") == sha
    finally:
        for process in launched:
            if process.poll() is None:
                process.terminate()
                process.wait(timeout=5)
