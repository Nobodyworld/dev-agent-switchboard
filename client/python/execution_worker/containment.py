# The launcher accepts only argv assembled from TrustedStep or fixed capability
# probes.  The child host validates a bounded serialized copy before execution.
# ruff: noqa: S603
"""Parent-side strict process containment for new public workload profiles."""

from __future__ import annotations

import ctypes
import json
import os
import signal
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import IO, BinaryIO

from .contained_host import (
    _HOST_CLEANUP_FAILURE,
    _HOST_DESCENDANT_REAPED,
    _HOST_SETUP_FAILURE,
)

_HOST_SCRIPT = Path(__file__).with_name("contained_host.py").resolve()
_MAX_PAYLOAD_BYTES = 64 * 1024
_JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE = 0x00002000
_JOB_OBJECT_EXTENDED_LIMIT_INFORMATION = 9
_JOB_OBJECT_BASIC_ACCOUNTING_INFORMATION = 1
_PROCESS_SET_QUOTA = 0x0100
_PROCESS_TERMINATE = 0x0001
_PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
_SYNCHRONIZE = 0x00100000
_POLL_SECONDS = 0.02


class ContainmentLaunchError(RuntimeError):
    """The trusted host could not be safely established before target launch."""


class ContainmentCleanupError(RuntimeError):
    """The platform did not prove that strict target descendants are gone."""


@dataclass(frozen=True, slots=True)
class ContainmentOutcome:
    """Post-host containment state consumed by the runner before evidence reads."""

    had_descendants: bool
    cleanup_verified: bool
    reason: str | None = None


if os.name == "nt":  # pragma: no branch - loaded on one platform per process
    from ctypes import wintypes

    _SIZE_T = ctypes.c_size_t

    class _IoCounters(ctypes.Structure):
        _fields_ = [
            ("ReadOperationCount", ctypes.c_ulonglong),
            ("WriteOperationCount", ctypes.c_ulonglong),
            ("OtherOperationCount", ctypes.c_ulonglong),
            ("ReadTransferCount", ctypes.c_ulonglong),
            ("WriteTransferCount", ctypes.c_ulonglong),
            ("OtherTransferCount", ctypes.c_ulonglong),
        ]

    class _JobObjectBasicLimitInformation(ctypes.Structure):
        _fields_ = [
            ("PerProcessUserTimeLimit", ctypes.c_longlong),
            ("PerJobUserTimeLimit", ctypes.c_longlong),
            ("LimitFlags", wintypes.DWORD),
            ("MinimumWorkingSetSize", _SIZE_T),
            ("MaximumWorkingSetSize", _SIZE_T),
            ("ActiveProcessLimit", wintypes.DWORD),
            ("Affinity", _SIZE_T),
            ("PriorityClass", wintypes.DWORD),
            ("SchedulingClass", wintypes.DWORD),
        ]

    class _JobObjectExtendedLimitInformation(ctypes.Structure):
        _fields_ = [
            ("BasicLimitInformation", _JobObjectBasicLimitInformation),
            ("IoInfo", _IoCounters),
            ("ProcessMemoryLimit", _SIZE_T),
            ("JobMemoryLimit", _SIZE_T),
            ("PeakProcessMemoryUsed", _SIZE_T),
            ("PeakJobMemoryUsed", _SIZE_T),
        ]

    class _JobObjectBasicAccountingInformation(ctypes.Structure):
        _fields_ = [
            ("TotalUserTime", ctypes.c_longlong),
            ("TotalKernelTime", ctypes.c_longlong),
            ("ThisPeriodTotalUserTime", ctypes.c_longlong),
            ("ThisPeriodTotalKernelTime", ctypes.c_longlong),
            ("TotalPageFaultCount", wintypes.DWORD),
            ("TotalProcesses", wintypes.DWORD),
            ("ActiveProcesses", wintypes.DWORD),
            ("TotalTerminatedProcesses", wintypes.DWORD),
        ]


