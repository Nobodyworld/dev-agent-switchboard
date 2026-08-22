# Every subprocess call in this module accepts only immutable reviewed TrustedStep
# argv or a fixed internal OS process-tree command; no caller argv reaches it.
# ruff: noqa: S603
"""Fixed-argv process execution with bounded output and cancellation."""

from __future__ import annotations

import datetime as dt
import errno
import os
import re
import signal
import subprocess
import sys
import threading
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path

from server.execution.evidence import ParsedResult, TerminalStatus
from server.execution.registry import TrustedStep

from .config import WorkerConfig
from .containment import (
    ContainmentCleanupError,
    StrictHostProcess,
    launch_strict_host,
)
from .parsers import parse_result

_WINDOWS_ABSOLUTE_PATH = re.compile(r"(?i)\b[A-Z]:\\[^\s\r\n\"']+")
_POSIX_ABSOLUTE_PATH = re.compile(r"(?<![:A-Za-z0-9])/(?:[^\s\r\n\"']+/?)+")
_LINUX_TERMINAL_PROCESS_STATES = frozenset({"X", "x", "Z"})
_LINUX_STAT_MIN_FIELDS = 3
_PROCESS_GROUP_POLL_SECONDS = 0.01


class OverallDeadlineExceededError(RuntimeError):
    """Raised before launch when no overall execution time remains."""


class CancellationToken:
    """Thread-safe run cancellation reason shared by monitor and runner."""

    def __init__(self) -> None:
        self._event = threading.Event()
        self._reason = "cancelled"
        self._lock = threading.Lock()

    def cancel(self, reason: str) -> None:
        with self._lock:
            if not self._event.is_set():
                self._reason = reason
                self._event.set()

    @property
    def cancelled(self) -> bool:
        return self._event.is_set()

    @property
    def reason(self) -> str:
        with self._lock:
            return self._reason


@dataclass(frozen=True, slots=True)
class StepResult:
    step_id: str
    title: str
    status: TerminalStatus
    exit_code: int | None
    duration_seconds: float
    stdout_summary: str
    stderr_summary: str
    summaries_truncated: bool
    stdout_log: str
    stderr_log: str
    environment_summary: dict[str, str]
    started_at: dt.datetime
    finished_at: dt.datetime
    parsed_result: ParsedResult | None
    terminal_reason: str | None = None


def _redact(value: str, config: WorkerConfig) -> str:
    for pattern in config.redacted_value_patterns:
        if pattern:
            value = value.replace(pattern, "[REDACTED]")
    value = _WINDOWS_ABSOLUTE_PATH.sub("[LOCAL_PATH]", value)
    return _POSIX_ABSOLUTE_PATH.sub("[LOCAL_PATH]", value)


def environment_summary(
    environment: dict[str, str], config: WorkerConfig
) -> dict[str, str]:
    """Expose only safe environment presence, respecting configured key patterns."""

    patterns = tuple(pattern.upper() for pattern in config.redacted_key_patterns)
    return {
        key: (
            "[REDACTED]"
            if any(pattern in key.upper() for pattern in patterns)
            else "[SET]"
        )
        for key in sorted(environment)
    }


def _summary(path: Path, limit: int, config: WorkerConfig) -> tuple[str, bool]:
    size = path.stat().st_size if path.exists() else 0
    lookahead = max(
        (len(value.encode("utf-8")) for value in config.redacted_value_patterns),
        default=0,
    )
    with path.open("rb") as handle:
        data = handle.read(limit + lookahead)
    text = _redact(data.decode("utf-8", errors="replace"), config)
    return text[:limit], size > limit


def _directory_size(path: Path) -> int:
    return sum(
        item.stat().st_size
        for item in path.rglob("*")
        if item.is_file() and not item.is_symlink()
    )


def _runtime_argv(argv: tuple[str, ...]) -> tuple[str, ...]:
    """Bind trusted symbolic Python steps to this worker's interpreter."""

    if argv and argv[0] == "python":
        return (sys.executable, *argv[1:])
    return argv


def _parse_linux_process_stat(value: str) -> tuple[int, str] | None:
    """Parse the process group and state from one Linux /proc stat record."""

    command_end = value.rfind(")")
    fields = value[command_end + 2 :].split() if command_end >= 0 else []
    if len(fields) < _LINUX_STAT_MIN_FIELDS:
        return None
    try:
        process_group_id = int(fields[2])
    except ValueError:
        return None
    return process_group_id, fields[0]


