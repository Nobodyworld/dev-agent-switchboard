# ruff: noqa: PLR2004, S603, S607
"""Server-backed, harmless ``worker-smoke@1`` acceptance coverage."""

from __future__ import annotations

import asyncio
import hashlib
import json
import subprocess
from collections.abc import AsyncGenerator
from http import HTTPStatus
from pathlib import Path
from unittest.mock import patch
from urllib.parse import urlsplit

import httpx
from fastapi import FastAPI
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from client.python.execution_worker import worker as worker_module
from client.python.execution_worker.client import ExecutionClient
from client.python.execution_worker.config import WorkerConfig
from client.python.execution_worker.evidence import EvidenceStore
from client.python.execution_worker.worker import LocalWorker
from server.api import AppConfig, create_app
from server.api.dependencies import (
    SessionDependency,
    get_github_adapter_service,
    get_session,
)
from server.application import build_execution_service
from server.db import Base
from server.execution.evidence import ExecutionEvidence, compute_evidence_fingerprint
from server.execution.registry import get_trusted_manifest
from server.github_adapter.errors import (
    GitHubAmbiguousWriteError,
    GitHubTransportError,
)
from server.github_adapter.repository import GitHubAdapterRepository
from server.github_adapter.service import (
    GitHubAdapterDependencies,
    GitHubAdapterService,
)
from server.github_adapter.transport import (
    GitHubActorIdentity,
    GitHubComment,
    GitHubCommentListing,
    GitHubTransport,
    ResolvedPullRequest,
)
from server.models import ExecutionLease, ExecutionRun, ExecutionWorker
from server.settings import GitHubSettings
from server.time_utils import utcnow_naive

_TOKEN = "worker-test-token"  # noqa: S105 - non-secret test fixture
_HTTP_ERROR_STATUS = 400
_EXPECTED_VALIDATION_RUNS = 2
_GITHUB_TEST_TOKEN = "offline-acceptance-secret-placeholder"  # noqa: S105
_GITHUB_ACTOR = GitHubActorIdentity(actor_id=700, node_id="U_acceptance")


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


def _validation_repository(tmp_path: Path) -> tuple[Path, tuple[str, str], str]:
    repository = tmp_path / "validation-canonical"
    subprocess.run(["git", "init", str(repository)], check=True, shell=False)
    _git(repository, "config", "user.email", "worker@example.test")
    _git(repository, "config", "user.name", "Worker Test")
    for directory in ("server", "client", "scripts", "tests", "web"):
        (repository / directory).mkdir()
        (repository / directory / "__init__.py").write_text("", encoding="utf-8")
    (repository / "server" / "sample.py").write_text(
        "def answer() -> int:\n    return 42\n", encoding="utf-8"
    )
    (repository / "tests" / "test_sample.py").write_text(
        "from server.sample import answer\n\n\ndef test_answer() -> None:\n"
        "    assert answer() == 42\n",
        encoding="utf-8",
    )
    (repository / "switchboard_cli.py").write_text(
        '"""CLI fixture."""\n', encoding="utf-8"
    )
    (repository / "switchboard_client.py").write_text(
        '"""Client fixture."""\n', encoding="utf-8"
    )
    (repository / "mypy.ini").write_text(
        "[mypy]\npython_version = 3.11\n", encoding="utf-8"
    )
    (repository / "pyproject.toml").write_text(
        "[tool.black]\nline-length = 88\n\n[tool.ruff]\nline-length = 88\n",
        encoding="utf-8",
    )
    requirements = repository / "server" / "requirements.txt"
    requirements.write_text("", encoding="utf-8")
    (repository / "server" / "requirements-dev.txt").write_text(
        "-r requirements.txt\n", encoding="utf-8"
    )
    (repository / "README.md").write_text("first\n", encoding="utf-8")
    _git(repository, "add", ".")
    _git(repository, "commit", "-m", "validation fixture one")
    first = _git(repository, "rev-parse", "HEAD")
    (repository / "README.md").write_text("second\n", encoding="utf-8")
    _git(repository, "commit", "-am", "validation fixture two")
    second = _git(repository, "rev-parse", "HEAD")
    return repository, (first, second), _git(repository, "status", "--porcelain=v1")


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


