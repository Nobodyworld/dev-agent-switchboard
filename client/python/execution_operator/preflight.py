"""Read-only exact-source and host preflight for the operator lifecycle."""

from __future__ import annotations

import hashlib
import os
import platform
import shutil
import socket
import stat
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

from client.python.execution_worker.containment import strict_containment_supported
from server.execution.capabilities import runtime_version_matches
from server.execution.registry import get_trusted_manifest

from .config import OperatorLifecycleConfig
from .models import OperatorLifecycleFailure

_COMMAND_TIMEOUT = 10.0
_OUTPUT_LIMIT = 64 * 1024
_VERSION_OUTPUT_LIMIT = 256
_MAX_WINDOWS_RUNTIME_ROOT_LENGTH = 80
PREFLIGHT_CHECKS = (
    "canonical_repository",
    "clean_source",
    "target_commit",
    "source_snapshot",
    "manifest_contract",
    "python_runtime",
    "git_runtime",
    "worker_capabilities",
    "root_safety",
    "loopback_port",
    "process_token",
    "report_policy",
)
_SUPPORTED_CAPABILITY_KEYS = frozenset(
    {
        "architecture",
        "git_available",
        "node",
        "operating_system",
        "pnpm",
        "python",
        "repository_write",
    }
)


@dataclass(frozen=True, slots=True)
class SourceSnapshot:
    head_sha: str
    tree_sha: str
    status_digest: str


@dataclass(frozen=True, slots=True)
class PreflightResult:
    source: SourceSnapshot
    manifest_digest: str
    manifest_steps: tuple[tuple[str, bool], ...]
    token_present: bool

    @property
    def manifest_step_count(self) -> int:
        return len(self.manifest_steps)


def _run_git(checkout: Path, arguments: tuple[str, ...]) -> bytes:
    executable = shutil.which("git", path=os.environ.get("PATH"))
    if executable is None:
        raise OperatorLifecycleFailure("git_probe_failed")
    try:
        completed = subprocess.run(  # noqa: S603 - fixed Git verbs, validated SHA
            [executable, "-c", f"safe.directory={checkout}", *arguments],
            cwd=checkout,
            env=_probe_environment(),
            shell=False,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            timeout=_COMMAND_TIMEOUT,
            check=False,
        )
    except (OSError, subprocess.SubprocessError) as error:
        raise OperatorLifecycleFailure("git_probe_failed") from error
    if completed.returncode != 0 or len(completed.stdout) > _OUTPUT_LIMIT:
        raise OperatorLifecycleFailure("git_probe_failed")
    return completed.stdout


def _probe_environment() -> dict[str, str]:
    allowed = ("PATH", "PATHEXT", "SYSTEMROOT", "WINDIR", "HOME", "USERPROFILE")
    return {key: os.environ[key] for key in allowed if key in os.environ}


def _one_line(value: bytes, reason: str) -> str:
    try:
        lines = value.decode("utf-8").splitlines()
    except UnicodeDecodeError as error:
        raise OperatorLifecycleFailure(reason) from error
    if len(lines) != 1 or not lines[0]:
        raise OperatorLifecycleFailure(reason)
    return lines[0]


def _is_reparse(path: Path) -> bool:
    try:
        attributes = path.lstat().st_file_attributes
    except AttributeError:
        return path.is_symlink()
    except OSError as error:
        raise OperatorLifecycleFailure("path_inspection_failed") from error
    return bool(attributes & stat.FILE_ATTRIBUTE_REPARSE_POINT)


def _assert_no_reparse_ancestry(path: Path, reason: str) -> None:
    current = path
    while True:
        if current.exists() and _is_reparse(current):
            raise OperatorLifecycleFailure(reason)
        if current == current.parent:
            return
        current = current.parent


def _contains(candidate: Path, root: Path) -> bool:
    try:
        candidate.relative_to(root)
    except ValueError:
        return False
    return True


def runtime_path_budget_ok(path: Path, *, platform_name: str = os.name) -> bool:
    """Reserve space for nested Git worktrees and target-owned test paths."""

    return platform_name != "nt" or len(str(path)) <= _MAX_WINDOWS_RUNTIME_ROOT_LENGTH


def source_snapshot(config: OperatorLifecycleConfig) -> SourceSnapshot:
    checkout = config.canonical_checkout
    if not checkout.is_dir() or _is_reparse(checkout):
        raise OperatorLifecycleFailure("canonical_checkout_invalid")
    _assert_no_reparse_ancestry(checkout, "canonical_checkout_reparse_ancestry")
    inside = _one_line(
        _run_git(checkout, ("rev-parse", "--is-inside-work-tree")),
        "canonical_checkout_invalid",
    )
    if inside != "true":
        raise OperatorLifecycleFailure("canonical_checkout_invalid")
    head = _one_line(_run_git(checkout, ("rev-parse", "HEAD")), "source_head_invalid")
    if head != config.target_sha:
        raise OperatorLifecycleFailure("source_head_mismatch")
    object_type = _one_line(
        _run_git(checkout, ("cat-file", "-t", config.target_sha)),
        "source_object_invalid",
    )
    if object_type != "commit":
        raise OperatorLifecycleFailure("source_object_invalid")
    status = _run_git(checkout, ("status", "--porcelain=v2", "--untracked-files=all"))
    if status:
        raise OperatorLifecycleFailure("source_checkout_dirty")
    tree = _one_line(
        _run_git(checkout, ("rev-parse", f"{config.target_sha}^{{tree}}")),
        "source_tree_invalid",
    )
    origin = _one_line(
        _run_git(checkout, ("remote", "get-url", "origin")),
        "source_origin_invalid",
    )
    accepted = {
        f"https://github.com/{config.repository_full_name}.git",
        f"git@github.com:{config.repository_full_name}.git",
    }
    if origin not in accepted:
        raise OperatorLifecycleFailure("source_origin_mismatch")
    return SourceSnapshot(
        head_sha=head, tree_sha=tree, status_digest=hashlib.sha256(status).hexdigest()
    )