def _linux_process_group_members(process_group_id: int) -> dict[int, str] | None:
    """Return Linux process states for a group, or None without reliable /proc."""

    proc_root = Path("/proc")
    if os.name == "nt" or not (proc_root / "self" / "stat").is_file():
        return None
    try:
        entries = tuple(proc_root.iterdir())
    except OSError:
        return None

    members: dict[int, str] = {}
    reliable = True
    for entry in entries:
        if not entry.name.isdecimal():
            continue
        try:
            stat = (entry / "stat").read_text(encoding="utf-8", errors="replace")
        except (FileNotFoundError, ProcessLookupError):
            continue
        except PermissionError:
            reliable = False
            break
        except OSError as error:
            if error.errno in {errno.ENOENT, errno.ESRCH}:
                continue
            reliable = False
            break

        parsed = _parse_linux_process_stat(stat)
        if parsed is None:
            reliable = False
            break
        try:
            member_process_id = int(entry.name)
        except ValueError:
            reliable = False
            break
        member_group_id, state = parsed
        if member_group_id == process_group_id:
            members[member_process_id] = state
    return members if reliable else None


def _process_group_observation(process_group_id: int) -> tuple[bool, str]:
    """Report execution-capable group membership; zombies are already terminated."""

    members = _linux_process_group_members(process_group_id)
    if members is not None:
        live = {
            process_id: state
            for process_id, state in members.items()
            if state not in _LINUX_TERMINAL_PROCESS_STATES
        }
        terminal = {
            process_id: state
            for process_id, state in members.items()
            if state in _LINUX_TERMINAL_PROCESS_STATES
        }
        if not members:
            kill_process_group = getattr(os, "killpg", None)
            if _signal_process_group(kill_process_group, process_group_id, 0):
                return (
                    True,
                    f"pgid={process_group_id} membership remains (states unavailable)",
                )
            return False, f"pgid={process_group_id} members=none"

        details = [f"pgid={process_group_id}"]
        if live:
            details.append(
                "live="
                + ",".join(
                    f"{process_id}:{state}"
                    for process_id, state in sorted(live.items())
                )
            )
        if terminal:
            details.append(
                "terminal="
                + ",".join(
                    f"{process_id}:{state}"
                    for process_id, state in sorted(terminal.items())
                )
            )
        return bool(live), " ".join(details)

    kill_process_group = getattr(os, "killpg", None)
    alive = _signal_process_group(kill_process_group, process_group_id, 0)
    return alive, (
        f"pgid={process_group_id} membership remains (states unavailable)"
        if alive
        else f"pgid={process_group_id} members=none"
    )


def _terminate_windows(process: subprocess.Popen[bytes], grace_seconds: float) -> None:
    """Use the fixed Windows tree-kill command for the trusted child PID."""

    terminated = subprocess.run(
        ["taskkill", "/PID", str(process.pid), "/T", "/F"],  # noqa: S607
        shell=False,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=False,
    )
    try:
        process.wait(timeout=grace_seconds)
    except subprocess.TimeoutExpired as error:
        raise RuntimeError(
            "Windows process-tree termination failed "
            f"(taskkill_exit={terminated.returncode})"
        ) from error
    if process.poll() is None:
        raise RuntimeError("Windows process-tree termination left parent running")


def _signal_process_group(
    kill_process_group: object, process_id: int, signal_number: int | signal.Signals
) -> bool:
    """Signal one known process group, returning false when it has exited."""

    if not callable(kill_process_group):  # pragma: no cover - POSIX contract guard
        raise RuntimeError("POSIX process-group termination is unavailable")
    try:
        kill_process_group(process_id, signal_number)
    except ProcessLookupError:
        return False
    return True


def _wait_for_parent(process: subprocess.Popen[bytes], grace_seconds: float) -> bool:
    try:
        process.wait(timeout=grace_seconds)
    except subprocess.TimeoutExpired:
        return False
    return True


def _wait_for_process_group_exit(process_group_id: int, grace_seconds: float) -> None:
    """Wait within the grace budget until no execution-capable member remains."""

    deadline = time.monotonic() + max(grace_seconds, 0.0)
    while True:
        alive, details = _process_group_observation(process_group_id)
        if not alive:
            return
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise RuntimeError(
                f"POSIX descendant process termination failed ({details})"
            )
        time.sleep(min(_PROCESS_GROUP_POLL_SECONDS, remaining))