class _WindowsJob:
    """One non-breakaway Windows Job Object held by the trusted parent runner."""

    def __init__(self, handle: int) -> None:
        self._handle = handle
        self._closed = False

    @staticmethod
    def _kernel32() -> object:
        if os.name != "nt":  # pragma: no cover - platform guard
            raise ContainmentLaunchError("Windows Job Objects are unavailable")
        win_dll = getattr(ctypes, "WinDLL", None)
        if win_dll is None:
            raise ContainmentLaunchError("Windows Job Objects are unavailable")
        return win_dll("kernel32", use_last_error=True)

    @classmethod
    def create(cls) -> _WindowsJob:
        kernel32 = cls._kernel32()
        create_job = kernel32.CreateJobObjectW  # type: ignore[attr-defined]
        create_job.argtypes = [ctypes.c_void_p, ctypes.c_wchar_p]
        create_job.restype = ctypes.c_void_p
        raw_handle = create_job(None, None)
        if not raw_handle:
            raise ContainmentLaunchError("Windows Job Object creation failed")
        job = cls(int(raw_handle))
        try:
            info = _JobObjectExtendedLimitInformation()
            info.BasicLimitInformation.LimitFlags = _JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
            set_information = kernel32.SetInformationJobObject  # type: ignore[attr-defined]
            set_information.argtypes = [
                ctypes.c_void_p,
                ctypes.c_int,
                ctypes.c_void_p,
                ctypes.c_ulong,
            ]
            set_information.restype = ctypes.c_bool
            if not set_information(
                ctypes.c_void_p(job._handle),
                _JOB_OBJECT_EXTENDED_LIMIT_INFORMATION,
                ctypes.byref(info),
                ctypes.sizeof(info),
            ):
                raise ContainmentLaunchError("Windows Job Object policy setup failed")
            # Absence of BREAKAWAY_OK / SILENT_BREAKAWAY_OK is deliberate.  Clear
            # inheritance as defense in depth; the runner remains the only holder.
            set_handle_information = kernel32.SetHandleInformation  # type: ignore[attr-defined]
            set_handle_information.argtypes = [
                ctypes.c_void_p,
                ctypes.c_ulong,
                ctypes.c_ulong,
            ]
            set_handle_information.restype = ctypes.c_bool
            if not set_handle_information(ctypes.c_void_p(job._handle), 1, 0):
                raise ContainmentLaunchError("Windows Job Object handle setup failed")
            return job
        except Exception:
            job.close()
            raise

    def _open_process(self, process_id: int) -> int:
        kernel32 = self._kernel32()
        open_process = kernel32.OpenProcess  # type: ignore[attr-defined]
        open_process.argtypes = [ctypes.c_ulong, ctypes.c_bool, ctypes.c_ulong]
        open_process.restype = ctypes.c_void_p
        access = (
            _PROCESS_SET_QUOTA
            | _PROCESS_TERMINATE
            | _PROCESS_QUERY_LIMITED_INFORMATION
            | _SYNCHRONIZE
        )
        raw_handle = open_process(access, False, process_id)
        if not raw_handle:
            raise ContainmentLaunchError("Windows host process handle setup failed")
        return int(raw_handle)

    def assign(self, process: subprocess.Popen[bytes]) -> None:
        """Assign the waiting host before its payload pipe receives target argv."""

        if not isinstance(getattr(process, "pid", None), int):
            raise ContainmentLaunchError("strict host has no process identifier")
        process_handle = self._open_process(process.pid)
        kernel32 = self._kernel32()
        close_handle = kernel32.CloseHandle  # type: ignore[attr-defined]
        close_handle.argtypes = [ctypes.c_void_p]
        close_handle.restype = ctypes.c_bool
        try:
            assign_process = kernel32.AssignProcessToJobObject  # type: ignore[attr-defined]
            assign_process.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
            assign_process.restype = ctypes.c_bool
            if not assign_process(
                ctypes.c_void_p(self._handle), ctypes.c_void_p(process_handle)
            ):
                raise ContainmentLaunchError(
                    "Windows strict host Job assignment failed"
                )
        finally:
            close_handle(ctypes.c_void_p(process_handle))

    def active_processes(self) -> int:
        if self._closed:
            return 0
        kernel32 = self._kernel32()
        accounting = _JobObjectBasicAccountingInformation()
        query = kernel32.QueryInformationJobObject  # type: ignore[attr-defined]
        query.argtypes = [
            ctypes.c_void_p,
            ctypes.c_int,
            ctypes.c_void_p,
            ctypes.c_ulong,
            ctypes.c_void_p,
        ]
        query.restype = ctypes.c_bool
        if not query(
            ctypes.c_void_p(self._handle),
            _JOB_OBJECT_BASIC_ACCOUNTING_INFORMATION,
            ctypes.byref(accounting),
            ctypes.sizeof(accounting),
            None,
        ):
            raise ContainmentCleanupError("Windows Job Object accounting failed")
        return int(accounting.ActiveProcesses)

    def terminate(self) -> None:
        if self._closed:
            return
        kernel32 = self._kernel32()
        terminate = kernel32.TerminateJobObject  # type: ignore[attr-defined]
        terminate.argtypes = [ctypes.c_void_p, ctypes.c_uint]
        terminate.restype = ctypes.c_bool
        if not terminate(ctypes.c_void_p(self._handle), 1):
            raise ContainmentCleanupError("Windows Job Object termination failed")

    def wait_for_zero(self, timeout_seconds: float) -> bool:
        deadline = time.monotonic() + max(timeout_seconds, 0.0)
        while True:
            if self.active_processes() == 0:
                return True
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                return False
            time.sleep(min(_POLL_SECONDS, remaining))

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        kernel32 = self._kernel32()
        close_handle = kernel32.CloseHandle  # type: ignore[attr-defined]
        close_handle.argtypes = [ctypes.c_void_p]
        close_handle.restype = ctypes.c_bool
        close_handle(ctypes.c_void_p(self._handle))


