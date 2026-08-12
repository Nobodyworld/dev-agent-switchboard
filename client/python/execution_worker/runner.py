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
import threading
import time
from dataclasses import dataclass
from pathlib import Path

from server.execution.evidence import ParsedResult, TerminalStatus
from server.execution.registry import TrustedStep

from .config import WorkerConfig
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


def _result(  # noqa: PLR0913 - immutable result records keep call-site context clear
    *,
    step: TrustedStep,
    status: TerminalStatus,
    process: subprocess.Popen[bytes],
    started: float,
    started_at: dt.datetime,
    stdout_path: Path,
    stderr_path: Path,
    config: WorkerConfig,
    environment: dict[str, str],
    terminal_reason: str | None = None,
) -> StepResult:
    limit = min(step.output_summary_limit, config.output_summary_limit)
    out, out_cut = _summary(stdout_path, limit, config)
    err, err_cut = _summary(stderr_path, limit, config)
    finished_at = dt.datetime.now(dt.UTC)
    parsed_result = (
        parse_result(
            step.parser_kind,
            stdout_path=stdout_path,
            stderr_path=stderr_path,
            command_succeeded=status == "succeeded",
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


def run_step(  # noqa: PLR0912, PLR0913, PLR0915 - trusted lifecycle inputs are explicit
    step: TrustedStep,
    checkout: Path,
    logs: Path,
    config: WorkerConfig,
    deadline: float,
    *,
    cancellation: CancellationToken | None = None,
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
    cwd = (checkout / step.working_directory).resolve(strict=True)
    if checkout.resolve() not in (cwd, *cwd.parents):
        raise ValueError("trusted working directory escaped checkout")
    logs.mkdir(parents=True, exist_ok=True)
    stdout_path, stderr_path = (
        logs / f"{step.id}.stdout.log",
        logs / f"{step.id}.stderr.log",
    )
    environment = {
        key: os.environ[key]
        for key in config.inherited_environment_keys
        if key in os.environ
    }
    environment.update(dict(step.environment))
    step_deadline = time.monotonic() + min(
        float(step.timeout_seconds), config.maximum_step_timeout_seconds, remaining
    )
    started = time.monotonic()
    started_at = dt.datetime.now(dt.UTC)
    with stdout_path.open("wb") as stdout, stderr_path.open("wb") as stderr:
        process = subprocess.Popen(
            step.argv,
            cwd=cwd,
            env=environment,
            shell=False,
            stdout=stdout,
            stderr=stderr,
            start_new_session=os.name != "nt",
        )
        status: TerminalStatus = "failed"
        reason: str | None = None
        while process.poll() is None:
            now = time.monotonic()
            if cancellation is not None and cancellation.cancelled:
                status, reason = "cancelled", cancellation.reason
                _terminate(process)
                break
            if now >= deadline:
                status, reason = "timed_out", "overall_timeout"
                _terminate(process)
                break
            if now >= step_deadline:
                status, reason = "timed_out", "step_timeout"
                _terminate(process)
                break
            total_output = _directory_size(logs)
            if total_output > config.total_output_limit:
                status, reason = "failed", "total_output_limit_exceeded"
                _terminate(process)
                break
            run_directory = logs.parent
            if _directory_size(run_directory) > config.disk_limit_bytes:
                reason = (
                    "total_output_limit_exceeded"
                    if _directory_size(logs) > config.total_output_limit
                    else "disk_limit_exceeded"
                )
                status = "failed"
                _terminate(process)
                break
            time.sleep(0.02)
        if process.poll() is None:  # pragma: no cover - _terminate contract guard
            raise RuntimeError("trusted process did not terminate")
        if reason is None:
            if _directory_size(logs) > config.total_output_limit:
                status, reason = "failed", "total_output_limit_exceeded"
            elif _directory_size(logs.parent) > config.disk_limit_bytes:
                status, reason = "failed", "disk_limit_exceeded"
            else:
                status = "succeeded" if process.returncode == 0 else "failed"
    return _result(
        step=step,
        status=status,
        process=process,
        started=started,
        started_at=started_at,
        stdout_path=stdout_path,
        stderr_path=stderr_path,
        config=config,
        environment=environment,
        terminal_reason=reason,
    )


__all__ = [
    "CancellationToken",
    "OverallDeadlineExceededError",
    "StepResult",
    "environment_summary",
    "run_step",
]