def _terminate_posix(process: subprocess.Popen[bytes], grace_seconds: float) -> None:
    """Send TERM then KILL to the trusted process group and verify it exits."""

    kill_process_group = getattr(os, "killpg", None)
    if not _signal_process_group(kill_process_group, process.pid, signal.SIGTERM):
        return
    force_signal = getattr(signal, "SIGKILL", signal.SIGTERM)
    force_sent = False
    if not _wait_for_parent(process, grace_seconds):
        _signal_process_group(kill_process_group, process.pid, force_signal)
        force_sent = True
        if not _wait_for_parent(process, grace_seconds):
            raise RuntimeError("POSIX parent process termination failed")
    alive, _details = _process_group_observation(process.pid)
    if not alive:
        return
    if not force_sent and not _signal_process_group(
        kill_process_group, process.pid, force_signal
    ):
        return
    _wait_for_process_group_exit(process.pid, grace_seconds)


def _terminate(process: subprocess.Popen[bytes], *, grace_seconds: float = 2.0) -> None:
    """Terminate a trusted process and descendants, surfacing failed cleanup."""

    if os.name == "nt":
        _terminate_windows(process, grace_seconds)
        return
    _terminate_posix(process, grace_seconds)


def _terminate_active_step(
    process: subprocess.Popen[bytes], strict_host: StrictHostProcess | None
) -> bool:
    """Terminate one step and report whether descendant quiescence is provable."""

    try:
        if strict_host is not None:
            strict_host.terminate()
        else:
            _terminate(process)
    except (ContainmentCleanupError, OSError, RuntimeError):
        return False
    return True


def _reap_unexpected_descendants_after_exit(
    process: subprocess.Popen[bytes], *, grace_seconds: float = 2.0
) -> bool:
    """Quiesce an exited command's process tree before reading target outputs.

    A reviewed command is not allowed to detach background work.  On POSIX the
    dedicated session gives us a precise group to inspect and terminate.  The
    Windows task-tree command is the existing native containment mechanism;
    its success means it found remaining descendants to reap.
    """

    if os.name == "nt":
        terminated = subprocess.run(
            ["taskkill", "/PID", str(process.pid), "/T", "/F"],  # noqa: S607
            shell=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        )
        return terminated.returncode == 0
    alive, _details = _process_group_observation(process.pid)
    if not alive:
        return False
    _terminate_posix(process, grace_seconds)
    return True


def _result(  # noqa: PLR0913 - immutable result records keep call-site context clear
    *,
    step: TrustedStep,
    status: TerminalStatus,
    process: subprocess.Popen[bytes],
    started: float,
    started_at: dt.datetime,
    stdout_path: Path,
    stderr_path: Path,
    checkout: Path,
    config: WorkerConfig,
    environment: dict[str, str],
    terminal_reason: str | None = None,
    result_contract: Mapping[str, object] | None = None,
    checkout_guard: Callable[[], None] | None = None,
) -> StepResult:
    limit = min(step.output_summary_limit, config.output_summary_limit)
    out, out_cut = _summary(stdout_path, limit, config)
    err, err_cut = _summary(stderr_path, limit, config)
    finished_at = dt.datetime.now(dt.UTC)
    if checkout_guard is not None:
        checkout_guard()
    parsed_result = (
        parse_result(
            step.parser_kind,
            stdout_path=stdout_path,
            stderr_path=stderr_path,
            command_succeeded=status == "succeeded",
            checkout=checkout,
            result_contract=result_contract,
        )
        if step.parser_kind is not None
        else None
    )
    return StepResult(
        step_id=step.id,
        title=step.title,
        status=status,
        exit_code=process.returncode,
        duration_seconds=time.monotonic() - started,
        stdout_summary=out,
        stderr_summary=err,
        summaries_truncated=out_cut or err_cut,
        stdout_log=stdout_path.name,
        stderr_log=stderr_path.name,
        environment_summary=environment_summary(environment, config),
        started_at=started_at,
        finished_at=finished_at,
        parsed_result=parsed_result,
        terminal_reason=terminal_reason,
    )


def _unquiescent_result(  # noqa: PLR0913 - preserves complete step provenance
    *,
    step: TrustedStep,
    process: subprocess.Popen[bytes],
    started: float,
    started_at: dt.datetime,
    stdout_path: Path,
    stderr_path: Path,
    config: WorkerConfig,
    environment: dict[str, str],
) -> StepResult:
    """Return a fixed failure without consuming output from an unsafe source."""

    return StepResult(
        step_id=step.id,
        title=step.title,
        status="failed",
        exit_code=process.returncode,
        duration_seconds=time.monotonic() - started,
        stdout_summary="",
        stderr_summary="",
        summaries_truncated=True,
        stdout_log=stdout_path.name,
        stderr_log=stderr_path.name,
        environment_summary=environment_summary(environment, config),
        started_at=started_at,
        finished_at=dt.datetime.now(dt.UTC),
        parsed_result=None,
        terminal_reason="descendant_cleanup_failed",
    )


