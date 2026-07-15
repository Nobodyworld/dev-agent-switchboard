"""Fixed-argv process execution with bounded redacted summaries."""

from __future__ import annotations

import os
import signal
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path

from server.execution.registry import TrustedStep

from .config import WorkerConfig


@dataclass(frozen=True, slots=True)
class StepResult:
    step_id: str
    status: str
    exit_code: int | None
    duration_seconds: float
    stdout_summary: str
    stderr_summary: str
    summaries_truncated: bool
    stdout_log: str
    stderr_log: str


def _redact(value: str, config: WorkerConfig) -> str:
    for pattern in config.redacted_value_patterns:
        if pattern:
            value = value.replace(pattern, "[REDACTED]")
    return value


def _summary(path: Path, limit: int, config: WorkerConfig) -> tuple[str, bool]:
    data = path.read_bytes()
    text = data[:limit].decode("utf-8", errors="replace")
    return _redact(text, config), len(data) > limit


def _terminate(process: subprocess.Popen[bytes]) -> None:
    if os.name == "nt":
        subprocess.run(
            ["taskkill", "/PID", str(process.pid), "/T", "/F"],
            shell=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        )
    else:
        os.killpg(process.pid, signal.SIGTERM)  # type: ignore[attr-defined]
        try:
            process.wait(timeout=2)
        except subprocess.TimeoutExpired:
            os.killpg(  # type: ignore[attr-defined]
                process.pid,
                signal.SIGKILL,  # type: ignore[attr-defined]
            )


def run_step(
    step: TrustedStep, checkout: Path, logs: Path, config: WorkerConfig, deadline: float
) -> StepResult:
    """Run only one locally resolved reviewed step; no caller argv is accepted."""
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
    timeout = min(
        float(step.timeout_seconds),
        config.maximum_step_timeout_seconds,
        max(0.01, deadline - time.monotonic()),
    )
    started = time.monotonic()
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
        try:
            process.wait(timeout=timeout)
            status = "succeeded" if process.returncode == 0 else "failed"
        except subprocess.TimeoutExpired:
            _terminate(process)
            process.wait()
            status = "timed_out"
    out, out_cut = _summary(
        stdout_path, min(step.output_summary_limit, config.output_summary_limit), config
    )
    err, err_cut = _summary(
        stderr_path, min(step.output_summary_limit, config.output_summary_limit), config
    )
    return StepResult(
        step.id,
        status,
        process.returncode,
        time.monotonic() - started,
        out,
        err,
        out_cut or err_cut,
        stdout_path.name,
        stderr_path.name,
    )
