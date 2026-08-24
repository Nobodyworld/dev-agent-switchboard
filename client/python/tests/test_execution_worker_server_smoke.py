# ruff: noqa: PLR2004, S603, S607
"""Server-backed, harmless ``worker-smoke@1`` acceptance coverage."""

from __future__ import annotations

import asyncio
import hashlib
import json
import subprocess
import sys
from collections.abc import AsyncGenerator, Callable
from http import HTTPStatus
from pathlib import Path
from unittest.mock import patch
from urllib.parse import urlsplit

import httpx
import pytest
from fastapi import FastAPI
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from client.python.execution_worker import worker as worker_module
from client.python.execution_worker.capabilities import discover_worker_registration
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
from server.execution.enums import RoutingPolicy
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


def _accounting_repository(tmp_path: Path) -> tuple[Path, tuple[str, str], str]:
    """Create a tiny committed repository compatible with the fixed manifest argv."""

    repository = tmp_path / "accounting-canonical"
    subprocess.run(["git", "init", str(repository)], check=True, shell=False)
    _git(repository, "config", "user.email", "worker@example.test")
    _git(repository, "config", "user.name", "Worker Test")
    modules = {
        "ruff": "print('ruff synthetic fixture passed')\n",
        "mypy": "print('mypy synthetic fixture passed')\n",
        "pip": "print('No broken requirements found.')\n",
        "pip_audit": "print('No known vulnerabilities found')\n",
    }
    for name, body in modules.items():
        package = repository / name
        package.mkdir(parents=True)
        (package / "__init__.py").write_text("", encoding="utf-8")
        (package / "__main__.py").write_text(body, encoding="utf-8")
    pytest_package = repository / "pytest"
    pytest_package.mkdir()
    (pytest_package / "__init__.py").write_text("", encoding="utf-8")
    (pytest_package / "__main__.py").write_text(
        """from pathlib import Path
import sys

if any(item.startswith('--cov=') for item in sys.argv):
    Path('coverage.xml').write_text('<coverage line-rate="1"/>', encoding='utf-8')
    Path('coverage.json').write_text(
        '{"totals":{"percent_covered":100}}', encoding='utf-8'
    )
print('1 passed in 0.01s')
print('TOTAL 10 0 100%')
""",
        encoding="utf-8",
    )
    for path in (
        "src/apps/modular_accounting/application",
        "src/apps/api",
        "src/apps/extensions",
        "src/cli",
        "src/tools",
        "tests",
    ):
        directory = repository / path
        directory.mkdir(parents=True, exist_ok=True)
        (directory / "__init__.py").write_text("", encoding="utf-8")
    for module, output in (
        ("coverage_gate", "Aggregate line coverage: 100%"),
        ("critical_coverage", "Critical coverage thresholds passed"),
        ("secret_scan", "No secrets found"),
    ):
        (repository / "src" / "tools" / f"{module}.py").write_text(
            f"print({output!r})\n", encoding="utf-8"
        )
    for test_name in (
        "test_ledger_service.py",
        "test_data_snapshot_service.py",
        "test_modular_accounting_snapshot.py",
        "test_modular_accounting_controls.py",
    ):
        (repository / "tests" / test_name).write_text(
            "def test_fixture() -> None:\n    assert True\n", encoding="utf-8"
        )
    (repository / "config").mkdir()
    (repository / "config" / "critical-coverage.toml").write_text(
        "[coverage]\n", encoding="utf-8"
    )
    for requirement in (
        "requirements.txt",
        "requirements-dev.txt",
        "requirements-container.lock",
    ):
        (repository / requirement).write_text("", encoding="utf-8")
    (repository / "README.md").write_text("fixture one\n", encoding="utf-8")
    _git(repository, "add", ".")
    _git(repository, "commit", "-m", "accounting fixture one")
    first = _git(repository, "rev-parse", "HEAD")
    (repository / "README.md").write_text("fixture two\n", encoding="utf-8")
    _git(repository, "commit", "-am", "accounting fixture two")
    second = _git(repository, "rev-parse", "HEAD")
    return repository, (first, second), _git(repository, "status", "--porcelain=v1")