@dataclass(slots=True)
class StrictHostProcess:
    """A host process plus any Windows-only parent-held containment resource."""

    process: subprocess.Popen[bytes]
    _windows_job: _WindowsJob | None = None
    _finished: bool = False

    def terminate(self, *, grace_seconds: float = 2.0) -> None:
        """Stop a strict run through its containment boundary, never taskkill.

        Windows explicitly terminates the parent-held Job Object, which covers
        the blocked host and every inherited target descendant.  Linux signals
        the host's private session; its signal handler reaps its target group
        and adopted ``setsid`` descendants before it returns.
        """

        if self._windows_job is not None:
            job = self._windows_job
            try:
                job.terminate()
                self.process.wait(timeout=grace_seconds)
                if not job.wait_for_zero(grace_seconds):
                    raise ContainmentCleanupError(
                        "Windows Job Object did not quiesce after termination"
                    )
            except (
                ContainmentCleanupError,
                OSError,
                subprocess.TimeoutExpired,
            ) as error:
                # Closing the sole non-inherited Job handle requests the same
                # KILL_ON_JOB_CLOSE boundary even when accounting/waiting
                # failed.  The caller still treats source quiescence as
                # unproven and quarantines all target-owned paths.
                job.close()
                self._finished = True
                if isinstance(error, ContainmentCleanupError):
                    raise
                raise ContainmentCleanupError(
                    "Windows strict host did not terminate with its Job Object"
                ) from error
            return
        if self.process.poll() is not None:
            return
        kill_process_group = getattr(os, "killpg", None)
        if not callable(kill_process_group):
            raise ContainmentCleanupError(
                "Linux strict host process-group termination is unavailable"
            )
        try:
            kill_process_group(self.process.pid, signal.SIGTERM)
        except ProcessLookupError:
            return
        except OSError as error:
            raise ContainmentCleanupError(
                "Linux strict host process-group termination failed"
            ) from error
        try:
            self.process.wait(timeout=grace_seconds)
            return
        except subprocess.TimeoutExpired:
            pass
        try:
            kill_process_group(
                self.process.pid, getattr(signal, "SIGKILL", signal.SIGTERM)
            )
            self.process.wait(timeout=grace_seconds)
        except (OSError, subprocess.TimeoutExpired) as error:
            raise ContainmentCleanupError(
                "Linux strict host did not terminate"
            ) from error

    def finalize_after_exit(self, *, grace_seconds: float = 2.0) -> ContainmentOutcome:
        """Prove descendants are gone before caller reads parser/evidence paths."""

        if self._finished:
            return ContainmentOutcome(had_descendants=False, cleanup_verified=True)
        self._finished = True
        if self._windows_job is None:
            return _linux_host_outcome(self.process.returncode)
        job = self._windows_job
        try:
            # The host itself has exited.  Any remaining active process is a
            # descendant that the no-breakaway job must kill before evidence I/O.
            had_descendants = job.active_processes() > 0
            if had_descendants:
                job.terminate()
            verified = job.wait_for_zero(grace_seconds)
            return ContainmentOutcome(
                had_descendants=had_descendants,
                cleanup_verified=verified,
                reason=None if verified else "Windows Job Object did not quiesce",
            )
        except ContainmentCleanupError as error:
            return ContainmentOutcome(
                had_descendants=False,
                cleanup_verified=False,
                reason=str(error),
            )
        finally:
            job.close()

    def abandon_after_launch_failure(self) -> None:
        """Kill the host while it is still blocked without ever sending target argv."""

        if self._windows_job is not None:
            try:
                self._windows_job.terminate()
                self._windows_job.wait_for_zero(0.5)
            except ContainmentCleanupError:
                pass
            finally:
                self._windows_job.close()
        else:
            try:
                self.process.kill()
            except OSError:
                pass
        try:
            self.process.wait(timeout=0.5)
        except (OSError, subprocess.TimeoutExpired):
            pass


