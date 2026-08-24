"""Focused runtime-capability discovery and reuse-identity coverage."""

from __future__ import annotations

import importlib.metadata
import subprocess
import time
from io import BytesIO
from pathlib import Path
from threading import Event
from types import SimpleNamespace

import pytest

from client.python.execution_worker import (
    capabilities as capabilities_module,
    worker as worker_module,
)
from client.python.execution_worker.capabilities import discover_worker_registration
from client.python.execution_worker.config import WorkerConfig
from client.python.execution_worker.containment import ContainmentOutcome

_TOKEN = "worker-test-token"  # noqa: S105 - non-secret test fixture
_SHORT_TEST_TIMEOUT_SECONDS = 0.2


def _config(tmp_path: Path) -> WorkerConfig:
    return WorkerConfig(
        base_url="http://localhost:8000",
        worker_id="worker-capabilities",
        display_name="Worker capabilities",
        admin_token=_TOKEN,
        worker_root=tmp_path / "worker-root",
        evidence_root=tmp_path / "evidence-root",
        repositories={
            "Nobodyworld/dev-agent-switchboard": tmp_path / "canonical-repository"
        },
    )


class _VersionProcess:
    def __init__(self, output: bytes, *, returncode: int = 0) -> None:
        self.stdout = BytesIO(output)
        self.returncode: int | None = None
        self._configured_returncode = returncode
        self.killed = False

    def kill(self) -> None:
        self.killed = True

    def wait(self, timeout: float | None = None) -> int:
        _ = timeout
        self.returncode = -9 if self.killed else self._configured_returncode
        return self.returncode


class _BlockingStream:
    def __init__(self) -> None:
        self._released = Event()

    def read(self, _size: int) -> bytes:
        self._released.wait()
        return b""

    def release(self) -> None:
        self._released.set()


class _BlockingVersionProcess(_VersionProcess):
    def __init__(self) -> None:
        super().__init__(b"")
        self.stdout = _BlockingStream()

    def kill(self) -> None:
        super().kill()
        self.stdout.release()


def test_discovery_reports_fixed_node_and_pnpm_versions(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        capabilities_module, "strict_containment_supported", lambda: False
    )
    calls: list[tuple[list[str], dict[str, object]]] = []
    processes = [_VersionProcess(b"v24.12.0\n"), _VersionProcess(b"10.18.1\n")]
    tool_paths = {"node": "/fixed/node", "pnpm": "/fixed/pnpm"}

    monkeypatch.setattr(
        capabilities_module.shutil,
        "which",
        tool_paths.get,
    )
    monkeypatch.setattr(capabilities_module.platform, "system", lambda: "Linux")
    monkeypatch.setattr(capabilities_module.platform, "machine", lambda: "x86_64")
    monkeypatch.setattr(
        capabilities_module.platform,
        "python_version",
        lambda: "3.11.9",
    )

    def fake_popen(argv: list[str], **kwargs: object) -> _VersionProcess:
        calls.append((argv, kwargs))
        return processes.pop(0)

    monkeypatch.setattr(capabilities_module.subprocess, "Popen", fake_popen)

    registration = discover_worker_registration(_config(tmp_path))

    assert registration["node_version"] == "24.12.0"
    assert registration["pnpm_version"] == "10.18.1"
    assert registration["capabilities"]["node_available"] is True
    assert registration["capabilities"]["pnpm_available"] is True
    assert [argv for argv, _kwargs in calls] == [
        ["/fixed/node", "--version"],
        ["/fixed/pnpm", "--version"],
    ]
    for _argv, kwargs in calls:
        assert kwargs["shell"] is False
        assert kwargs["stdin"] is subprocess.DEVNULL
        assert kwargs["stdout"] is subprocess.PIPE
        assert kwargs["stderr"] is subprocess.STDOUT
        assert kwargs["env"] == capabilities_module._probe_environment()
        assert kwargs["start_new_session"] is (capabilities_module.os.name != "nt")


def test_capability_probe_omits_worker_and_host_secrets(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        capabilities_module, "strict_containment_supported", lambda: False
    )
    monkeypatch.setenv("PATH", "/safe/path")
    monkeypatch.setenv("SWITCHBOARD_ADMIN_TOKEN", "must-not-reach-probe")
    monkeypatch.setenv("GITHUB_TOKEN", "must-not-reach-probe")
    observed: dict[str, str] = {}
    monkeypatch.setattr(
        capabilities_module.shutil, "which", lambda _name: "/fixed/pnpm"
    )

    def fake_popen(_argv: list[str], **kwargs: object) -> _VersionProcess:
        observed.update(kwargs["env"])  # type: ignore[arg-type]
        return _VersionProcess(b"10.18.1\n")

    monkeypatch.setattr(capabilities_module.subprocess, "Popen", fake_popen)

    assert capabilities_module._pnpm_version() == "10.18.1"
    assert observed["PATH"] == "/safe/path"
    assert set(observed).issubset(capabilities_module._PROBE_ENVIRONMENT_KEYS)
    assert "SWITCHBOARD_ADMIN_TOKEN" not in observed
    assert "GITHUB_TOKEN" not in observed


@pytest.mark.parametrize(
    "output", [b"not-a-version\n", b"token-value\n", b"v10.18.1\n"]
)
def test_pnpm_discovery_rejects_nonsemantic_or_prefixed_output(
    monkeypatch: pytest.MonkeyPatch, output: bytes
) -> None:
    monkeypatch.setattr(
        capabilities_module, "strict_containment_supported", lambda: False
    )
    monkeypatch.setattr(
        capabilities_module.shutil, "which", lambda _name: "/fixed/pnpm"
    )
    monkeypatch.setattr(
        capabilities_module.subprocess,
        "Popen",
        lambda *_args, **_kwargs: _VersionProcess(output),
    )

    assert capabilities_module._pnpm_version() is None


