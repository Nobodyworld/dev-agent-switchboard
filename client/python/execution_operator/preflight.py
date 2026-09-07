"""Read-only exact-source and host preflight for the operator lifecycle."""

from __future__ import annotations

import hashlib
import os
import platform
import re
import shutil
import socket
import stat
import subprocess
import sys
from collections.abc import Callable
from dataclasses import asdict, dataclass
from pathlib import Path
from urllib.parse import SplitResult, urlsplit

from client.python.execution_worker.containment import strict_containment_supported
from server.execution.capabilities import runtime_version_matches
from server.execution.registry import TrustedManifest, get_trusted_manifest

from .config import OperatorConfigurationError, OperatorLifecycleConfig
from .models import OperatorLifecycleFailure
from .report_contract import PREFLIGHT_CHECKS

_COMMAND_TIMEOUT = 10.0
_OUTPUT_LIMIT = 64 * 1024
_VERSION_OUTPUT_LIMIT = 256
_MAX_WINDOWS_RUNTIME_ROOT_LENGTH = 80
_WINDOWS_REPARSE_POINT_FALLBACK = 0x0400
_GITHUB_REPOSITORY_COMPONENT_COUNT = 2
_GITHUB_COMPONENT = re.compile(r"^[A-Za-z0-9_.-]+$")
_PUBLIC_IDENTITY_RULES = {
    "repository_full_name": (re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$"), 255),
    "target_sha": (re.compile(r"^[0-9a-f]{40}$"), 40),
    "manifest_name": (re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$"), 128),
    "manifest_version": (re.compile(r"^[A-Za-z0-9_.-]{1,64}$"), 64),
    "worker_id": (re.compile(r"^[A-Za-z0-9_.-]{1,128}$"), 128),
    "expected_manifest_digest": (re.compile(r"^[0-9a-f]{64}$"), 64),
    "verified_manifest_digest": (re.compile(r"^[0-9a-f]{64}$"), 64),
}
_CREDENTIAL = re.compile(r"(?i)(?:gh[pousr]_|github_pat_|sk-[a-z0-9]{16})")
_SCP_GITHUB_ORIGIN = re.compile(
    r"^git@(?P<host>github\.com):(?P<path>[^?#]+)$", re.IGNORECASE
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
READINESS_CHECKS = (
    "configuration",
    "python_runtime",
    "strict_containment",
    "root_safety",
    "control_plane_source",
    "loopback_port",
    "process_token",
    "canonical_source",
    "manifest_contract",
    "manifest_timeouts",
    "worker_capabilities",
)
PREFLIGHT_FAILURE_REASONS = frozenset(
    {
        "invalid_configuration",
        "public_identity_rejected",
        "python_version_unsupported",
        "strict_containment_unsupported",
        "runtime_root_already_exists",
        "runtime_path_budget_exceeded",
        "runtime_parent_reparse_ancestry",
        "runtime_parent_invalid",
        "runtime_source_overlap",
        "path_inspection_failed",
        "control_plane_source_reparse_ancestry",
        "control_plane_source_invalid",
        "control_plane_target_overlap",
        "loopback_port_occupied",
        "loopback_port_probe_failed",
        "admin_token_missing",
        "git_probe_failed",
        "canonical_checkout_invalid",
        "canonical_checkout_reparse_ancestry",
        "source_head_invalid",
        "source_head_mismatch",
        "source_object_invalid",
        "source_checkout_dirty",
        "source_tree_invalid",
        "source_origin_invalid",
        "source_origin_mismatch",
        "trusted_manifest_not_found",
        "trusted_manifest_digest_mismatch",
        "trusted_manifest_contract_unsupported",
        "manifest_timeout_exceeds_worker_budget",
        "manifest_step_timeout_exceeds_worker_budget",
        "terminal_timeout_below_manifest_budget",
        "worker_capability_mismatch",
        "preflight_probe_failed",
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


@dataclass(frozen=True, slots=True)
class PreflightCheck:
    name: str
    status: str
    reason: str | None = None


@dataclass(frozen=True, slots=True)
class PreflightAssessment:
    """Private execution proof and the checks actually performed to obtain it."""

    result: PreflightResult | None
    checks: tuple[PreflightCheck, ...]
    reason: str
    manifest_timeout_seconds: int | None
    maximum_step_timeout_seconds: int | None


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
    environment = {key: os.environ[key] for key in allowed if key in os.environ}
    # Even a clean status probe must not refresh or lock the target Git index.
    environment["GIT_OPTIONAL_LOCKS"] = "0"
    return environment


def _one_line(value: bytes, reason: str) -> str:
    try:
        lines = value.decode("utf-8").splitlines()
    except UnicodeDecodeError as error:
        raise OperatorLifecycleFailure(reason) from error
    if len(lines) != 1 or not lines[0]:
        raise OperatorLifecycleFailure(reason)
    return lines[0]


def _file_attributes(metadata: os.stat_result) -> int | None:
    attributes = getattr(metadata, "st_file_attributes", None)
    return attributes if isinstance(attributes, int) else None


def _reparse_point_flag() -> int:
    value = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", None)
    return (
        value
        if isinstance(value, int) and value > 0
        else _WINDOWS_REPARSE_POINT_FALLBACK
    )


def _metadata_is_reparse(metadata: os.stat_result) -> bool:
    attributes = _file_attributes(metadata)
    return stat.S_ISLNK(metadata.st_mode) or bool(
        attributes is not None and attributes & _reparse_point_flag()
    )


def path_is_reparse(path: Path) -> bool:
    """Inspect symlink/reparse state without Linux-only typing assumptions."""

    try:
        return _metadata_is_reparse(path.lstat())
    except OSError as error:
        raise OperatorLifecycleFailure("path_inspection_failed") from error


def assert_no_reparse_ancestry(path: Path, reason: str) -> None:
    current = path
    while True:
        try:
            metadata = current.lstat()
        except FileNotFoundError:
            metadata = None
        except OSError as error:
            raise OperatorLifecycleFailure("path_inspection_failed") from error
        if metadata is not None and _metadata_is_reparse(metadata):
            raise OperatorLifecycleFailure(reason)
        if current == current.parent:
            return
        current = current.parent


def _github_repository_parts(path: str) -> tuple[str, str] | None:
    if not path or "%" in path or "\\" in path:
        return None
    normalized = path[:-1] if path.endswith("/") else path
    if normalized.endswith("/") or normalized.startswith("//"):
        return None
    normalized = normalized[1:] if normalized.startswith("/") else normalized
    parts = normalized.split("/")
    if len(parts) != _GITHUB_REPOSITORY_COMPONENT_COUNT:
        return None
    owner, repository = parts
    if repository.endswith(".git"):
        repository = repository[:-4]
    if (
        not owner
        or not repository
        or owner in {".", ".."}
        or repository in {".", ".."}
        or not _GITHUB_COMPONENT.fullmatch(owner)
        or not _GITHUB_COMPONENT.fullmatch(repository)
    ):
        return None
    return owner.casefold(), repository.casefold()


def _url_github_repository(parsed: SplitResult) -> tuple[str, str] | None:
    try:
        port = parsed.port
    except ValueError:
        return None
    if (
        parsed.query
        or parsed.fragment
        or port is not None
        or parsed.hostname is None
        or parsed.hostname.casefold() != "github.com"
    ):
        return None
    if parsed.scheme == "https":
        if (
            "@" in parsed.netloc
            or parsed.username is not None
            or parsed.password is not None
        ):
            return None
    elif parsed.scheme == "ssh":
        if parsed.username != "git" or parsed.password is not None:
            return None
    else:
        return None
    return _github_repository_parts(parsed.path)


def github_origin_identity(origin: str) -> tuple[str, str] | None:
    """Return a strict case-insensitive GitHub owner/repository identity."""

    match = _SCP_GITHUB_ORIGIN.fullmatch(origin)
    if match is not None:
        return _github_repository_parts(match.group("path"))
    try:
        parsed = urlsplit(origin)
    except ValueError:
        return None
    return _url_github_repository(parsed)


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
    if not checkout.is_dir() or path_is_reparse(checkout):
        raise OperatorLifecycleFailure("canonical_checkout_invalid")
    assert_no_reparse_ancestry(checkout, "canonical_checkout_reparse_ancestry")
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
    expected_identity = tuple(
        component.casefold() for component in config.repository_full_name.split("/", 1)
    )
    if github_origin_identity(origin) != expected_identity:
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


def _validate_manifest_timeouts(
    config: OperatorLifecycleConfig, manifest: TrustedManifest
) -> None:
    """Reject limits the generated worker would refuse, before creating state."""

    if manifest.timeout_seconds > config.work_order_timeout_seconds:
        raise OperatorLifecycleFailure("manifest_timeout_exceeds_worker_budget")
    if any(
        step.timeout_seconds > config.work_order_timeout_seconds
        for step in manifest.execution_steps
    ):
        raise OperatorLifecycleFailure("manifest_step_timeout_exceeds_worker_budget")
    if config.terminal_timeout_seconds < manifest.timeout_seconds:
        raise OperatorLifecycleFailure("terminal_timeout_below_manifest_budget")


def _validate_python_runtime() -> None:
    if sys.version_info < (3, 11):
        raise OperatorLifecycleFailure("python_version_unsupported")


def _validate_containment() -> None:
    if not strict_containment_supported():
        raise OperatorLifecycleFailure("strict_containment_unsupported")


def _validate_roots(config: OperatorLifecycleConfig) -> None:
    if config.runtime_root.exists() or config.runtime_root.is_symlink():
        raise OperatorLifecycleFailure("runtime_root_already_exists")
    if not runtime_path_budget_ok(config.runtime_root):
        raise OperatorLifecycleFailure("runtime_path_budget_exceeded")
    assert_no_reparse_ancestry(
        config.runtime_root.parent, "runtime_parent_reparse_ancestry"
    )
    try:
        canonical = config.canonical_checkout.resolve(strict=True)
    except OSError as error:
        raise OperatorLifecycleFailure("canonical_checkout_invalid") from error
    try:
        runtime_parent = config.runtime_root.parent.resolve(strict=True)
    except OSError as error:
        raise OperatorLifecycleFailure("runtime_parent_invalid") from error
    if not runtime_parent.is_dir():
        raise OperatorLifecycleFailure("runtime_parent_invalid")
    prospective = runtime_parent / config.runtime_root.name
    if _contains(prospective, canonical) or _contains(canonical, prospective):
        raise OperatorLifecycleFailure("runtime_source_overlap")


def _validate_control_plane(config: OperatorLifecycleConfig) -> None:
    # Deferred to avoid the process/runtime imports forming an import cycle.
    from .processes import _control_plane_source_root  # noqa: PLC0415

    _control_plane_source_root(config)


def _validate_port(config: OperatorLifecycleConfig) -> None:
    try:
        available = _port_appears_available(config.host, config.port)
    except OSError as error:
        raise OperatorLifecycleFailure("loopback_port_probe_failed") from error
    if not available:
        raise OperatorLifecycleFailure("loopback_port_occupied")


def _validate_token() -> None:
    if not os.environ.get("SWITCHBOARD_ADMIN_TOKEN", "").strip():
        raise OperatorLifecycleFailure("admin_token_missing")


def safe_readiness_identity(field: str, value: object) -> str | None:
    """Use one closed public-identity policy before execution and presentation."""

    rule = _PUBLIC_IDENTITY_RULES.get(field)
    if rule is None or not isinstance(value, str):
        return None
    pattern, maximum = rule
    token = os.environ.get("SWITCHBOARD_ADMIN_TOKEN", "").strip()
    if (
        len(value) > maximum
        or pattern.fullmatch(value) is None
        or _CREDENTIAL.search(value)
        or (token and token in value)
        or any(part in {".", ".."} for part in value.split("/"))
    ):
        return None
    return value


def _validate_configuration(config: OperatorLifecycleConfig) -> None:
    payload = asdict(config)
    payload.update(
        schema_version=1,
        canonical_checkout=str(config.canonical_checkout),
        runtime_root=str(config.runtime_root),
    )
    try:
        OperatorLifecycleConfig.from_mapping(payload)
    except (OperatorConfigurationError, ValueError, TypeError, OverflowError) as error:
        raise OperatorLifecycleFailure("invalid_configuration") from error
    for field in _PUBLIC_IDENTITY_RULES:
        if field == "verified_manifest_digest":
            continue
        value = getattr(config, field)
        if field == "expected_manifest_digest" and value is None:
            continue
        if safe_readiness_identity(field, value) is None:
            raise OperatorLifecycleFailure("invalid_configuration")


def _validated_manifest(config: OperatorLifecycleConfig) -> TrustedManifest:
    manifest = get_trusted_manifest(config.manifest_name, config.manifest_version)
    if manifest is None:
        raise OperatorLifecycleFailure("trusted_manifest_not_found")
    digest = manifest.digest
    if safe_readiness_identity("verified_manifest_digest", digest) is None:
        raise OperatorLifecycleFailure("public_identity_rejected")
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
    return manifest


@dataclass(slots=True)
class _PreflightProbes:
    config: OperatorLifecycleConfig
    source: SourceSnapshot | None = None
    manifest: TrustedManifest | None = None

    def inspect_source(self) -> None:
        self.source = source_snapshot(self.config)

    def inspect_manifest(self) -> None:
        self.manifest = _validated_manifest(self.config)

    def inspect_timeouts(self) -> None:
        assert self.manifest is not None
        _validate_manifest_timeouts(self.config, self.manifest)

    def inspect_capabilities(self) -> None:
        assert self.manifest is not None
        if not _manifest_capabilities_compatible(self.manifest.required_capabilities):
            raise OperatorLifecycleFailure("worker_capability_mismatch")

    def ordered(self) -> tuple[Callable[[], None], ...]:
        return (
            lambda: _validate_configuration(self.config),
            _validate_python_runtime,
            _validate_containment,
            lambda: _validate_roots(self.config),
            lambda: _validate_control_plane(self.config),
            lambda: _validate_port(self.config),
            _validate_token,
            self.inspect_source,
            self.inspect_manifest,
            self.inspect_timeouts,
            self.inspect_capabilities,
        )


def assess_preflight(config: OperatorLifecycleConfig) -> PreflightAssessment:
    """Run the single authoritative sequence, stopping at its first failure."""

    probes = _PreflightProbes(config)
    checks: list[PreflightCheck] = []
    reason = "ready"
    for name, probe in zip(READINESS_CHECKS, probes.ordered(), strict=True):
        if reason != "ready":
            checks.append(PreflightCheck(name, "not_checked"))
            continue
        try:
            probe()
        except OperatorLifecycleFailure as error:
            reason = (
                error.reason
                if error.reason in PREFLIGHT_FAILURE_REASONS
                else "preflight_probe_failed"
            )
        except Exception:
            reason = "preflight_probe_failed"
        checks.append(
            PreflightCheck(
                name,
                "pass" if reason == "ready" else "fail",
                None if reason == "ready" else reason,
            )
        )
    manifest = probes.manifest
    result = None
    if reason == "ready" and manifest is not None and probes.source is not None:
        result = PreflightResult(
            source=probes.source,
            manifest_digest=manifest.digest,
            manifest_steps=tuple(
                (step.id, step.required) for step in manifest.execution_steps
            ),
            token_present=True,
        )
    return PreflightAssessment(
        result=result,
        checks=tuple(checks),
        reason=reason,
        manifest_timeout_seconds=(manifest.timeout_seconds if manifest else None),
        maximum_step_timeout_seconds=(
            max(step.timeout_seconds for step in manifest.execution_steps)
            if manifest
            else None
        ),
    )


def run_preflight(config: OperatorLifecycleConfig) -> PreflightResult:
    """Repeat all read-only checks immediately before runtime creation."""

    assessment = assess_preflight(config)
    if assessment.result is None:
        raise OperatorLifecycleFailure(assessment.reason)
    return assessment.result


__all__ = [
    "PREFLIGHT_CHECKS",
    "PreflightResult",
    "SourceSnapshot",
    "assert_no_reparse_ancestry",
    "github_origin_identity",
    "path_is_reparse",
    "run_preflight",
    "runtime_path_budget_ok",
    "source_snapshot",
]