class _MockGitHubAcceptanceTransport(GitHubTransport):
    """Offline GitHub state and one managed-comment surface."""

    def __init__(self, resolved: ResolvedPullRequest) -> None:
        self.resolved = resolved
        self.comments: list[GitHubComment] = []
        self.create_calls = 0
        self.update_calls = 0

    async def resolve_pull_request(
        self,
        repository_full_name: str,
        pull_request_number: int,
        *,
        require_head: bool = True,
    ) -> ResolvedPullRequest:
        assert repository_full_name == "Nobodyworld/dev-agent-switchboard"
        assert pull_request_number == 125
        assert not require_head or self.resolved.head_sha is not None
        return self.resolved

    async def list_comments(
        self, repository_full_name: str, pull_request_number: int
    ) -> GitHubCommentListing:
        assert repository_full_name == "Nobodyworld/dev-agent-switchboard"
        assert pull_request_number == 125
        return GitHubCommentListing(comments=tuple(self.comments), complete=True)

    async def resolve_authenticated_actor(self) -> GitHubActorIdentity:
        return _GITHUB_ACTOR

    async def get_comment(
        self,
        repository_full_name: str,
        comment_id: int,
    ) -> GitHubComment:
        assert repository_full_name == "Nobodyworld/dev-agent-switchboard"
        for comment in self.comments:
            if comment.comment_id == comment_id:
                return comment
        raise GitHubTransportError("github_comment_not_found")

    async def create_comment(
        self,
        repository_full_name: str,
        pull_request_number: int,
        body: str,
    ) -> GitHubComment:
        assert repository_full_name == "Nobodyworld/dev-agent-switchboard"
        assert pull_request_number == 125
        self.create_calls += 1
        comment = GitHubComment(
            comment_id=900,
            body=body,
            author=_GITHUB_ACTOR,
            repository_full_name=repository_full_name,
            pull_request_number=pull_request_number,
        )
        self.comments.append(comment)
        return comment

    async def update_comment(
        self,
        repository_full_name: str,
        comment_id: int,
        body: str,
    ) -> GitHubComment:
        assert repository_full_name == "Nobodyworld/dev-agent-switchboard"
        self.update_calls += 1
        for index, comment in enumerate(self.comments):
            if comment.comment_id == comment_id:
                updated = GitHubComment(
                    comment_id=comment_id,
                    body=body,
                    author=comment.author,
                    repository_full_name=comment.repository_full_name,
                    pull_request_number=comment.pull_request_number,
                )
                self.comments[index] = updated
                return updated
        raise GitHubAmbiguousWriteError("github_publication_failed")


def _resolved_pull_request(
    head_sha: str,
    *,
    head_repository_full_name: str = "Nobodyworld/dev-agent-switchboard",
    head_repository_id: int = 100,
) -> ResolvedPullRequest:
    return ResolvedPullRequest(
        repository_full_name="Nobodyworld/dev-agent-switchboard",
        repository_id=100,
        repository_node_id="R_acceptance",
        pull_request_number=125,
        pull_request_id=200,
        pull_request_node_id="PR_acceptance",
        state="open",
        draft=False,
        merged=False,
        base_ref="main",
        base_sha="b" * 40,
        head_ref="feature/exact-validation",
        head_sha=head_sha,
        head_repository_full_name=head_repository_full_name,
        head_repository_id=head_repository_id,
    )


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


