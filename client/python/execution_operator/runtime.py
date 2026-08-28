"""Marker-owned runtime creation, inspection, and atomic report writes."""

from __future__ import annotations

import json
import os
import stat
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
from .preflight import (
    PreflightResult,
    assert_no_reparse_ancestry,
    path_is_reparse,
)

MARKER_NAME = "operator-runtime.json"
REPORT_JSON_NAME = "operator-report.json"
REPORT_TEXT_NAME = "operator-report.txt"
_MAX_MARKER_BYTES = 16 * 1024
_MARKER_KEYS = {
    "schema_version",
    "runtime_id",
    "repository_full_name",
    "target_sha",
    "manifest_name",
    "manifest_version",
    "manifest_digest",
    "mode",
    "command_identity",
    "created_at",
}


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
    temporary_alt: Path
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
        temporary_alt=root / "tmp",
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


def _same_file_identity(first: os.stat_result, second: os.stat_result) -> bool:
    common = (
        first.st_dev,
        first.st_ino,
        first.st_mode,
        first.st_size,
        first.st_mtime_ns,
    ) == (
        second.st_dev,
        second.st_ino,
        second.st_mode,
        second.st_size,
        second.st_mtime_ns,
    )
    return common and (os.name == "nt" or first.st_ctime_ns == second.st_ctime_ns)


def _strict_json(data: bytes) -> object:
    def object_pairs(pairs: list[tuple[str, object]]) -> dict[str, object]:
        result: dict[str, object] = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("duplicate JSON key")
            result[key] = value
        return result

    def invalid_constant(_value: str) -> object:
        raise ValueError("invalid JSON constant")

    return json.loads(
        data.decode("utf-8"),
        object_pairs_hook=object_pairs,
        parse_constant=invalid_constant,
    )


def _read_json(path: Path, *, maximum: int) -> object:
    try:
        before = path.lstat()
        if (
            path_is_reparse(path)
            or not stat.S_ISREG(before.st_mode)
            or before.st_size > maximum
        ):
            raise OperatorLifecycleFailure("runtime_record_invalid")
        flags = os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0)
        descriptor = os.open(path, flags)
        try:
            opened = os.fstat(descriptor)
            if not stat.S_ISREG(opened.st_mode) or not _same_file_identity(
                before, opened
            ):
                raise OperatorLifecycleFailure("runtime_record_unstable")
            with os.fdopen(descriptor, "rb", closefd=False) as handle:
                raw = handle.read(maximum + 1)
            after = os.fstat(descriptor)
            if not _same_file_identity(before, after):
                raise OperatorLifecycleFailure("runtime_record_unstable")
        finally:
            os.close(descriptor)
        if len(raw) > maximum:
            raise OperatorLifecycleFailure("runtime_record_invalid")
        after_path = path.lstat()
        if path_is_reparse(path) or not _same_file_identity(before, after_path):
            raise OperatorLifecycleFailure("runtime_record_unstable")
        return _strict_json(raw)
    except OperatorLifecycleFailure:
        raise
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, ValueError) as error:
        raise OperatorLifecycleFailure("runtime_record_invalid") from error


def _read_runtime_summary(layout: RuntimeLayout) -> RuntimeSummary:
    payload = _read_json(layout.marker, maximum=_MAX_MARKER_BYTES)
    if not isinstance(payload, dict) or set(payload) != _MARKER_KEYS:
        raise OperatorLifecycleFailure("runtime_marker_invalid")
    try:
        summary = RuntimeSummary(**payload)
    except TypeError as error:
        raise OperatorLifecycleFailure("runtime_marker_invalid") from error
    validate_runtime_summary(summary)
    return summary


def _validate_runtime_layout(layout: RuntimeLayout) -> None:
    if not layout.root.is_absolute() or layout != _layout(layout.root):
        raise OperatorLifecycleFailure("runtime_root_invalid")
    assert_no_reparse_ancestry(layout.root, "runtime_root_reparse_ancestry")
    try:
        root_metadata = layout.root.lstat()
    except OSError as error:
        raise OperatorLifecycleFailure("runtime_root_invalid") from error
    if not stat.S_ISDIR(root_metadata.st_mode) or path_is_reparse(layout.root):
        raise OperatorLifecycleFailure("runtime_root_invalid")


def verify_runtime_ownership(
    layout: RuntimeLayout,
    expected: RuntimeSummary,
    *,
    destination: Path | None = None,
) -> RuntimeSummary:
    """Revalidate the exact original marker identity before an owned action."""

    try:
        _validate_runtime_layout(layout)
        assert_no_reparse_ancestry(layout.marker, "runtime_marker_reparse_ancestry")
        current = _read_runtime_summary(layout)
        if current != expected:
            raise OperatorLifecycleFailure("runtime_ownership_lost")
        if destination is not None:
            if not destination.is_absolute() or destination == layout.root:
                raise OperatorLifecycleFailure("runtime_ownership_lost")
            try:
                destination.relative_to(layout.root)
            except ValueError as error:
                raise OperatorLifecycleFailure("runtime_ownership_lost") from error
            assert_no_reparse_ancestry(
                destination.parent, "runtime_destination_reparse_ancestry"
            )
        return current
    except OperatorLifecycleFailure as error:
        if error.reason == "runtime_ownership_lost":
            raise
        raise OperatorLifecycleFailure("runtime_ownership_lost") from error


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
            command_identity="validation-lifecycle@1",
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
            layout.temporary_alt,
            layout.process_records,
        ):
            verify_runtime_ownership(layout, summary, destination=directory)
            directory.mkdir(exist_ok=False)
        return layout, summary
    except OperatorLifecycleFailure:
        raise
    except (OSError, ValueError) as error:
        raise OperatorLifecycleFailure("runtime_creation_failed") from error


def inspect_runtime(root: Path) -> tuple[RuntimeLayout, RuntimeSummary]:
    layout = _layout(root)
    _validate_runtime_layout(layout)
    assert_no_reparse_ancestry(layout.marker, "runtime_marker_reparse_ancestry")
    return layout, _read_runtime_summary(layout)


def write_report(
    layout: RuntimeLayout, report: OperatorLifecycleReport, *, maximum_bytes: int
) -> None:
    expected = report.runtime
    if expected is None:
        raise OperatorLifecycleFailure("runtime_ownership_lost")
    json_payload = report.as_json_bytes(maximum_bytes=maximum_bytes)
    text_payload = report.as_text(maximum_bytes=maximum_bytes)
    try:
        verify_runtime_ownership(
            layout,
            expected,
            destination=layout.reports / REPORT_JSON_NAME,
        )
        _atomic_write(
            layout.reports / REPORT_JSON_NAME,
            json_payload,
        )
        verify_runtime_ownership(
            layout,
            expected,
            destination=layout.reports / REPORT_TEXT_NAME,
        )
        _atomic_write(
            layout.reports / REPORT_TEXT_NAME,
            text_payload,
        )
    except OperatorLifecycleFailure:
        raise
    except OSError as error:
        raise OperatorLifecycleFailure("report_write_failed") from error


def touch_owned_stop(
    layout: RuntimeLayout, expected: RuntimeSummary, path: Path
) -> None:
    verify_runtime_ownership(layout, expected, destination=path)
    if path not in {layout.stop_server, layout.stop_worker}:
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
    "verify_runtime_ownership",
    "write_report",
]
