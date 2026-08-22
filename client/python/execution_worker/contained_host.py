# This module is intentionally standard-library only: it is executed from an
# absolute trusted worker path while the target checkout is the current directory.
# ruff: noqa: S603
"""Gated strict-containment child host for reviewed public workload steps.

The parent starts this module with an empty stdin pipe.  It establishes the
platform-specific boundary *before* it accepts a small, validated argv payload,
so a target command cannot run when the boundary is unavailable.
"""

from __future__ import annotations

import ctypes
import errno
import json
import os
import signal
import subprocess
import sys
import time
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

_MAX_PAYLOAD_BYTES = 64 * 1024
_MAX_ARGUMENT_COUNT = 128
_MAX_ARGUMENT_BYTES = 16 * 1024
_CLEANUP_TIMEOUT_SECONDS = 2.0
_POLL_SECONDS = 0.02
_LINUX_STAT_REQUIRED_FIELDS = 3
_PR_SET_CHILD_SUBREAPER = 36
_PR_GET_CHILD_SUBREAPER = 37

# These codes are emitted only by the trusted host.  The parent maps them to a
# terminal reason after the host has exited; a reviewed command normally does
# not use them, and either interpretation is still a failed public workload.
_HOST_SETUP_FAILURE = 125
_HOST_DESCENDANT_REAPED = 126
_HOST_CLEANUP_FAILURE = 127
_HOST_TERMINATED_CLEAN = 124


class _HostError(RuntimeError):
    """The host cannot safely accept or run the requested command."""


class _TerminationRequested(BaseException):
    """Raised only from a POSIX host signal handler to run cleanup first."""


@dataclass(frozen=True, slots=True)
class _ProcessRecord:
    process_id: int
    parent_process_id: int
    process_group_id: int
    state: str


def _write_failure() -> None:
    """Keep host diagnostics generic: target argv and inherited env stay private."""

    try:
        sys.stderr.write("strict containment host failed\n")
        sys.stderr.flush()
    except OSError:  # pragma: no cover - stdout/stderr can be closed by a caller
        pass


def _read_payload() -> tuple[str, ...]:
    """Read exactly one bounded fixed-argv JSON payload from the trusted parent."""

    raw = sys.stdin.buffer.read(_MAX_PAYLOAD_BYTES + 1)
    if len(raw) > _MAX_PAYLOAD_BYTES:
        raise _HostError("payload exceeds bounded host input")
    try:
        payload = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise _HostError("payload is not valid UTF-8 JSON") from error
    if not isinstance(payload, Mapping) or set(payload) != {"argv"}:
        raise _HostError("payload shape is invalid")
    argv = payload["argv"]
    if not isinstance(argv, list) or not argv or len(argv) > _MAX_ARGUMENT_COUNT:
        raise _HostError("argv shape is invalid")
    if not all(isinstance(argument, str) for argument in argv):
        raise _HostError("argv contains a non-string")
    if any(
        not argument
        or "\x00" in argument
        or len(argument.encode("utf-8")) > _MAX_ARGUMENT_BYTES
        for argument in argv
    ):
        raise _HostError("argv value is invalid")
    return tuple(argv)


def _establish_linux_subreaper() -> None:
    """Become a Linux child subreaper before accepting the target payload."""

    if not sys.platform.startswith("linux"):
        raise _HostError("Linux subreaper containment is unavailable")
    proc_self = Path("/proc/self/stat")
    if not proc_self.is_file():
        raise _HostError("Linux process inspection is unavailable")
    try:
        libc = ctypes.CDLL(None, use_errno=True)
        prctl = libc.prctl
        prctl.argtypes = [
            ctypes.c_int,
            ctypes.c_ulong,
            ctypes.c_ulong,
            ctypes.c_ulong,
            ctypes.c_ulong,
        ]
        prctl.restype = ctypes.c_int
    except (AttributeError, OSError) as error:
        raise _HostError("Linux prctl subreaper is unavailable") from error

    if prctl(_PR_SET_CHILD_SUBREAPER, 1, 0, 0, 0) != 0:
        raise _HostError("Linux subreaper setup failed")
    enabled = ctypes.c_int(0)
    # Passing a pointer through c_ulong avoids platform-dependent varargs use.
    if (
        prctl(
            _PR_GET_CHILD_SUBREAPER,
            ctypes.cast(ctypes.byref(enabled), ctypes.c_void_p).value or 0,
            0,
            0,
            0,
        )
        != 0
        or enabled.value != 1
    ):
        raise _HostError("Linux subreaper verification failed")