def _retained_hashes(directory: Path) -> dict[str, str]:
    hashes: dict[str, str] = {}
    for path in directory.rglob("*"):
        if path.is_file():
            hashes[path.relative_to(directory).as_posix()] = hashlib.sha256(
                path.read_bytes()
            ).hexdigest()
    return hashes


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
            evidence_root=tmp_path / "evidence-root",
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

        assert list((tmp_path / "worker-root").glob("run-*")) == []
        run_directory = tmp_path / "evidence-root" / f"run-{run['id']}"
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
            evidence_root=tmp_path / "evidence-root",
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
                EvidenceStore, "write_result", side_effect=OSError("disk")
            ):
                assert worker.poll_once() is True

        runs = _request(
            app, "GET", f"/api/execution/runs?work_order_id={created['id']}"
        )
        assert len(runs) == 1
        run = runs[0]
        assert run["status"] == "failed"
        assert run["terminal_reason"] == "local_result_record_failed"
        assert run["cleanup_status"] == "succeeded"
        assert run["evidence_metadata"]["local_record_status"] == "failed:OSError"
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


def test_validate_switchboard_twice_retains_retrievable_exact_sha_evidence(  # noqa: PLR0915 - complete two-run acceptance proof
    tmp_path: Path,
) -> None:
    canonical, tested_shas, status_before = _validation_repository(tmp_path)
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'evidence-e2e.db'}")
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
        work_order_ids: list[int] = []
        for sha in tested_shas:
            created = _request(
                app,
                "POST",
                "/api/execution/work-orders",
                {
                    "repository_full_name": "Nobodyworld/dev-agent-switchboard",
                    "commit_sha": sha,
                    "manifest": {"name": "validate-switchboard", "version": "1"},
                    "timeout_seconds": 3600,
                },
            )
            work_order_ids.append(created["id"])
            _request(
                app,
                "POST",
                f"/api/execution/work-orders/{created['id']}/approve",
                {},
            )

        config = WorkerConfig(
            base_url="http://switchboard.test",
            worker_id="validation-evidence-worker",
            display_name="Validation evidence worker",
            admin_token=_TOKEN,
            worker_root=tmp_path / "worker-root",
            evidence_root=tmp_path / "evidence-root",
            repositories={"Nobodyworld/dev-agent-switchboard": canonical},
            execution_timeout_seconds=3600,
            heartbeat_interval_seconds=5,
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
            assert worker.poll_once() is True

        manifest = get_trusted_manifest("validate-switchboard", "1")
        assert manifest is not None
        run_ids: list[int] = []
        for work_order_id, tested_sha in zip(work_order_ids, tested_shas, strict=True):
            runs = _request(
                app, "GET", f"/api/execution/runs?work_order_id={work_order_id}"
            )
            assert len(runs) == 1
            run = runs[0]
            run_ids.append(run["id"])
            assert run["status"] == "succeeded", json.dumps(run, indent=2)
            evidence_payload = _request(
                app, "GET", f"/api/execution/runs/{run['id']}/evidence"
            )
            evidence = ExecutionEvidence.model_validate(evidence_payload)
            assert evidence.tested_sha == tested_sha
            assert evidence.manifest_name == "validate-switchboard"
            assert evidence.manifest_version == "1"
            assert evidence.manifest_digest == manifest.digest
            assert evidence.worker_id == config.worker_id
            assert evidence.environment.fingerprint
            assert evidence.source_cleanup_status == "succeeded"
            assert evidence.artifact_finalization_status == "succeeded"
            assert evidence.dependency_lock_status == "succeeded"
            assert evidence.fingerprint == compute_evidence_fingerprint(evidence)
            assert len(evidence.steps) == len(manifest.execution_steps)
            assert len(evidence.artifacts) == len(manifest.artifact_declarations)
            assert any(
                step.parsed_result is not None and step.parsed_result.tests is not None
                for step in evidence.steps
            )
            run_directory = config.evidence_root / f"run-{run['id']}"
            assert (run_directory / "ownership.json").is_file()
            assert (run_directory / "result.json").is_file()
            for artifact in evidence.artifacts:
                retained = run_directory.joinpath(*artifact.relative_path.split("/"))
                content = retained.read_bytes()
                assert len(content) == artifact.size_bytes
                assert hashlib.sha256(content).hexdigest() == artifact.sha256
            serialized = json.dumps(evidence_payload, sort_keys=True)
            assert str(canonical) not in serialized
            assert str(config.evidence_root) not in serialized
            assert "C:\\\\" not in serialized
            assert "/var/" not in serialized
            assert '"argv"' not in serialized
            assert '"stdout"' not in serialized
            assert '"stderr"' not in serialized
            print(f"VALIDATE_SWITCHBOARD_E2E_RUN={run['id']} SHA={tested_sha}")

        assert list(config.worker_root.glob("run-*")) == []
        assert _git(canonical, "status", "--porcelain=v1") == status_before

        async def database_proof() -> tuple[int, int]:
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

        assert asyncio.run(database_proof()) == (0, 0)
        assert len(run_ids) == _EXPECTED_VALIDATION_RUNS

        missing = _AsgiSession(app).request(
            "GET",
            "http://switchboard.test/api/execution/runs/999999/evidence",
            headers={"Authorization": f"Bearer {_TOKEN}"},
        )
        assert missing.status_code == HTTPStatus.NOT_FOUND

        async def replace_persisted_evidence(payload: dict[str, object]) -> None:
            async with sessions() as database:
                persisted = await database.get(ExecutionRun, run_ids[0])
                assert persisted is not None
                persisted.evidence_metadata = payload
                await database.commit()

        asyncio.run(replace_persisted_evidence({}))
        absent = _AsgiSession(app).request(
            "GET",
            f"http://switchboard.test/api/execution/runs/{run_ids[0]}/evidence",
            headers={"Authorization": f"Bearer {_TOKEN}"},
        )
        assert absent.status_code == HTTPStatus.NOT_FOUND
        assert absent.json()["detail"] == "execution_evidence_not_found"

        asyncio.run(replace_persisted_evidence({"schema_version": 1}))
        malformed = _AsgiSession(app).request(
            "GET",
            f"http://switchboard.test/api/execution/runs/{run_ids[0]}/evidence",
            headers={"Authorization": f"Bearer {_TOKEN}"},
        )
        assert malformed.status_code == HTTPStatus.INTERNAL_SERVER_ERROR
        assert malformed.json()["detail"] == "malformed_execution_evidence"
    finally:
        app.dependency_overrides.clear()
        asyncio.run(engine.dispose())


def test_mocked_github_request_executes_exact_local_head_and_publishes_once(  # noqa: PLR0915 - complete issue #122 acceptance proof
    tmp_path: Path,
) -> None:
    canonical, tested_shas, status_before = _validation_repository(tmp_path)
    tested_sha, moved_sha = tested_shas
    absent_fork_sha = "f" * 40
    engine = create_async_engine(
        f"sqlite+aiosqlite:///{tmp_path / 'github-acceptance.db'}"
    )
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    app = create_app(AppConfig(include_ui=False))
    github = _MockGitHubAcceptanceTransport(_resolved_pull_request(tested_sha))

    async def isolated_session() -> AsyncGenerator[AsyncSession, None]:
        async with sessions() as session:
            yield session

    def github_service(session: SessionDependency) -> GitHubAdapterService:
        settings = GitHubSettings(
            api_url="https://api.github.com",
            operator_id="acceptance-operator",
            token=_GITHUB_TEST_TOKEN,
        )
        return GitHubAdapterService(
            dependencies=GitHubAdapterDependencies(
                repository=GitHubAdapterRepository(session),
                execution=build_execution_service(session),
                transport=github,
            ),
            settings=settings,
            clock=utcnow_naive,
        )

    app.dependency_overrides[get_session] = isolated_session
    app.dependency_overrides[get_github_adapter_service] = github_service

    async def prepare() -> None:
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)

    asyncio.run(prepare())
    try:
        request_payload = {
            "repository_full_name": "Nobodyworld/dev-agent-switchboard",
            "pull_request_number": 125,
            "manifest": {"name": "validate-switchboard", "version": "1"},
        }
        created = _request(
            app,
            "POST",
            "/api/execution/github/pull-requests/validate",
            request_payload,
        )
        duplicate = _request(
            app,
            "POST",
            "/api/execution/github/pull-requests/validate",
            request_payload,
        )
        assert duplicate["request_id"] == created["request_id"]
        assert duplicate["work_order_id"] == created["work_order_id"]
        assert created["tested_head_sha"] == tested_sha
        assert created["work_order_status"] == "pending_approval"

        approved = _request(
            app,
            "POST",
            f"/api/execution/work-orders/{created['work_order_id']}/approve",
            {},
        )
        assert approved["status"] == "queued"

        config = WorkerConfig(
            base_url="http://switchboard.test",
            worker_id="github-acceptance-worker",
            display_name="GitHub acceptance worker",
            admin_token=_TOKEN,
            worker_root=tmp_path / "github-worker-root",
            evidence_root=tmp_path / "github-evidence-root",
            repositories={"Nobodyworld/dev-agent-switchboard": canonical},
            execution_timeout_seconds=3600,
            heartbeat_interval_seconds=5,
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
                app,
                "GET",
                f"/api/execution/runs?work_order_id={created['work_order_id']}",
            )
            assert len(runs) == 1
            assert runs[0]["status"] == "succeeded", json.dumps(runs[0], indent=2)
            assert runs[0]["evidence_metadata"]["tested_sha"] == tested_sha

            published = _request(
                app,
                "POST",
                (f"/api/execution/github/requests/{created['request_id']}/publish"),
                {},
            )
            assert published["publication_state"] == "published_current"
            assert published["publication_decision"] == "current"
            assert published["tested_head_sha"] == tested_sha
            assert github.create_calls == 1
            assert github.update_calls == 0
            assert len(github.comments) == 1

            github.resolved = _resolved_pull_request(moved_sha)
            stale = _request(
                app,
                "POST",
                (f"/api/execution/github/requests/{created['request_id']}/publish"),
                {},
            )
            assert stale["publication_state"] == "published_stale"
            assert stale["publication_decision"] == "stale"
            assert stale["tested_head_sha"] == tested_sha
            assert stale["publication_head_sha"] == moved_sha
            assert github.create_calls == 1
            assert github.update_calls == 1
            assert len(github.comments) == 1

            github.resolved = _resolved_pull_request(
                absent_fork_sha,
                head_repository_full_name=("fork-owner/dev-agent-switchboard"),
                head_repository_id=101,
            )
            fork_request = _request(
                app,
                "POST",
                "/api/execution/github/pull-requests/validate",
                request_payload,
            )
            assert fork_request["tested_head_sha"] == absent_fork_sha
            assert fork_request["request_id"] != created["request_id"]
            _request(
                app,
                "POST",
                (f"/api/execution/work-orders/{fork_request['work_order_id']}/approve"),
                {},
            )
            assert worker.poll_once() is True

        fork_runs = _request(
            app,
            "GET",
            (f"/api/execution/runs?work_order_id={fork_request['work_order_id']}"),
        )
        assert len(fork_runs) == 1
        assert fork_runs[0]["status"] == "failed"
        assert fork_runs[0]["terminal_reason"] == "requested_sha_not_available_locally"
        assert fork_runs[0]["evidence_metadata"] is None
        assert absent_fork_sha in fork_runs[0]["result_summary"]
        absent_publication = _AsgiSession(app).request(
            "POST",
            (
                "http://switchboard.test/api/execution/github/requests/"
                f"{fork_request['request_id']}/publish"
            ),
            json={},
            headers={"Authorization": f"Bearer {_TOKEN}"},
        )
        assert absent_publication.status_code == HTTPStatus.CONFLICT
        assert (
            absent_publication.json()["detail"] == "github_terminal_evidence_required"
        )

        comment_body = github.comments[0].body
        serialized_status = json.dumps(stale, sort_keys=True)
        for prohibited in (
            _GITHUB_TEST_TOKEN,
            str(canonical),
            str(config.worker_root),
            str(config.evidence_root),
            '"argv"',
            '"stdout"',
            '"stderr"',
            '"environment"',
            "response_body",
            "artifact_locations",
        ):
            assert prohibited not in comment_body
            assert prohibited not in serialized_status
        assert tested_sha in comment_body
        assert moved_sha not in comment_body
        assert "Head decision: `stale` (`github_head_changed`)" in comment_body
        assert _git(canonical, "status", "--porcelain=v1") == status_before
        assert list(config.worker_root.glob("run-*")) == []
    finally:
        app.dependency_overrides.clear()
        asyncio.run(engine.dispose())


