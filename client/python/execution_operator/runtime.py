"""Marker-owned runtime creation, inspection, and atomic report writes."""

from __future__ import annotations

import json
import os
import uuid
from dataclasses import asdict, dataclass
from pathlib import Path

from .config import OperatorLifecycleConfig
from .models import (
    OperatorLifecycleFailure,
    OperatorLifecycleReport,
    RuntimeSummary,
    utc_now_text,
    validate_runtime_summary,
)
from .preflight import PreflightResult

MARKER_NAME = "operator-runtime.json"
REPORT_JSON_NAME = "operator-report.json"
REPORT_TEXT_NAME = "operator-report.txt"
_MAX_MARKER_BYTES = 16 * 1024


@dataclass(frozen=True, slots=True)
class RuntimeLayout:
    root: Path
    marker: Path
    database: Path
    server_storage: Path
    file_storage: Path
    worker_source: Path
    retained_evidence: Path
    reports: Path
    temporary: Path
    process_records: Path
    stop_server: Path
    stop_worker: Path
    worker_config: Path


def _layout(root: Path) -> RuntimeLayout:
    return RuntimeLayout(
        root=root,
        marker=root / MARKER_NAME,
        database=root / "database" / "switchboard.db",
        server_storage=root / "server-storage",
        file_storage=root / "file-storage",
        worker_source=root / "worker-source",
        retained_evidence=root / "retained-evidence",
        reports=root / "reports",
        temporary=root / "temp",
        process_records=root / "processes",
        stop_server=root / "processes" / "stop-server",
        stop_worker=root / "processes" / "stop-worker",
        worker_config=root / "worker-config.json",
    )


def _atomic_write(path: Path, data: bytes, *, exclusive: bool = False) -> None:
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    descriptor = os.open(temporary, flags, 0o600)
    try:
        with os.fdopen(descriptor, "wb", closefd=True) as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        if exclusive and path.exists():
            raise FileExistsError(path.name)
        os.replace(temporary, path)
    except Exception:
        try:
            temporary.unlink(missing_ok=True)
        except OSError:
            pass
        raise


def _read_json(path: Path, *, maximum: int) -> object:
    try:
        if path.is_symlink() or not path.is_file() or path.stat().st_size > maximum:
            raise OperatorLifecycleFailure("runtime_record_invalid")
        raw = path.read_bytes()
        if len(raw) > maximum:
            raise OperatorLifecycleFailure("runtime_record_invalid")
        return json.loads(raw.decode("utf-8"))
    except OperatorLifecycleFailure:
        raise
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise OperatorLifecycleFailure("runtime_record_invalid") from error


def create_runtime(
    config: OperatorLifecycleConfig, preflight: PreflightResult
) -> tuple[RuntimeLayout, RuntimeSummary]:
    """Create one new root and write its ownership marker before subdirectories."""

    try:
        config.runtime_root.mkdir(parents=False, exist_ok=False)
        summary = RuntimeSummary(
            schema_version=1,
            runtime_id=str(uuid.uuid4()),
            repository_full_name=config.repository_full_name,
            target_sha=config.target_sha,
            manifest_name=config.manifest_name,
            manifest_version=config.manifest_version,
            manifest_digest=preflight.manifest_digest,
            mode=config.mode,
            created_at=utc_now_text(),
        )
        validate_runtime_summary(summary)
        layout = _layout(config.runtime_root)
        marker_bytes = json.dumps(
            asdict(summary), sort_keys=True, separators=(",", ":")
        ).encode("utf-8")
        _atomic_write(layout.marker, marker_bytes, exclusive=True)
        for directory in (
            layout.database.parent,
            layout.server_storage,
            layout.file_storage,
            layout.worker_source,
            layout.retained_evidence,
            layout.reports,
            layout.temporary,
            layout.process_records,
        ):
            directory.mkdir(exist_ok=False)
        return layout, summary
    except OperatorLifecycleFailure:
        raise
    except (OSError, ValueError) as error:
        raise OperatorLifecycleFailure("runtime_creation_failed") from error


def inspect_runtime(root: Path) -> tuple[RuntimeLayout, RuntimeSummary]:
    if not root.is_absolute() or root.is_symlink() or not root.is_dir():
        raise OperatorLifecycleFailure("runtime_root_invalid")
    layout = _layout(root)
    payload = _read_json(layout.marker, maximum=_MAX_MARKER_BYTES)
    if not isinstance(payload, dict) or set(payload) != {
        "schema_version",
        "runtime_id",
        "repository_full_name",
        "target_sha",
        "manifest_name",
        "manifest_version",
        "manifest_digest",
        "mode",
        "created_at",
    }:
        raise OperatorLifecycleFailure("runtime_marker_invalid")
    try:
        summary = RuntimeSummary(**payload)
    except TypeError as error:
        raise OperatorLifecycleFailure("runtime_marker_invalid") from error
    validate_runtime_summary(summary)
    return layout, summary


def write_report(
    layout: RuntimeLayout, report: OperatorLifecycleReport, *, maximum_bytes: int
) -> None:
    inspected, expected = inspect_runtime(layout.root)
    if inspected.marker != layout.marker or report.runtime != expected:
        raise OperatorLifecycleFailure("runtime_ownership_lost")
    try:
        _atomic_write(
            layout.reports / REPORT_JSON_NAME,
            report.as_json_bytes(maximum_bytes=maximum_bytes),
        )
        _atomic_write(
            layout.reports / REPORT_TEXT_NAME,
            report.as_text(maximum_bytes=maximum_bytes),
        )
    except OperatorLifecycleFailure:
        raise
    except OSError as error:
        raise OperatorLifecycleFailure("report_write_failed") from error


def touch_owned_stop(layout: RuntimeLayout, path: Path) -> None:
    inspected, _summary = inspect_runtime(layout.root)
    if inspected != layout or path not in {layout.stop_server, layout.stop_worker}:
        raise OperatorLifecycleFailure("runtime_ownership_lost")
    try:
        _atomic_write(path, b"stop\n", exclusive=True)
    except FileExistsError:
        return
    except OSError as error:
        raise OperatorLifecycleFailure("shutdown_signal_failed") from error


__all__ = [
    "MARKER_NAME",
    "REPORT_JSON_NAME",
    "REPORT_TEXT_NAME",
    "RuntimeLayout",
    "create_runtime",
    "inspect_runtime",
    "touch_owned_stop",
    "write_report",
]