def _parse_linux_stat(value: str, process_id: int) -> _ProcessRecord | None:
    """Return only the `/proc/<pid>/stat` fields needed for descendant cleanup."""

    command_end = value.rfind(")")
    fields = value[command_end + 2 :].split() if command_end >= 0 else []
    # state, ppid, pgrp are the first three fields after the command.
    if len(fields) < _LINUX_STAT_REQUIRED_FIELDS:
        return None
    try:
        return _ProcessRecord(
            process_id=process_id,
            state=fields[0],
            parent_process_id=int(fields[1]),
            process_group_id=int(fields[2]),
        )
    except ValueError:
        return None


def _linux_process_table() -> dict[int, _ProcessRecord]:
    """Read one bounded process table snapshot or fail closed when it is unreliable."""

    process_root = Path("/proc")
    try:
        entries = tuple(process_root.iterdir())
    except OSError as error:
        raise _HostError("Linux process inspection failed") from error
    records: dict[int, _ProcessRecord] = {}
    for entry in entries:
        if not entry.name.isdecimal():
            continue
        try:
            process_id = int(entry.name)
            value = (entry / "stat").read_text(encoding="utf-8", errors="replace")
        except (FileNotFoundError, ProcessLookupError):
            continue
        except OSError as error:
            if error.errno in {errno.ENOENT, errno.ESRCH}:
                continue
            raise _HostError("Linux process inspection failed") from error
        record = _parse_linux_stat(value, process_id)
        if record is None:
            raise _HostError("Linux process inspection was malformed")
        records[process_id] = record
    return records


def _linux_descendants(parent_process_id: int) -> dict[int, _ProcessRecord]:
    """Find all descendants of the subreaper from one coherent `/proc` snapshot."""

    records = _linux_process_table()
    children: dict[int, list[_ProcessRecord]] = {}
    for record in records.values():
        children.setdefault(record.parent_process_id, []).append(record)
    pending = [parent_process_id]
    descendants: dict[int, _ProcessRecord] = {}
    while pending:
        parent = pending.pop()
        for child in children.get(parent, []):
            if child.process_id in descendants:
                continue
            descendants[child.process_id] = child
            pending.append(child.process_id)
    return descendants


def _reap_adopted_children() -> None:
    """Reap every already-terminated child the subreaper has adopted."""

    waitpid = getattr(os, "waitpid", None)
    nohang = getattr(os, "WNOHANG", None)
    if not callable(waitpid) or not isinstance(nohang, int):
        raise _HostError("Linux child reaping is unavailable")
    while True:
        try:
            process_id, _status = waitpid(-1, nohang)
        except ChildProcessError:
            return
        if process_id == 0:
            return


def _signal_process_group(process_group_id: int, signal_number: signal.Signals) -> bool:
    kill_process_group = getattr(os, "killpg", None)
    if not callable(kill_process_group):
        raise _HostError("Linux process-group cleanup is unavailable")
    try:
        kill_process_group(process_group_id, signal_number)
    except ProcessLookupError:
        return False
    except OSError as error:
        raise _HostError("Linux process-group cleanup failed") from error
    return True


def _signal_process(process_id: int, signal_number: signal.Signals) -> bool:
    try:
        os.kill(process_id, signal_number)
    except ProcessLookupError:
        return False
    except OSError as error:
        raise _HostError("Linux descendant cleanup failed") from error
    return True


def _process_group_exists(process_group_id: int) -> bool:
    kill_process_group = getattr(os, "killpg", None)
    if not callable(kill_process_group):
        raise _HostError("Linux process-group inspection is unavailable")
    try:
        kill_process_group(process_group_id, 0)
    except ProcessLookupError:
        return False
    except OSError as error:
        raise _HostError("Linux process-group inspection failed") from error
    return True