def _abort_after_launch_error(  # noqa: PLR0913 - preserves complete step provenance
    *,
    step: TrustedStep,
    process: subprocess.Popen[bytes],
    strict_host: StrictHostProcess | None,
    started: float,
    started_at: dt.datetime,
    stdout_path: Path,
    stderr_path: Path,
    config: WorkerConfig,
    environment: dict[str, str],
) -> StepResult:
    """Quarantine a launched target when monitoring cannot prove its state."""

    _terminate_active_step(process, strict_host)
    return _unquiescent_result(
        step=step,
        process=process,
        started=started,
        started_at=started_at,
        stdout_path=stdout_path,
        stderr_path=stderr_path,
        config=config,
        environment=environment,
    )


def run_step(  # noqa: PLR0911, PLR0912, PLR0913, PLR0915 - trusted lifecycle inputs are explicit
    step: TrustedStep,
    checkout: Path,
    logs: Path,
    config: WorkerConfig,
    deadline: float,
    *,
    cancellation: CancellationToken | None = None,
    allowed_inherited_environment_keys: frozenset[str] | None = None,
    result_contract: Mapping[str, object] | None = None,
    strict_containment: bool = False,
    checkout_guard: Callable[[], None] | None = None,
) -> StepResult:
    """Run one locally resolved reviewed step; no caller argv is accepted."""

    remaining = deadline - time.monotonic()
    if remaining <= 0:
        raise OverallDeadlineExceededError(
            "overall execution deadline expired before launch"
        )
    if cancellation is not None and cancellation.cancelled:
        raise OverallDeadlineExceededError(
            f"execution cancelled before launch:{cancellation.reason}"
        )
    if checkout_guard is not None:
        checkout_guard()
    cwd = (checkout / step.working_directory).resolve(strict=True)
    if checkout.resolve() not in (cwd, *cwd.parents):
        raise ValueError("trusted working directory escaped checkout")
    logs.mkdir(parents=True, exist_ok=True)
    stdout_path, stderr_path = (
        logs / f"{step.id}.stdout.log",
        logs / f"{step.id}.stderr.log",
    )
    configured_inherited_keys = config.inherited_environment_keys
    if allowed_inherited_environment_keys is not None:
        configured_inherited_keys = tuple(
            key
            for key in configured_inherited_keys
            if key in allowed_inherited_environment_keys
        )
    environment = {
        key: os.environ[key] for key in configured_inherited_keys if key in os.environ
    }
    environment.update(dict(step.environment))
    step_deadline = time.monotonic() + min(
        float(step.timeout_seconds), config.maximum_step_timeout_seconds, remaining
    )
    started = time.monotonic()
    started_at = dt.datetime.now(dt.UTC)
    with stdout_path.open("wb") as stdout, stderr_path.open("wb") as stderr:
        strict_host: StrictHostProcess | None = None
        if not strict_containment:
            # Preserve the established legacy execution path byte-for-byte in
            # behavior.  New public profiles opt into the gated containment host
            # separately so parser contracts remain independent per step.
            process = subprocess.Popen(
                _runtime_argv(step.argv),
                cwd=cwd,
                env=environment,
                shell=False,
                stdout=stdout,
                stderr=stderr,
                start_new_session=os.name != "nt",
            )
        else:
            strict_host = launch_strict_host(
                argv=_runtime_argv(step.argv),
                cwd=cwd,
                environment=environment,
                stdout=stdout,
                stderr=stderr,
            )
            process = strict_host.process
        status: TerminalStatus = "failed"
        reason: str | None = None
        while process.poll() is None:
            now = time.monotonic()
            if cancellation is not None and cancellation.cancelled:
                status, reason = "cancelled", cancellation.reason
                if not _terminate_active_step(process, strict_host):
                    return _unquiescent_result(
                        step=step,
                        process=process,
                        started=started,
                        started_at=started_at,
                        stdout_path=stdout_path,
                        stderr_path=stderr_path,
                        config=config,
                        environment=environment,
                    )
                break
            if now >= deadline:
                status, reason = "timed_out", "overall_timeout"
                if not _terminate_active_step(process, strict_host):
                    return _unquiescent_result(
                        step=step,
                        process=process,
                        started=started,
                        started_at=started_at,
                        stdout_path=stdout_path,
                        stderr_path=stderr_path,
                        config=config,
                        environment=environment,
                    )
                break
            if now >= step_deadline:
                status, reason = "timed_out", "step_timeout"
                if not _terminate_active_step(process, strict_host):
                    return _unquiescent_result(
                        step=step,
                        process=process,
                        started=started,
                        started_at=started_at,
                        stdout_path=stdout_path,
                        stderr_path=stderr_path,
                        config=config,
                        environment=environment,
                    )
                break
            try:
                total_output = _directory_size(logs)
            except OSError:
                return _abort_after_launch_error(
                    step=step,
                    process=process,
                    strict_host=strict_host,
                    started=started,
                    started_at=started_at,
                    stdout_path=stdout_path,
                    stderr_path=stderr_path,
                    config=config,
                    environment=environment,
                )
            if total_output > config.total_output_limit:
                status, reason = "failed", "total_output_limit_exceeded"
                if not _terminate_active_step(process, strict_host):
                    return _unquiescent_result(
                        step=step,
                        process=process,
                        started=started,
                        started_at=started_at,
                        stdout_path=stdout_path,
                        stderr_path=stderr_path,
                        config=config,
                        environment=environment,
                    )
                break
            run_directory = logs.parent
            try:
                run_directory_size = _directory_size(run_directory)
            except OSError:
                return _abort_after_launch_error(
                    step=step,
                    process=process,
                    strict_host=strict_host,
                    started=started,
                    started_at=started_at,
                    stdout_path=stdout_path,
                    stderr_path=stderr_path,
                    config=config,
                    environment=environment,
                )
            if run_directory_size > config.disk_limit_bytes:
                reason = (
                    "total_output_limit_exceeded"
                    if total_output > config.total_output_limit
                    else "disk_limit_exceeded"
                )
                status = "failed"
                if not _terminate_active_step(process, strict_host):
                    return _unquiescent_result(
                        step=step,
                        process=process,
                        started=started,
                        started_at=started_at,
                        stdout_path=stdout_path,
                        stderr_path=stderr_path,
                        config=config,
                        environment=environment,
                    )
                break
            time.sleep(0.02)
        if process.poll() is None:  # pragma: no cover - _terminate contract guard
            raise RuntimeError("trusted process did not terminate")
        if strict_host is not None:
            try:
                outcome = strict_host.finalize_after_exit()
            except (ContainmentCleanupError, OSError, RuntimeError):
                return _abort_after_launch_error(
                    step=step,
                    process=process,
                    strict_host=strict_host,
                    started=started,
                    started_at=started_at,
                    stdout_path=stdout_path,
                    stderr_path=stderr_path,
                    config=config,
                    environment=environment,
                )
            if not outcome.cleanup_verified:
                return _abort_after_launch_error(
                    step=step,
                    process=process,
                    strict_host=strict_host,
                    started=started,
                    started_at=started_at,
                    stdout_path=stdout_path,
                    stderr_path=stderr_path,
                    config=config,
                    environment=environment,
                )
            elif outcome.had_descendants:
                status, reason = "failed", "unexpected_descendant_process"
        elif status in {"succeeded", "failed"}:
            try:
                if _reap_unexpected_descendants_after_exit(process):
                    status, reason = "failed", "unexpected_descendant_process"
            except (OSError, RuntimeError):
                return _unquiescent_result(
                    step=step,
                    process=process,
                    started=started,
                    started_at=started_at,
                    stdout_path=stdout_path,
                    stderr_path=stderr_path,
                    config=config,
                    environment=environment,
                )
        try:
            if reason is None:
                if _directory_size(logs) > config.total_output_limit:
                    status, reason = "failed", "total_output_limit_exceeded"
                elif _directory_size(logs.parent) > config.disk_limit_bytes:
                    status, reason = "failed", "disk_limit_exceeded"
                else:
                    status = "succeeded" if process.returncode == 0 else "failed"
        except OSError:
            return _abort_after_launch_error(
                step=step,
                process=process,
                strict_host=strict_host,
                started=started,
                started_at=started_at,
                stdout_path=stdout_path,
                stderr_path=stderr_path,
                config=config,
                environment=environment,
            )
        if checkout_guard is not None:
            try:
                checkout_guard()
            except Exception:
                return _abort_after_launch_error(
                    step=step,
                    process=process,
                    strict_host=strict_host,
                    started=started,
                    started_at=started_at,
                    stdout_path=stdout_path,
                    stderr_path=stderr_path,
                    config=config,
                    environment=environment,
                )
    return _result(
        step=step,
        status=status,
        process=process,
        started=started,
        started_at=started_at,
        stdout_path=stdout_path,
        stderr_path=stderr_path,
        checkout=checkout,
        config=config,
        environment=environment,
        terminal_reason=reason,
        result_contract=result_contract,
        checkout_guard=checkout_guard,
    )


__all__ = [
    "CancellationToken",
    "OverallDeadlineExceededError",
    "StepResult",
    "environment_summary",
    "run_step",
]