def test_routed_github_validation_executes_then_reuses_real_local_worker(  # noqa: PLR0915 - complete issue #136 worker trust proof
    tmp_path: Path,
) -> None:
    canonical, tested_shas, status_before = _validation_repository(tmp_path)
    tested_sha, moved_sha = tested_shas
    engine = create_async_engine(
        f"sqlite+aiosqlite:///{tmp_path / 'operator-worker-acceptance.db'}"
    )
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    app = create_app(AppConfig(include_ui=False))
    github = _MockGitHubAcceptanceTransport(_resolved_pull_request(tested_sha))

    async def isolated_session() -> AsyncGenerator[AsyncSession, None]:
        async with sessions() as session:
            yield session

    def github_service(session: SessionDependency) -> GitHubAdapterService:
        return GitHubAdapterService(
            dependencies=GitHubAdapterDependencies(
                repository=GitHubAdapterRepository(session),
                execution=build_execution_service(session),
                transport=github,
            ),
            settings=GitHubSettings(
                api_url="https://api.github.com",
                operator_id="operator-worker-acceptance",
                token=_GITHUB_TEST_TOKEN,
            ),
            clock=utcnow_naive,
        )

    app.dependency_overrides[get_session] = isolated_session
    app.dependency_overrides[get_github_adapter_service] = github_service

    async def prepare() -> None:
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)

    asyncio.run(prepare())
    cheap_config = WorkerConfig(
        base_url="http://switchboard.test",
        worker_id="operator-worker-cheap",
        display_name="Operator worker cheap",
        admin_token=_TOKEN,
        worker_root=tmp_path / "operator-cheap-worktrees",
        evidence_root=tmp_path / "operator-cheap-evidence",
        repositories={"Nobodyworld/dev-agent-switchboard": canonical},
        execution_timeout_seconds=3600,
        heartbeat_interval_seconds=5,
    )
    expensive_config = WorkerConfig(
        base_url="http://switchboard.test",
        worker_id="operator-worker-expensive",
        display_name="Operator worker expensive",
        admin_token=_TOKEN,
        worker_root=tmp_path / "operator-expensive-worktrees",
        evidence_root=tmp_path / "operator-expensive-evidence",
        repositories={"Nobodyworld/dev-agent-switchboard": canonical},
        execution_timeout_seconds=3600,
        heartbeat_interval_seconds=5,
    )
    try:
        with (
            ExecutionClient(
                cheap_config.base_url,
                cheap_config.worker_id,
                cheap_config.admin_token,
                session=_AsgiSession(app),  # type: ignore[arg-type]
            ) as cheap_client,
            ExecutionClient(
                expensive_config.base_url,
                expensive_config.worker_id,
                expensive_config.admin_token,
                session=_AsgiSession(app),  # type: ignore[arg-type]
            ) as expensive_client,
        ):
            cheap_worker = LocalWorker(cheap_config, cheap_client)
            expensive_worker = LocalWorker(expensive_config, expensive_client)
            cheap_worker.start()
            expensive_worker.start()
            for worker_id, cost in (
                (cheap_config.worker_id, 3),
                (expensive_config.worker_id, 9),
            ):
                _request(
                    app,
                    "POST",
                    "/api/execution/routing-profiles",
                    {
                        "schema_version": 1,
                        "worker_id": worker_id,
                        "enabled": True,
                        "estimated_cost_units_per_run": cost,
                        "quota_capacity_units": 20,
                        "quota_remaining_units": 20,
                        "quota_reset_at": None,
                        "routing_priority": 0,
                    },
                )
            cheap_client.heartbeat_worker(status="online")
            expensive_client.heartbeat_worker(status="online")
            assert cheap_worker.poll_once() is False
            assert expensive_worker.poll_once() is False

            request_payload = {
                "repository_full_name": "Nobodyworld/dev-agent-switchboard",
                "pull_request_number": 125,
                "manifest": {"name": "validate-switchboard", "version": "1"},
                "routing_policy": "cheapest_capable",
                "reuse_policy": "never",
                "maximum_cost_units": 10,
                "required_quota_units": 2,
            }
            fresh_request = _request(
                app,
                "POST",
                "/api/execution/github/pull-requests/validate",
                request_payload,
            )
            _request(
                app,
                "POST",
                f"/api/execution/work-orders/{fresh_request['work_order_id']}/approve",
                {"queue": True},
            )
            expensive_client.heartbeat_worker(status="online")
            assert expensive_worker.poll_once() is False

            original_runner = worker_module.run_step
            original_verifier = worker_module.verify_reuse_candidate
            with (
                patch.object(
                    worker_module, "run_step", wraps=original_runner
                ) as runner,
                patch.object(
                    worker_module,
                    "verify_reuse_candidate",
                    wraps=original_verifier,
                ) as verifier,
            ):
                cheap_client.heartbeat_worker(status="online")
                assert cheap_worker.poll_once() is True
                manifest = get_trusted_manifest("validate-switchboard", "1")
                assert manifest is not None
                fresh_step_count = len(manifest.execution_steps)
                assert runner.call_count == fresh_step_count
                assert verifier.call_count == 0

                fresh_runs = _request(
                    app,
                    "GET",
                    f"/api/execution/runs?work_order_id={fresh_request['work_order_id']}",
                )
                assert len(fresh_runs) == 1
                fresh_run = fresh_runs[0]
                fresh_evidence = ExecutionEvidence.model_validate(
                    _request(
                        app,
                        "GET",
                        f"/api/execution/runs/{fresh_run['id']}/evidence",
                    )
                )
                assert fresh_run["status"] == "succeeded"
                assert fresh_run["worker_id"] == cheap_config.worker_id
                assert fresh_run["route_provenance"]["estimated_cost_units"] == 3
                assert fresh_run["route_provenance"]["required_quota_units"] == 2
                assert fresh_evidence.tested_sha == tested_sha
                assert fresh_evidence.reuse_provenance.decision == "fresh"
                assert len(fresh_evidence.steps) == fresh_step_count
                assert len(fresh_evidence.artifacts) == len(
                    manifest.artifact_declarations
                )
                fresh_directory = cheap_config.evidence_root / f"run-{fresh_run['id']}"
                assert (fresh_directory / "ownership.json").is_file()
                assert (fresh_directory / "result.json").is_file()
                assert list((fresh_directory / "logs").glob("*.log"))
                for artifact in fresh_evidence.artifacts:
                    retained = fresh_directory.joinpath(
                        *artifact.relative_path.split("/")
                    )
                    assert retained.is_file()
                    assert (
                        hashlib.sha256(retained.read_bytes()).hexdigest()
                        == artifact.sha256
                    )
                source_hashes = _retained_hashes(fresh_directory)
                assert source_hashes

                published_current = _request(
                    app,
                    "POST",
                    f"/api/execution/github/requests/{fresh_request['request_id']}/publish",
                    {},
                )
                assert published_current["publication_state"] == "published_current"
                assert published_current["publication_decision"] == "current"

                reused_request = _request(
                    app,
                    "POST",
                    "/api/execution/github/pull-requests/validate",
                    {**request_payload, "reuse_policy": "allow_exact"},
                )
                assert reused_request["request_id"] != fresh_request["request_id"]
                assert reused_request["work_order_id"] != fresh_request["work_order_id"]
                _request(
                    app,
                    "POST",
                    f"/api/execution/work-orders/{reused_request['work_order_id']}/approve",
                    {"queue": True},
                )
                expensive_client.heartbeat_worker(status="online")
                assert expensive_worker.poll_once() is False
                cheap_client.heartbeat_worker(status="online")
                assert cheap_worker.poll_once() is True
                assert runner.call_count == fresh_step_count
                assert verifier.call_count == 1

            reused_runs = _request(
                app,
                "GET",
                f"/api/execution/runs?work_order_id={reused_request['work_order_id']}",
            )
            assert len(reused_runs) == 1
            reused_run = reused_runs[0]
            reused_evidence = ExecutionEvidence.model_validate(
                _request(
                    app,
                    "GET",
                    f"/api/execution/runs/{reused_run['id']}/evidence",
                )
            )
            assert reused_run["id"] != fresh_run["id"]
            assert reused_run["worker_id"] == cheap_config.worker_id
            assert reused_run["reuse_decision"] == "reused"
            assert reused_run["reused_from_run_id"] == fresh_run["id"]
            assert (
                reused_run["source_evidence_fingerprint"] == fresh_evidence.fingerprint
            )
            assert reused_evidence.steps == []
            assert reused_evidence.artifacts == []
            assert reused_evidence.reuse_provenance.source_run_id == fresh_run["id"]
            assert (
                reused_evidence.reuse_provenance.source_evidence_fingerprint
                == fresh_evidence.fingerprint
            )
            assert _retained_hashes(fresh_directory) == source_hashes
            reused_directory = cheap_config.evidence_root / f"run-{reused_run['id']}"
            assert (reused_directory / "ownership.json").is_file()
            assert (reused_directory / "result.json").is_file()

            github.resolved = _resolved_pull_request(moved_sha)
            published_stale = _request(
                app,
                "POST",
                f"/api/execution/github/requests/{reused_request['request_id']}/publish",
                {},
            )
            assert published_stale["publication_state"] == "published_stale"
            assert published_stale["publication_decision"] == "stale"
            assert published_stale["tested_head_sha"] == tested_sha
            assert published_stale["publication_head_sha"] == moved_sha

            overview = _request(
                app,
                "GET",
                "/api/execution/operator/overview?window_days=1",
            )
            history = _request(
                app,
                "GET",
                "/api/execution/operator/history?limit=25&offset=0",
            )
            assert overview["runs"]["fresh_successful"] == 1
            assert overview["runs"]["reused_successful"] == 1
            assert overview["avoided_work"]["deterministic_executions_avoided"] == 1
            assert overview["avoided_work"]["reference_seconds_avoided"] > 0
            assert overview["avoided_work"]["comparison_units_avoided"] == 3
            assert overview["avoided_work"]["reuse_rate"] == 0.5
            assert overview["publications"] == {"current": 1, "stale": 1}
            assert history["total"] == 2
            history_by_request = {item["request_id"]: item for item in history["items"]}
            assert (
                history_by_request[fresh_request["request_id"]]["reuse_decision"]
                == "fresh"
            )
            assert (
                history_by_request[reused_request["request_id"]]["reuse_decision"]
                == "reused"
            )
            assert (
                history_by_request[reused_request["request_id"]]["reused_from_run_id"]
                == fresh_run["id"]
            )

        async def capacity_proof() -> tuple[int, list[int]]:
            async with sessions() as database:
                leases = await database.scalar(
                    select(func.count()).select_from(ExecutionLease)
                )
                active_counts = (
                    (
                        await database.execute(
                            select(ExecutionWorker.active_run_count).order_by(
                                ExecutionWorker.worker_id
                            )
                        )
                    )
                    .scalars()
                    .all()
                )
            return int(leases or 0), [int(value) for value in active_counts]

        leases, active_counts = asyncio.run(capacity_proof())
        assert leases == 0
        assert active_counts == [0, 0]
        assert list(cheap_config.worker_root.glob("run-*")) == []
        assert list(expensive_config.worker_root.glob("run-*")) == []
        assert _git(canonical, "status", "--porcelain=v1") == status_before
        assert _git(canonical, "rev-parse", "HEAD") == moved_sha
        assert tested_sha != moved_sha
    finally:
        app.dependency_overrides.clear()
        asyncio.run(engine.dispose())