def _cleanup_linux_target(  # noqa: PLR0912 - ordered containment state is explicit
    process_group_id: int, *, expected_primary_process_id: int | None = None
) -> bool:
    """Kill/reap target descendants, including children that called ``setsid``.

    The target starts a fresh process group.  Once it exits, this host is a
    subreaper, so a detached descendant becomes a child of this host and shows
    up in the explicit `/proc` ancestry walk instead of escaping the normal
    process-group cleanup.
    """

    # A target knows this host's PID through its parent relationship.  Ignore
    # TERM/INT while proving quiescence so an adopted ``setsid`` child cannot
    # interrupt the cleanup loop and turn a partially cleaned tree into a
    # signal-shaped successful host exit.  SIGKILL remains uncatchable and is
    # deliberately handled as unverified by the parent.
    previous_handlers = {
        signal.SIGTERM: signal.signal(signal.SIGTERM, signal.SIG_IGN),
        signal.SIGINT: signal.signal(signal.SIGINT, signal.SIG_IGN),
    }
    try:
        observed = _process_group_exists(process_group_id)
        if observed:
            _signal_process_group(process_group_id, signal.SIGTERM)
        had_unexpected_descendants = False
        deadline = time.monotonic() + _CLEANUP_TIMEOUT_SECONDS
        force_after = time.monotonic() + min(0.25, _CLEANUP_TIMEOUT_SECONDS / 2)
        force = False
        while True:
            _reap_adopted_children()
            descendants = _linux_descendants(os.getpid())
            live_descendants = {
                process_id: record
                for process_id, record in descendants.items()
                if record.state not in {"X", "x", "Z"}
            }
            if expected_primary_process_id is not None:
                # The host itself was deliberately signalled while its reviewed
                # primary target was still alive.  Terminating that one process
                # is expected; a sibling or child remains an unexpected target
                # descendant and must still make the step fail.
                live_descendants.pop(expected_primary_process_id, None)
            if live_descendants:
                had_unexpected_descendants = True
            group_exists = _process_group_exists(process_group_id)
            if not live_descendants and not group_exists:
                _reap_adopted_children()
                # One final snapshot avoids accepting a descendant that appeared
                # during the preceding reap loop.
                if not _linux_descendants(os.getpid()):
                    if expected_primary_process_id is None and observed:
                        return True
                    return had_unexpected_descendants
                continue

            if expected_primary_process_id is None:
                observed = True
            now = time.monotonic()
            if now >= force_after:
                force = True
            if force:
                signal_number = getattr(signal, "SIGKILL", signal.SIGTERM)
            else:
                signal_number = signal.SIGTERM
            if group_exists:
                _signal_process_group(process_group_id, signal_number)
            for process_id in live_descendants:
                _signal_process(process_id, signal_number)
            if now >= deadline:
                raise _HostError("Linux descendant cleanup timed out")
            time.sleep(min(_POLL_SECONDS, deadline - now))
    finally:
        for signal_number, previous_handler in previous_handlers.items():
            signal.signal(signal_number, previous_handler)


def _install_linux_termination_handler() -> None:
    """Turn parent termination into ordered target cleanup, not host abandonment."""

    def request_cleanup(_signum: int, _frame: object) -> None:
        raise _TerminationRequested

    signal.signal(signal.SIGTERM, request_cleanup)
    signal.signal(signal.SIGINT, request_cleanup)


def _exit_code(return_code: int) -> int:
    """Preserve ordinary child status as closely as a Python host can portably do."""

    if return_code >= 0:
        return min(return_code, 255)
    return min(128 + abs(return_code), 255)


def _run_target(argv: tuple[str, ...]) -> int:
    """Run the reviewed argv only after the boundary and payload checks complete."""

    process = subprocess.Popen(
        argv,
        cwd=os.getcwd(),
        env=dict(os.environ),
        shell=False,
        stdin=subprocess.DEVNULL,
        # The parent redirects this host's streams to bounded step logs.
        stdout=None,
        stderr=None,
        start_new_session=sys.platform.startswith("linux"),
    )
    try:
        return_code = process.wait()
    except _TerminationRequested:
        if sys.platform.startswith("linux"):
            try:
                had_descendants = _cleanup_linux_target(
                    process.pid, expected_primary_process_id=process.pid
                )
            except _HostError:
                return _HOST_CLEANUP_FAILURE
            if had_descendants:
                return _HOST_DESCENDANT_REAPED
            return _HOST_TERMINATED_CLEAN
        raise
    if sys.platform.startswith("linux"):
        try:
            had_descendants = _cleanup_linux_target(process.pid)
        except _HostError:
            return _HOST_CLEANUP_FAILURE
        if had_descendants:
            return _HOST_DESCENDANT_REAPED
    return _exit_code(return_code)


def main() -> int:
    """Execute one payload or report a closed, generic host failure."""

    try:
        if sys.platform.startswith("linux"):
            _establish_linux_subreaper()
            _install_linux_termination_handler()
        elif os.name != "nt":
            raise _HostError("strict containment is unsupported on this platform")
        argv = _read_payload()
        return _run_target(argv)
    except _TerminationRequested:
        return 128 + int(signal.SIGTERM)
    except (_HostError, OSError, subprocess.SubprocessError):
        _write_failure()
        return _HOST_SETUP_FAILURE


if __name__ == "__main__":  # pragma: no cover - exercised through the parent runner
    raise SystemExit(main())