def _write_fixture_file(repository: Path, relative_path: str, content: str) -> None:
    """Write one committed synthetic repository input with explicit UTF-8 bytes."""

    path = repository.joinpath(*relative_path.split("/"))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _catalog_repository(
    tmp_path: Path,
    *,
    directory_name: str,
    files: dict[str, str],
    moved_input_path: str,
) -> tuple[Path, tuple[str, str], str]:
    """Create a clean two-commit local canonical repository for a catalog profile."""

    repository = tmp_path / directory_name
    subprocess.run(["git", "init", str(repository)], check=True, shell=False)
    _git(repository, "config", "user.email", "worker@example.test")
    _git(repository, "config", "user.name", "Worker Test")
    for relative_path, content in sorted(files.items()):
        _write_fixture_file(repository, relative_path, content)
    _git(repository, "add", ".")
    _git(repository, "commit", "-m", f"{directory_name} fixture one")
    first = _git(repository, "rev-parse", "HEAD")
    _write_fixture_file(
        repository,
        moved_input_path,
        f"{files[moved_input_path]}\n# synthetic result-affecting input change\n",
    )
    _git(repository, "commit", "-am", f"{directory_name} fixture two")
    second = _git(repository, "rev-parse", "HEAD")
    return repository, (first, second), _git(repository, "status", "--porcelain=v1")


def _zscripts_repository(tmp_path: Path) -> tuple[Path, tuple[str, str], str]:
    """Build a no-network Zscripts fixture compatible with ``quality-gate``."""

    quality_gate = """from __future__ import annotations

import json
import sys
from pathlib import Path

OPERATIONS = (
    "format-check",
    "lint",
    "type",
    "frontend-install",
    "frontend-format",
    "frontend-lint",
    "frontend-typecheck",
    "frontend-tests",
    "frontend-build",
    "repository-safety",
    "snapshot-store",
    "workspace-api",
    "packaged-workspace",
    "helper-surface",
    "helper-boundary",
    "helper-compatibility",
    "bandit",
    "audit",
    "binary",
    "tests",
    "coverage",
    "docs",
    "editable-smoke",
    "wheel",
    "zipapp",
    "diagnostics",
)

if sys.argv[1:] != ["quality"]:
    raise SystemExit(2)

reports = Path("reports")
reports.mkdir(exist_ok=True)
summary = {
    "profile": "quality",
    "status": "passed",
    "coverage_threshold": 85,
    "operations": [
        {
            "operation": operation,
            "status": "passed",
            "duration_seconds": 0,
            "details": (
                {"coverage_percent": 100, "coverage_threshold": 85}
                if operation == "coverage"
                else {}
            ),
        }
        for operation in OPERATIONS
    ],
    "duration_seconds": 0,
}
(reports / "quality-summary.json").write_text(
    json.dumps(summary, sort_keys=True), encoding="utf-8"
)
(reports / "coverage.json").write_text(
    json.dumps({"totals": {"percent_covered": 100}}), encoding="utf-8"
)
(reports / "diagnostics.json").write_text(
    json.dumps({"telemetry": {"status": "inactive"}}), encoding="utf-8"
)
print("quality gate synthetic fixture passed")
"""
    return _catalog_repository(
        tmp_path,
        directory_name="zscripts-canonical",
        files={
            ".github/workflows/ci.yml": "name: synthetic\n",
            "README.md": "fixture first head\n",
            "pyproject.toml": "[project]\nname = 'synthetic-zscripts'\n",
            "scripts/quality_gate.py": quality_gate,
            "workspace-ui/package.json": '{"name":"synthetic-workspace"}\n',
            "workspace-ui/pnpm-lock.yaml": "lockfileVersion: '9.0'\n",
        },
        moved_input_path="scripts/quality_gate.py",
    )