def _linux_host_outcome(return_code: int | None) -> ContainmentOutcome:
    """Translate closed trusted-host status codes after it has reaped children."""

    # A signal-directed host exit means target code may have killed or stopped
    # its subreaper before descendant cleanup completed.  Do not parse or clean
    # target-controlled paths on that ambiguous boundary.
    if return_code is None or return_code < 0:
        return ContainmentOutcome(
            had_descendants=True,
            cleanup_verified=False,
            reason="Linux strict host exited without descendant verification",
        )
    if return_code in {128 + int(signal.SIGINT), 128 + int(signal.SIGTERM)}:
        return ContainmentOutcome(
            had_descendants=True,
            cleanup_verified=False,
            reason="Linux strict host cleanup was interrupted by a signal",
        )
    if return_code == _HOST_DESCENDANT_REAPED:
        return ContainmentOutcome(had_descendants=True, cleanup_verified=True)
    if return_code == _HOST_CLEANUP_FAILURE:
        return ContainmentOutcome(
            had_descendants=True,
            cleanup_verified=False,
            reason="Linux strict host descendant cleanup failed",
        )
    if return_code == _HOST_SETUP_FAILURE:
        return ContainmentOutcome(
            had_descendants=False,
            cleanup_verified=False,
            reason="strict containment host setup failed",
        )
    return ContainmentOutcome(had_descendants=False, cleanup_verified=True)


def strict_containment_supported() -> bool:
    """Return whether this host has an implementation for the active platform."""

    return os.name == "nt" or sys.platform.startswith("linux")


def _payload(argv: tuple[str, ...]) -> bytes:
    try:
        encoded = json.dumps({"argv": list(argv)}, separators=(",", ":")).encode(
            "utf-8"
        )
    except (TypeError, UnicodeEncodeError) as error:
        raise ContainmentLaunchError(
            "strict host payload serialization failed"
        ) from error
    if len(encoded) > _MAX_PAYLOAD_BYTES:
        raise ContainmentLaunchError("strict host payload exceeds its input limit")
    return encoded


def _write_payload(stream: IO[bytes] | None, payload: bytes) -> None:
    if stream is None:
        raise ContainmentLaunchError("strict host has no payload pipe")
    try:
        stream.write(payload)
        stream.close()
    except (BrokenPipeError, OSError) as error:
        try:
            stream.close()
        except OSError:
            pass
        raise ContainmentLaunchError("strict host rejected its payload") from error


def launch_strict_host(
    *,
    argv: tuple[str, ...],
    cwd: Path,
    environment: dict[str, str],
    stdout: int | BinaryIO | None,
    stderr: int | BinaryIO | None,
) -> StrictHostProcess:
    """Launch the gated host and only then deliver the validated fixed argv.

    Windows Job assignment happens while the host is blocked on an empty stdin
    pipe.  Linux setup happens inside the host before it reads that pipe.  Both
    paths therefore fail closed before a target process can execute.
    """

    if not strict_containment_supported():
        raise ContainmentLaunchError("strict process containment is unsupported")
    if not _HOST_SCRIPT.is_file():
        raise ContainmentLaunchError("trusted strict host script is unavailable")
    payload = _payload(argv)
    windows_job = _WindowsJob.create() if os.name == "nt" else None
    strict_process: StrictHostProcess | None = None
    try:
        process = subprocess.Popen(
            [sys.executable, "-I", "-u", str(_HOST_SCRIPT)],
            cwd=cwd,
            env=environment,
            shell=False,
            stdin=subprocess.PIPE,
            stdout=stdout,
            stderr=stderr,
            start_new_session=os.name != "nt",
        )
        strict_process = StrictHostProcess(process=process, _windows_job=windows_job)
        if windows_job is not None:
            windows_job.assign(process)
        _write_payload(process.stdin, payload)
        return strict_process
    except (ContainmentLaunchError, OSError, subprocess.SubprocessError) as error:
        if strict_process is not None:
            strict_process.abandon_after_launch_failure()
        elif windows_job is not None:
            windows_job.close()
        if isinstance(error, ContainmentLaunchError):
            raise
        raise ContainmentLaunchError("strict host launch failed") from error


__all__ = [
    "ContainmentCleanupError",
    "ContainmentLaunchError",
    "ContainmentOutcome",
    "StrictHostProcess",
    "launch_strict_host",
    "strict_containment_supported",
]