@pytest.mark.parametrize(
    ("path", "returncode"),
    [(None, None), ("/fixed/pnpm", 1)],
)
def test_pnpm_discovery_rejects_missing_and_nonzero_tools(
    monkeypatch: pytest.MonkeyPatch,
    path: str | None,
    returncode: int | None,
) -> None:
    monkeypatch.setattr(
        capabilities_module, "strict_containment_supported", lambda: False
    )
    monkeypatch.setattr(
        capabilities_module.shutil,
        "which",
        lambda _name: path,
    )
    if returncode is not None:
        monkeypatch.setattr(
            capabilities_module.subprocess,
            "Popen",
            lambda *_args, **_kwargs: _VersionProcess(
                b"10.18.1\n", returncode=returncode
            ),
        )

    assert capabilities_module._pnpm_version() is None


def test_pnpm_discovery_bounds_timeout_and_output(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        capabilities_module, "strict_containment_supported", lambda: False
    )
    monkeypatch.setattr(
        capabilities_module.shutil,
        "which",
        lambda _name: "/fixed/pnpm",
    )
    monkeypatch.setattr(capabilities_module, "_VERSION_TIMEOUT_SECONDS", 0.01)
    monkeypatch.setattr(
        capabilities_module,
        "_VERSION_TERMINATION_TIMEOUT_SECONDS",
        0.05,
    )
    blocking = _BlockingVersionProcess()
    monkeypatch.setattr(
        capabilities_module.subprocess,
        "Popen",
        lambda *_args, **_kwargs: blocking,
    )

    started = time.monotonic()
    assert capabilities_module._pnpm_version() is None
    assert time.monotonic() - started < _SHORT_TEST_TIMEOUT_SECONDS
    assert blocking.killed is True

    oversized = _VersionProcess(b"12345")
    monkeypatch.setattr(capabilities_module, "_VERSION_OUTPUT_LIMIT_BYTES", 4)
    monkeypatch.setattr(
        capabilities_module.subprocess,
        "Popen",
        lambda *_args, **_kwargs: oversized,
    )

    assert capabilities_module._pnpm_version() is None
    assert oversized.killed is True


def test_capability_probe_uses_strict_host_with_fixed_argv_and_safe_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("PATH", "/safe/path")
    monkeypatch.setenv("SWITCHBOARD_ADMIN_TOKEN", "must-not-reach-probe")
    observed: dict[str, object] = {}
    process = _VersionProcess(b"10.18.1\n")

    def launch(**kwargs: object) -> object:
        observed.update(kwargs)
        return SimpleNamespace(
            process=process,
            finalize_after_exit=lambda **_kwargs: ContainmentOutcome(
                had_descendants=False, cleanup_verified=True
            ),
        )

    monkeypatch.setattr(
        capabilities_module.shutil, "which", lambda _name: "/fixed/pnpm"
    )
    monkeypatch.setattr(
        capabilities_module, "strict_containment_supported", lambda: True
    )
    monkeypatch.setattr(capabilities_module, "launch_strict_host", launch)

    assert capabilities_module._pnpm_version() == "10.18.1"
    assert observed["argv"] == ("/fixed/pnpm", "--version")
    assert observed["cwd"] == capabilities_module._probe_cwd()
    assert observed["environment"] == capabilities_module._probe_environment()
    assert "SWITCHBOARD_ADMIN_TOKEN" not in observed["environment"]


def test_worker_uses_node_normalization_and_exact_pnpm_requirements(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    registration = {
        "operating_system": "linux",
        "architecture": "x86_64",
        "python_version": "3.11.9",
        "node_version": "24.12.0",
        "pnpm_version": "10.18.1",
        "docker_available": False,
        "browsers": [],
        "gpu_available": False,
        "unity_available": False,
        "desktop_available": False,
        "capabilities": {},
    }
    monkeypatch.setattr(
        worker_module,
        "discover_worker_registration",
        lambda _config: registration,
    )
    requirements = {
        "node": {"minimum": "24.12.0"},
        "pnpm": {"exact": "10.18.1"},
    }

    worker_module._validate_capabilities(requirements, _config(tmp_path))

    registration["pnpm_version"] = "10.18.2"
    with pytest.raises(ValueError, match="pnpm"):
        worker_module._validate_capabilities(requirements, _config(tmp_path))


def test_runtime_requirements_enter_environment_fingerprint(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    versions = {"node_version": "v24.12.0", "pnpm_version": "10.18.1"}
    monkeypatch.setattr(
        worker_module,
        "discover_worker_registration",
        lambda _config: versions,
    )
    monkeypatch.setattr(worker_module.platform, "machine", lambda: "x86_64")
    monkeypatch.setattr(worker_module.platform, "system", lambda: "Linux")
    monkeypatch.setattr(worker_module.platform, "python_version", lambda: "3.11.9")

    def missing_distribution(_name: str) -> str:
        raise importlib.metadata.PackageNotFoundError

    monkeypatch.setattr(
        worker_module.importlib.metadata,
        "version",
        missing_distribution,
    )
    requirements = (
        {"node": {"minimum": "24.12.0"}},
        {"pnpm": {"exact": "10.18.1"}},
    )

    original = worker_module._environment_identity(
        _config(tmp_path), required_capabilities=requirements
    )
    assert [(tool.name, tool.version) for tool in original.tools] == [
        ("node", "24.12.0"),
        ("pnpm", "10.18.1"),
    ]

    versions["pnpm_version"] = "10.18.2"
    changed = worker_module._environment_identity(
        _config(tmp_path), required_capabilities=requirements
    )

    assert changed.fingerprint != original.fingerprint