def _industry_repository(tmp_path: Path) -> tuple[Path, tuple[str, str], str]:
    """Build a no-network Industry fixture compatible with all ten fixed steps."""

    pytest_main = """from __future__ import annotations

import json
import sys
from pathlib import Path

xml_path = None
json_path = None
for argument in sys.argv[1:]:
    if argument.startswith("--cov-report=xml:"):
        xml_path = Path(argument.split(":", 1)[1])
    if argument.startswith("--cov-report=json:"):
        json_path = Path(argument.split(":", 1)[1])
if xml_path is None or json_path is None:
    raise SystemExit(2)
xml_path.parent.mkdir(parents=True, exist_ok=True)
xml_path.write_text('<coverage line-rate="1"/>', encoding="utf-8")
json_path.write_text(
    json.dumps({"totals": {"percent_covered": 100}}), encoding="utf-8"
)
print("2 passed in 0.01s")
print("TOTAL 10 0 100%")
"""
    pip_audit_main = """from __future__ import annotations

import json
from pathlib import Path

report = Path("build/reports/pip-audit.json")
report.parent.mkdir(parents=True, exist_ok=True)
report.write_text(json.dumps({"dependencies": []}), encoding="utf-8")
print("No known vulnerabilities found")
"""
    return _catalog_repository(
        tmp_path,
        directory_name="industry-canonical",
        files={
            ".github/workflows/ci.yml": "name: synthetic\n",
            "Makefile": "all:\n\t@true\n",
            "README.md": "fixture first head\n",
            "app.py": "def app() -> str:\n    return 'synthetic'\n",
            "black/__init__.py": "",
            "black/__main__.py": "print('black synthetic fixture passed')\n",
            "config/.secrets.baseline": "{}\n",
            "detect_secrets/__init__.py": "",
            "detect_secrets/pre_commit_hook.py": (
                "print('detect-secrets baseline validation passed')\n"
            ),
            "mypy/__init__.py": "",
            "mypy/__main__.py": "print('mypy synthetic fixture passed')\n",
            "pip/__init__.py": "",
            "pip/__main__.py": "print('No broken requirements found.')\n",
            "pip_audit/__init__.py": "",
            "pip_audit/__main__.py": pip_audit_main,
            "pytest/__init__.py": "",
            "pytest/__main__.py": pytest_main,
            "requirements-dev.txt": "-r requirements.txt\n",
            "requirements.txt": "",
            "ruff/__init__.py": "",
            "ruff/__main__.py": "print('ruff synthetic fixture passed')\n",
            "src/adapters/__init__.py": "",
            "src/agents/__init__.py": "",
            "src/application/__init__.py": "",
            "src/core/__init__.py": "",
            "src/extensions/__init__.py": "",
            "src/infrastructure/__init__.py": "",
            "src/interfaces/__init__.py": "",
            "src/interfaces/api/__init__.py": "",
            "src/interfaces/streamlit/__init__.py": "",
            "src/scripts/benchmark_metrics.py": (
                "from __future__ import annotations\n"
                "import sys\n"
                "if sys.argv[1:] != ['--check']:\n    raise SystemExit(2)\n"
                "print('benchmark metrics passed')\n"
            ),
            "tests/__init__.py": "",
        },
        moved_input_path="requirements.txt",
    )


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
        assert repository_full_name == self.resolved.repository_full_name
        assert pull_request_number == self.resolved.pull_request_number
        assert not require_head or self.resolved.head_sha is not None
        return self.resolved

    async def list_comments(
        self, repository_full_name: str, pull_request_number: int
    ) -> GitHubCommentListing:
        assert repository_full_name == self.resolved.repository_full_name
        assert pull_request_number == self.resolved.pull_request_number
        return GitHubCommentListing(comments=tuple(self.comments), complete=True)

    async def resolve_authenticated_actor(self) -> GitHubActorIdentity:
        return _GITHUB_ACTOR

    async def get_comment(
        self,
        repository_full_name: str,
        comment_id: int,
    ) -> GitHubComment:
        assert repository_full_name == self.resolved.repository_full_name
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
        assert repository_full_name == self.resolved.repository_full_name
        assert pull_request_number == self.resolved.pull_request_number
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
        assert repository_full_name == self.resolved.repository_full_name
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
    repository_full_name: str = "Nobodyworld/dev-agent-switchboard",
    pull_request_number: int = 125,
) -> ResolvedPullRequest:
    return ResolvedPullRequest(
        repository_full_name=repository_full_name,
        repository_id=100,
        repository_node_id="R_acceptance",
        pull_request_number=pull_request_number,
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


def _run_catalog_profile_acceptance(  # noqa: PLR0913, PLR0915 - acceptance inputs and boundaries are explicit
    tmp_path: Path,
    *,
    repository_factory: Callable[[Path], tuple[Path, tuple[str, str], str]],
    repository_name: str,
    manifest_name: str,
    pull_request_number: int,
    expected_step_count: int,
    expected_artifact_paths: set[str],
    mismatch_versions: dict[str, str],
    expected_mismatch_reasons: set[str],
    expected_parsers: dict[str, str],
) -> None:
    """Exercise an immutable catalog profile through the real local worker path."""

    canonical, tested_shas, status_before = repository_factory(tmp_path)
    tested_sha, moved_sha = tested_shas
    database_path = tmp_path / f"{manifest_name}-worker-acceptance.db"
    engine = create_async_engine(f"sqlite+aiosqlite:///{database_path}")
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    app = create_app(AppConfig(include_ui=False))
    github = _MockGitHubAcceptanceTransport(
        _resolved_pull_request(
            tested_sha,
            repository_full_name=repository_name,
            head_repository_full_name=repository_name,
            pull_request_number=pull_request_number,
        )
    )

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
                operator_id=f"{manifest_name}-worker-acceptance",
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
    mapped_config = WorkerConfig(
        base_url="http://switchboard.test",
        worker_id=f"{manifest_name}-mapped-worker",
        display_name=f"{manifest_name} mapped worker",
        admin_token=_TOKEN,
        worker_root=tmp_path / f"{manifest_name}-mapped-worktrees",
        evidence_root=tmp_path / f"{manifest_name}-mapped-evidence",
        repositories={repository_name: canonical},
        execution_timeout_seconds=14_400,
        output_summary_limit=16_384,
        heartbeat_interval_seconds=5,
    )
    unmapped_config = WorkerConfig(
        base_url="http://switchboard.test",
        worker_id=f"{manifest_name}-unmapped-worker",
        display_name=f"{manifest_name} unmapped worker",
        admin_token=_TOKEN,
        worker_root=tmp_path / f"{manifest_name}-unmapped-worktrees",
        evidence_root=tmp_path / f"{manifest_name}-unmapped-evidence",
        repositories={"Nobodyworld/dev-agent-switchboard": canonical},
        execution_timeout_seconds=14_400,
        output_summary_limit=16_384,
        heartbeat_interval_seconds=5,
    )
    mismatch_config = WorkerConfig(
        base_url="http://switchboard.test",
        worker_id=f"{manifest_name}-mismatch-worker",
        display_name=f"{manifest_name} mismatched worker",
        admin_token=_TOKEN,
        worker_root=tmp_path / f"{manifest_name}-mismatch-worktrees",
        evidence_root=tmp_path / f"{manifest_name}-mismatch-evidence",
        repositories={repository_name: canonical},
        execution_timeout_seconds=14_400,
        output_summary_limit=16_384,
        heartbeat_interval_seconds=5,
    )
    try:
        with (
            ExecutionClient(
                mapped_config.base_url,
                mapped_config.worker_id,
                mapped_config.admin_token,
                session=_AsgiSession(app),  # type: ignore[arg-type]
            ) as mapped_client,
            ExecutionClient(
                unmapped_config.base_url,
                unmapped_config.worker_id,
                unmapped_config.admin_token,
                session=_AsgiSession(app),  # type: ignore[arg-type]
            ) as unmapped_client,
            ExecutionClient(
                mismatch_config.base_url,
                mismatch_config.worker_id,
                mismatch_config.admin_token,
                session=_AsgiSession(app),  # type: ignore[arg-type]
            ) as mismatch_client,
        ):
            mapped_worker = LocalWorker(mapped_config, mapped_client)
            unmapped_worker = LocalWorker(unmapped_config, unmapped_client)
            mismatch_worker = LocalWorker(mismatch_config, mismatch_client)
            mapped_worker.start()
            unmapped_worker.start()
            mismatch_registration = discover_worker_registration(mismatch_config)
            mismatch_registration.update(mismatch_versions)
            mismatch_client.register_worker(mismatch_registration)
            for client, worker in (
                (mapped_client, mapped_worker),
                (unmapped_client, unmapped_worker),
                (mismatch_client, mismatch_worker),
            ):
                client.heartbeat_worker(status="online")
                assert worker.poll_once() is False

            readiness = _request(
                app,
                "GET",
                f"/api/execution/catalog/{repository_name}/readiness",
            )
            readiness_by_worker = {
                item["worker_id"]: item for item in readiness["workers"]
            }
            assert (
                readiness_by_worker[unmapped_config.worker_id]["readiness_reason"]
                == "repository_unavailable"
            )
            assert (
                readiness_by_worker[mismatch_config.worker_id]["readiness_reason"]
                == "manifest_capability_mismatch"
            )

            async def mismatch_assessment() -> dict[str, tuple[str, ...]]:
                async with sessions() as session:
                    service = build_execution_service(session)
                    evaluations, _selected = await service.assess_repository_readiness(
                        repository_full_name=repository_name,
                        manifest_name=manifest_name,
                        manifest_version="1",
                        routing_policy=RoutingPolicy.FIRST_AVAILABLE,
                        maximum_cost_units=None,
                        required_quota_units=0,
                        preferred_executor=None,
                    )
                    return {item.worker.worker_id: item.reasons for item in evaluations}

            mismatch_reasons = asyncio.run(mismatch_assessment())
            assert (
                "worker_repository_unavailable"
                in mismatch_reasons[unmapped_config.worker_id]
            )
            assert expected_mismatch_reasons.issubset(
                set(mismatch_reasons[mismatch_config.worker_id])
            )

            request_payload = {
                "repository_full_name": repository_name,
                "pull_request_number": pull_request_number,
                "manifest": {"name": manifest_name, "version": "1"},
                "routing_policy": "first_available",
                "reuse_policy": "never",
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
                mismatch_client.heartbeat_worker(status="online")
                assert mismatch_worker.poll_once() is False
                unmapped_client.heartbeat_worker(status="online")
                assert unmapped_worker.poll_once() is False
                mapped_client.heartbeat_worker(status="online")
                assert mapped_worker.poll_once() is True
                manifest = get_trusted_manifest(manifest_name, "1")
                assert manifest is not None
                assert len(manifest.execution_steps) == expected_step_count
                assert runner.call_count == expected_step_count
                assert verifier.call_count == 0

                fresh_run = _request(
                    app,
                    "GET",
                    f"/api/execution/runs?work_order_id={fresh_request['work_order_id']}",
                )[0]
                fresh_evidence = ExecutionEvidence.model_validate(
                    _request(
                        app,
                        "GET",
                        f"/api/execution/runs/{fresh_run['id']}/evidence",
                    )
                )
                assert fresh_run["status"] == "succeeded", {
                    "cleanup_status": fresh_run["cleanup_status"],
                    "result_summary": fresh_run["result_summary"],
                    "terminal_reason": fresh_run["terminal_reason"],
                }
                assert fresh_run["worker_id"] == mapped_config.worker_id
                assert fresh_run["route_provenance"]["selected_worker_id"] == (
                    mapped_config.worker_id
                )
                assert fresh_run["route_provenance"]["routing_policy"] == (
                    "first_available"
                )
                assert fresh_evidence.tested_sha == tested_sha
                assert fresh_evidence.reuse_provenance.decision == "fresh"
                assert len(fresh_evidence.steps) == expected_step_count
                assert all(item.status == "succeeded" for item in fresh_evidence.steps)
                parsed_by_step = {
                    item.step_id: item.parsed_result for item in fresh_evidence.steps
                }
                for step_id, parser in expected_parsers.items():
                    parsed = parsed_by_step[step_id]
                    assert parsed is not None
                    assert parsed.status == "parsed"
                    assert parsed.parser == parser
                assert {item.relative_path for item in fresh_evidence.artifacts} == (
                    expected_artifact_paths
                )
                fresh_directory = mapped_config.evidence_root / f"run-{fresh_run['id']}"
                assert (fresh_directory / "ownership.json").is_file()
                assert (fresh_directory / "result.json").is_file()
                assert list((fresh_directory / "logs").glob("*.log"))
                for artifact in fresh_evidence.artifacts:
                    retained = fresh_directory.joinpath(
                        *artifact.relative_path.split("/")
                    )
                    assert retained.is_file()
                    assert 0 < artifact.size_bytes <= 16 * 1024 * 1024
                    assert hashlib.sha256(retained.read_bytes()).hexdigest() == (
                        artifact.sha256
                    )
                source_hashes = _retained_hashes(fresh_directory)
                assert source_hashes
                assert github.comments == []
                assert github.create_calls == 0
                assert github.update_calls == 0

                reused_request = _request(
                    app,
                    "POST",
                    "/api/execution/github/pull-requests/validate",
                    {**request_payload, "reuse_policy": "allow_exact"},
                )
                _request(
                    app,
                    "POST",
                    f"/api/execution/work-orders/{reused_request['work_order_id']}/approve",
                    {"queue": True},
                )
                mismatch_client.heartbeat_worker(status="online")
                assert mismatch_worker.poll_once() is False
                unmapped_client.heartbeat_worker(status="online")
                assert unmapped_worker.poll_once() is False
                mapped_client.heartbeat_worker(status="online")
                assert mapped_worker.poll_once() is True
                assert runner.call_count == expected_step_count
                assert verifier.call_count == 1

            reused_run = _request(
                app,
                "GET",
                f"/api/execution/runs?work_order_id={reused_request['work_order_id']}",
            )[0]
            reused_evidence = ExecutionEvidence.model_validate(
                _request(
                    app,
                    "GET",
                    f"/api/execution/runs/{reused_run['id']}/evidence",
                )
            )
            assert reused_run["status"] == "succeeded"
            assert reused_run["worker_id"] == mapped_config.worker_id
            assert reused_run["route_provenance"]["selected_worker_id"] == (
                mapped_config.worker_id
            )
            assert reused_run["reuse_decision"] == "reused"
            assert reused_run["reused_from_run_id"] == fresh_run["id"]
            assert reused_run["source_evidence_fingerprint"] == (
                fresh_evidence.fingerprint
            )
            assert reused_evidence.steps == []
            assert reused_evidence.artifacts == []
            assert reused_evidence.reuse_provenance.decision == "reused"
            assert reused_evidence.reuse_provenance.source_run_id == fresh_run["id"]
            assert (
                reused_evidence.reuse_provenance.source_evidence_fingerprint
                == fresh_evidence.fingerprint
            )
            assert _retained_hashes(fresh_directory) == source_hashes
            assert github.comments == []
            assert github.create_calls == 0
            assert github.update_calls == 0

            github.resolved = _resolved_pull_request(
                moved_sha,
                repository_full_name=repository_name,
                head_repository_full_name=repository_name,
                pull_request_number=pull_request_number,
            )
            moved_request = _request(
                app,
                "POST",
                "/api/execution/github/pull-requests/validate",
                {**request_payload, "reuse_policy": "allow_exact"},
            )
            assert moved_request["work_order_id"] != reused_request["work_order_id"]
            _request(
                app,
                "POST",
                f"/api/execution/work-orders/{moved_request['work_order_id']}/approve",
                {"queue": True},
            )
            with (
                patch.object(
                    worker_module, "run_step", wraps=original_runner
                ) as moved_runner,
                patch.object(
                    worker_module,
                    "verify_reuse_candidate",
                    wraps=original_verifier,
                ) as moved_verifier,
            ):
                mapped_client.heartbeat_worker(status="online")
                assert mapped_worker.poll_once() is True
                assert moved_runner.call_count == expected_step_count
                assert moved_verifier.call_count == 0
            moved_run = _request(
                app,
                "GET",
                f"/api/execution/runs?work_order_id={moved_request['work_order_id']}",
            )[0]
            moved_evidence = ExecutionEvidence.model_validate(
                _request(
                    app,
                    "GET",
                    f"/api/execution/runs/{moved_run['id']}/evidence",
                )
            )
            assert moved_run["status"] == "succeeded"
            assert moved_run["reuse_decision"] == "fresh"
            assert moved_run["reused_from_run_id"] is None
            assert moved_evidence.tested_sha == moved_sha
            assert (
                moved_evidence.dependency_lock_hashes
                != fresh_evidence.dependency_lock_hashes
            )
            assert len(moved_evidence.steps) == expected_step_count
            assert github.comments == []
            assert github.create_calls == 0
            assert github.update_calls == 0

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
        assert active_counts == [0, 0, 0]
        assert list(mapped_config.worker_root.glob("run-*")) == []
        assert list(unmapped_config.worker_root.glob("run-*")) == []
        assert list(mismatch_config.worker_root.glob("run-*")) == []
        assert _git(canonical, "status", "--porcelain=v1") == status_before
        assert _git(canonical, "rev-parse", "HEAD") == moved_sha
        assert tested_sha != moved_sha
    finally:
        app.dependency_overrides.clear()
        asyncio.run(engine.dispose())


def test_zscripts_catalog_routes_real_worker_then_reuses_exact_evidence(
    tmp_path: Path,
) -> None:
    _run_catalog_profile_acceptance(
        tmp_path,
        repository_factory=_zscripts_repository,
        repository_name="Nobodyworld/dev-logger-zscripts",
        manifest_name="validate-zscripts",
        pull_request_number=143,
        expected_step_count=1,
        expected_artifact_paths={
            "reports/quality-summary.json",
            "reports/coverage.json",
            "reports/diagnostics.json",
        },
        mismatch_versions={"node_version": "v0.0.0", "pnpm_version": "0.0.0"},
        expected_mismatch_reasons={
            "node_version_too_old_or_missing",
            "pnpm_version_mismatch_or_missing",
        },
        expected_parsers={"quality-gate": "quality-summary-v1"},
    )


@pytest.mark.skipif(
    sys.version_info < (3, 13),
    reason="trusted Industry Resilience acceptance requires Python 3.13+",
)
def test_industry_resilience_catalog_routes_real_worker_then_reuses_exact_evidence(
    tmp_path: Path,
) -> None:
    _run_catalog_profile_acceptance(
        tmp_path,
        repository_factory=_industry_repository,
        repository_name="Nobodyworld/app-industry-resilience",
        manifest_name="validate-industry-resilience",
        pull_request_number=130,
        expected_step_count=10,
        expected_artifact_paths={
            "build/reports/runtime-coverage.xml",
            "build/reports/runtime-coverage.json",
            "build/reports/full-src-coverage.xml",
            "build/reports/full-src-coverage.json",
            "build/reports/pip-audit.json",
        },
        mismatch_versions={"python_version": "0.0.0"},
        expected_mismatch_reasons={"python_version_too_old_or_missing"},
        expected_parsers={
            "dependency-health": "dependency-health",
            "runtime-coverage": "pytest-coverage",
            "full-src-coverage": "pytest-coverage",
            "dependency-audit": "dependency-audit",
            "secret-scan": "secret-scan",
        },
    )


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
                assert fresh_run["status"] == "succeeded", {
                    "result_summary": fresh_run["result_summary"],
                    "terminal_reason": fresh_run["terminal_reason"],
                    "cleanup_status": fresh_run["cleanup_status"],
                    "steps": [
                        (item.step_id, item.status, item.summary)
                        for item in fresh_evidence.steps
                    ],
                }
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


@pytest.mark.skipif(
    sys.version_info < (3, 12),
    reason="trusted accounting acceptance requires the workload's Python 3.12+ runtime",
)
def test_accounting_catalog_routes_real_worker_then_reuses_exact_evidence(  # noqa: PLR0915 - complete issue #138 production-path proof
    tmp_path: Path,
) -> None:
    repository_name = "Nobodyworld/app-accounting-modular"
    canonical, tested_shas, status_before = _accounting_repository(tmp_path)
    tested_sha, moved_sha = tested_shas
    engine = create_async_engine(
        f"sqlite+aiosqlite:///{tmp_path / 'accounting-worker-acceptance.db'}"
    )
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    app = create_app(AppConfig(include_ui=False))
    github = _MockGitHubAcceptanceTransport(
        _resolved_pull_request(
            tested_sha,
            repository_full_name=repository_name,
            head_repository_full_name=repository_name,
            pull_request_number=126,
        )
    )

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
                operator_id="accounting-worker-acceptance",
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
    mapped_config = WorkerConfig(
        base_url="http://switchboard.test",
        worker_id="accounting-mapped-worker",
        display_name="Accounting mapped worker",
        admin_token=_TOKEN,
        worker_root=tmp_path / "accounting-mapped-worktrees",
        evidence_root=tmp_path / "accounting-mapped-evidence",
        repositories={repository_name: canonical},
        execution_timeout_seconds=5400,
        heartbeat_interval_seconds=5,
    )
    unmapped_config = WorkerConfig(
        base_url="http://switchboard.test",
        worker_id="accounting-unmapped-worker",
        display_name="Accounting unmapped worker",
        admin_token=_TOKEN,
        worker_root=tmp_path / "accounting-unmapped-worktrees",
        evidence_root=tmp_path / "accounting-unmapped-evidence",
        repositories={"Nobodyworld/dev-agent-switchboard": canonical},
        execution_timeout_seconds=5400,
        heartbeat_interval_seconds=5,
    )
    try:
        with (
            ExecutionClient(
                mapped_config.base_url,
                mapped_config.worker_id,
                mapped_config.admin_token,
                session=_AsgiSession(app),  # type: ignore[arg-type]
            ) as mapped_client,
            ExecutionClient(
                unmapped_config.base_url,
                unmapped_config.worker_id,
                unmapped_config.admin_token,
                session=_AsgiSession(app),  # type: ignore[arg-type]
            ) as unmapped_client,
        ):
            mapped_worker = LocalWorker(mapped_config, mapped_client)
            unmapped_worker = LocalWorker(unmapped_config, unmapped_client)
            mapped_worker.start()
            unmapped_worker.start()
            for worker_id, cost in (
                (unmapped_config.worker_id, 1),
                (mapped_config.worker_id, 5),
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
            mapped_client.heartbeat_worker(status="online")
            unmapped_client.heartbeat_worker(status="online")
            assert mapped_worker.poll_once() is False
            assert unmapped_worker.poll_once() is False

            request_payload = {
                "repository_full_name": repository_name,
                "pull_request_number": 126,
                "manifest": {
                    "name": "validate-accounting-modular",
                    "version": "1",
                },
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
            unmapped_client.heartbeat_worker(status="online")
            assert unmapped_worker.poll_once() is False

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
                mapped_client.heartbeat_worker(status="online")
                assert mapped_worker.poll_once() is True
                manifest = get_trusted_manifest("validate-accounting-modular", "1")
                assert manifest is not None
                assert runner.call_count == len(manifest.execution_steps) == 11
                assert verifier.call_count == 0

                fresh_run = _request(
                    app,
                    "GET",
                    f"/api/execution/runs?work_order_id={fresh_request['work_order_id']}",
                )[0]
                fresh_evidence = ExecutionEvidence.model_validate(
                    _request(
                        app,
                        "GET",
                        f"/api/execution/runs/{fresh_run['id']}/evidence",
                    )
                )
                assert fresh_run["status"] == "succeeded", {
                    "result_summary": fresh_run["result_summary"],
                    "terminal_reason": fresh_run["terminal_reason"],
                    "cleanup_status": fresh_run["cleanup_status"],
                    "steps": [
                        (item.step_id, item.status, item.summary)
                        for item in fresh_evidence.steps
                    ],
                }
                assert fresh_run["worker_id"] == mapped_config.worker_id
                assert fresh_evidence.tested_sha == tested_sha
                assert len(fresh_evidence.steps) == 11
                assert {
                    item.relative_path for item in fresh_evidence.artifacts
                }.issuperset({"coverage.xml", "coverage.json"})
                fresh_directory = mapped_config.evidence_root / f"run-{fresh_run['id']}"
                assert (fresh_directory / "ownership.json").is_file()
                assert (fresh_directory / "result.json").is_file()
                assert list((fresh_directory / "logs").glob("*.log"))
                assert (fresh_directory / "coverage.xml").is_file()
                assert (fresh_directory / "coverage.json").is_file()
                source_hashes = _retained_hashes(fresh_directory)
                assert github.comments == []

                published_current = _request(
                    app,
                    "POST",
                    f"/api/execution/github/requests/{fresh_request['request_id']}/publish",
                    {},
                )
                assert published_current["publication_decision"] == "current"
                assert len(github.comments) == 1

                reused_request = _request(
                    app,
                    "POST",
                    "/api/execution/github/pull-requests/validate",
                    {**request_payload, "reuse_policy": "allow_exact"},
                )
                _request(
                    app,
                    "POST",
                    f"/api/execution/work-orders/{reused_request['work_order_id']}/approve",
                    {"queue": True},
                )
                unmapped_client.heartbeat_worker(status="online")
                assert unmapped_worker.poll_once() is False
                mapped_client.heartbeat_worker(status="online")
                assert mapped_worker.poll_once() is True
                assert runner.call_count == 11
                assert verifier.call_count == 1

            reused_run = _request(
                app,
                "GET",
                f"/api/execution/runs?work_order_id={reused_request['work_order_id']}",
            )[0]
            reused_evidence = ExecutionEvidence.model_validate(
                _request(
                    app,
                    "GET",
                    f"/api/execution/runs/{reused_run['id']}/evidence",
                )
            )
            assert reused_run["id"] != fresh_run["id"]
            assert reused_run["reuse_decision"] == "reused"
            assert reused_run["reused_from_run_id"] == fresh_run["id"]
            assert (
                reused_run["source_evidence_fingerprint"] == fresh_evidence.fingerprint
            )
            assert reused_evidence.steps == []
            assert reused_evidence.artifacts == []
            assert _retained_hashes(fresh_directory) == source_hashes

            github.resolved = _resolved_pull_request(
                moved_sha,
                repository_full_name=repository_name,
                head_repository_full_name=repository_name,
                pull_request_number=126,
            )
            published_stale = _request(
                app,
                "POST",
                f"/api/execution/github/requests/{reused_request['request_id']}/publish",
                {},
            )
            assert published_stale["publication_decision"] == "stale"
            assert published_stale["tested_head_sha"] == tested_sha
            assert published_stale["publication_head_sha"] == moved_sha
            assert len(github.comments) == 2

            overview = _request(
                app, "GET", "/api/execution/operator/overview?window_days=1"
            )
            history = _request(
                app, "GET", "/api/execution/operator/history?limit=25&offset=0"
            )
            assert overview["runs"]["fresh_successful"] == 1
            assert overview["runs"]["reused_successful"] == 1
            assert overview["avoided_work"]["deterministic_executions_avoided"] == 1
            assert overview["avoided_work"]["reuse_rate"] == 0.5
            assert overview["publications"] == {"current": 1, "stale": 1}
            assert history["total"] == 2

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
        assert list(mapped_config.worker_root.glob("run-*")) == []
        assert list(unmapped_config.worker_root.glob("run-*")) == []
        assert _git(canonical, "status", "--porcelain=v1") == status_before
        assert _git(canonical, "rev-parse", "HEAD") == moved_sha
        print(
            "accounting_acceptance="
            + json.dumps(
                {
                    "fresh_run_id": fresh_run["id"],
                    "fresh_step_count": len(fresh_evidence.steps),
                    "reused_run_id": reused_run["id"],
                    "reused_step_count": len(reused_evidence.steps),
                    "source_evidence_fingerprint": fresh_evidence.fingerprint,
                    "publication_decisions": [
                        published_current["publication_decision"],
                        published_stale["publication_decision"],
                    ],
                    "history_total": history["total"],
                    "reuse_rate": overview["avoided_work"]["reuse_rate"],
                    "canonical_clean": True,
                },
                sort_keys=True,
            )
        )
    finally:
        app.dependency_overrides.clear()
        asyncio.run(engine.dispose())