def _port_appears_available(host: str, port: int) -> bool:
    family = socket.AF_INET6 if host == "::1" else socket.AF_INET
    address: tuple[str, int] | tuple[str, int, int, int]
    address = (host, port, 0, 0) if family == socket.AF_INET6 else (host, port)
    with socket.socket(family, socket.SOCK_STREAM) as probe:
        probe.settimeout(0.25)
        return probe.connect_ex(address) != 0


def _tool_version(name: str, *, allow_leading_v: bool = False) -> str | None:
    executable = shutil.which(name, path=os.environ.get("PATH"))
    if executable is None:
        return None
    try:
        completed = subprocess.run(  # noqa: S603 - fixed version-only argv
            [executable, "--version"],
            cwd=Path(os.path.abspath(os.sep)),
            env=_probe_environment(),
            shell=False,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            timeout=_COMMAND_TIMEOUT,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if completed.returncode != 0 or len(completed.stdout) > _VERSION_OUTPUT_LIMIT:
        return None
    try:
        lines = completed.stdout.decode("utf-8").strip().splitlines()
    except UnicodeDecodeError:
        return None
    if len(lines) != 1:
        return None
    value = lines[0].strip()
    if allow_leading_v and value[:1].lower() == "v":
        value = value[1:]
    return value


def _manifest_capabilities_compatible(  # noqa: PLR0911, PLR0912 - fail closed
    requirements: dict[str, object],
) -> bool:
    if set(requirements) - _SUPPORTED_CAPABILITY_KEYS:
        return False
    operating_system = platform.system().lower()
    architecture = platform.machine().lower()
    for name, required in requirements.items():
        if name in {"operating_system", "architecture"}:
            values = [required] if isinstance(required, str) else required
            if not isinstance(values, (list, tuple)) or not all(
                isinstance(item, str) for item in values
            ):
                return False
            actual = operating_system if name == "operating_system" else architecture
            if actual not in {item.lower() for item in values}:
                return False
        elif name == "python":
            if not runtime_version_matches(platform.python_version(), required):
                return False
        elif name == "node":
            if not runtime_version_matches(
                _tool_version("node", allow_leading_v=True), required
            ):
                return False
        elif name == "pnpm":
            if not runtime_version_matches(_tool_version("pnpm"), required):
                return False
        elif name == "git_available":
            if required is not True or shutil.which("git") is None:
                return False
        elif name == "repository_write" and required is not False:
            return False
    return True


def run_preflight(config: OperatorLifecycleConfig) -> PreflightResult:
    """Complete all read-only checks before runtime creation."""

    if sys.version_info < (3, 11):
        raise OperatorLifecycleFailure("python_version_unsupported")
    if not strict_containment_supported():
        raise OperatorLifecycleFailure("strict_containment_unsupported")
    if config.runtime_root.exists():
        raise OperatorLifecycleFailure("runtime_root_already_exists")
    if not runtime_path_budget_ok(config.runtime_root):
        raise OperatorLifecycleFailure("runtime_path_budget_exceeded")
    _assert_no_reparse_ancestry(
        config.runtime_root.parent, "runtime_parent_reparse_ancestry"
    )
    canonical = config.canonical_checkout.resolve(strict=True)
    runtime_parent = config.runtime_root.parent.resolve(strict=True)
    prospective = runtime_parent / config.runtime_root.name
    if _contains(prospective, canonical) or _contains(canonical, prospective):
        raise OperatorLifecycleFailure("runtime_source_overlap")
    if not _port_appears_available(config.host, config.port):
        raise OperatorLifecycleFailure("loopback_port_occupied")
    token_present = bool(os.environ.get("SWITCHBOARD_ADMIN_TOKEN", "").strip())
    if not token_present:
        raise OperatorLifecycleFailure("admin_token_missing")
    snapshot = source_snapshot(config)
    manifest = get_trusted_manifest(config.manifest_name, config.manifest_version)
    if manifest is None:
        raise OperatorLifecycleFailure("trusted_manifest_not_found")
    digest = manifest.digest
    if (
        config.expected_manifest_digest is not None
        and digest != config.expected_manifest_digest
    ):
        raise OperatorLifecycleFailure("trusted_manifest_digest_mismatch")
    if (
        manifest.repository_write_policy.value != "read_only"
        or manifest.network_policy.value != "worker_restricted"
        or not manifest.execution_steps
    ):
        raise OperatorLifecycleFailure("trusted_manifest_contract_unsupported")
    if not _manifest_capabilities_compatible(manifest.required_capabilities):
        raise OperatorLifecycleFailure("worker_capability_mismatch")
    return PreflightResult(
        source=snapshot,
        manifest_digest=digest,
        manifest_steps=tuple(
            (step.id, step.required) for step in manifest.execution_steps
        ),
        token_present=token_present,
    )


__all__ = [
    "PREFLIGHT_CHECKS",
    "PreflightResult",
    "SourceSnapshot",
    "run_preflight",
    "runtime_path_budget_ok",
    "source_snapshot",
]
