"""Small bounded parsers selected only by reviewed trusted manifest steps."""

from __future__ import annotations

import json
import os
import re
import stat
from collections.abc import Mapping
from pathlib import Path, PurePosixPath
from typing import Any, Literal, cast

from server.execution.evidence import (
    AuditSummary,
    ParsedCoverage,
    ParsedResult,
    ParsedTestCounts,
    ParserKind,
)

_MAX_PARSE_BYTES = 1024 * 1024
_MAX_QUALITY_SUMMARY_BYTES = 128 * 1024
_MAX_QUALITY_COVERAGE_BYTES = 2 * 1024 * 1024
_MAX_RESULT_RECORDS = 10_000_000
_MAX_COVERAGE_PERCENT = 100
_QUALITY_COVERAGE_THRESHOLD = 85
_BANDIT_MANAGER_ERROR = "[manager]\tERROR\t"
_PYTEST_COUNTS = {
    "passed": re.compile(r"(?P<count>\d+) passed\b"),
    "failed": re.compile(r"(?P<count>\d+) failed\b"),
    "skipped": re.compile(r"(?P<count>\d+) skipped\b"),
    "errors": re.compile(r"(?P<count>\d+) errors?\b"),
    "xfailed": re.compile(r"(?P<count>\d+) xfailed\b"),
    "xpassed": re.compile(r"(?P<count>\d+) xpassed\b"),
}
_QUALITY_OPERATIONS = (
    "format-check",
    "lint",
    "type",
    "frontend-install",
    "frontend-format",
    "frontend-lint",
    "frontend-typecheck",
    "frontend-tests",
    "frontend-build",
    "repository-safety",
    "snapshot-store",
    "workspace-api",
    "packaged-workspace",
    "helper-surface",
    "helper-boundary",
    "helper-compatibility",
    "bandit",
    "audit",
    "binary",
    "tests",
    "coverage",
    "docs",
    "editable-smoke",
    "wheel",
    "zipapp",
    "diagnostics",
)
_RESULT_CONTRACT_FIELDS = frozenset(
    {
        "failure_conditions",
        "maximum_parsed_bytes",
        "maximum_parsed_records",
        "minimum_coverage_percent",
        "minimum_test_count",
        "parser_kind",
        "required_summary_fields",
        "source",
        "source_path",
    }
)
_RESULT_CONTRACT_FAILURES = {
    "dependency-audit": frozenset({"dependency-vulnerability"}),
    "dependency-health": frozenset({"dependency-health"}),
    "pytest": frozenset({"test-failure"}),
    "pytest-coverage": frozenset({"coverage-threshold", "test-failure"}),
    "quality-summary-v1": frozenset(
        {"coverage-threshold", "quality-operation-failure"}
    ),
    "secret-scan": frozenset({"baseline-validation"}),
}


def _combined(stdout_path: Path, stderr_path: Path, maximum_bytes: int) -> str:
    """Read both streams under one aggregate byte budget plus one overflow byte."""

    chunks: list[bytes] = []
    remaining = maximum_bytes + 1
    for path in (stdout_path, stderr_path):
        with path.open("rb") as handle:
            chunk = handle.read(remaining)
        chunks.append(chunk)
        remaining -= len(chunk)
        if remaining == 0:
            break
    if sum(len(chunk) for chunk in chunks) > maximum_bytes:
        raise ValueError("declared result streams exceed their aggregate byte limit")
    chunks.extend(b"" for _ in range(2 - len(chunks)))
    return "\n".join(chunk.decode("utf-8", errors="replace") for chunk in chunks)


def _pytest_counts(text: str) -> ParsedTestCounts | None:
    counts: dict[str, int] = {}
    for name, pattern in _PYTEST_COUNTS.items():
        matches = list(pattern.finditer(text))
        counts[name] = int(matches[-1].group("count")) if matches else 0
    total = sum(counts.values())
    if total == 0:
        return None
    return ParsedTestCounts(total=total, **counts)


def _coverage(text: str) -> ParsedCoverage | None:
    for line in reversed(text.splitlines()):
        normalized = line.strip()
        if not (
            normalized.startswith("TOTAL") or "line coverage" in normalized.lower()
        ):
            continue
        matches = list(re.finditer(r"(?P<percent>\d+(?:\.\d+)?)%", normalized))
        match = matches[0] if matches else None
        if match:
            return ParsedCoverage(measured_percent=float(match.group("percent")))
    return None


def _is_reparse(metadata: os.stat_result) -> bool:
    attributes = getattr(metadata, "st_file_attributes", 0)
    reparse = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
    return stat.S_ISLNK(metadata.st_mode) or bool(attributes & reparse)


def _same_file_identity(first: os.stat_result, second: os.stat_result) -> bool:
    same = (
        first.st_dev,
        first.st_ino,
        first.st_size,
        first.st_mtime_ns,
    ) == (
        second.st_dev,
        second.st_ino,
        second.st_size,
        second.st_mtime_ns,
    )
    # Windows exposes different ctime precision through lstat and a handle.
    return same and (os.name == "nt" or first.st_ctime_ns == second.st_ctime_ns)


def _result_path_parts(relative_path: str) -> tuple[str, ...]:
    path = PurePosixPath(relative_path)
    if (
        not path.parts
        or path.is_absolute()
        or any(part in {"", ".", ".."} for part in path.parts)
    ):
        raise ValueError("declared result report path is invalid")
    return path.parts


def _assert_regular_checkout_root(checkout: Path) -> Path:
    root = Path(os.path.abspath(checkout))
    metadata = os.lstat(root)
    if _is_reparse(metadata) or not stat.S_ISDIR(metadata.st_mode):
        raise ValueError("declared result checkout is not a regular directory")
    return root


def _open_posix_report(root: Path, parts: tuple[str, ...]) -> int:
    """Open one fixed report through no-follow directory handles on POSIX."""

    directory_flags = (
        os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0)
    )
    if not getattr(os, "O_DIRECTORY", 0) or not getattr(os, "O_NOFOLLOW", 0):
        raise ValueError("safe result report traversal is unavailable")
    descriptors: list[int] = []
    try:
        descriptors.append(os.open(root, directory_flags))
        for part in parts[:-1]:
            descriptors.append(os.open(part, directory_flags, dir_fd=descriptors[-1]))
        file_flags = (
            os.O_RDONLY | getattr(os, "O_NONBLOCK", 0) | getattr(os, "O_NOFOLLOW", 0)
        )
        return os.open(parts[-1], file_flags, dir_fd=descriptors[-1])
    except OSError as error:
        raise ValueError("declared result report could not be opened safely") from error
    finally:
        for descriptor in reversed(descriptors):
            os.close(descriptor)


def _open_windows_report(root: Path, parts: tuple[str, ...]) -> tuple[int, Path]:
    """Use the available no-follow leaf check on Windows reparse paths."""

    path = root.joinpath(*parts)
    current = root
    for part in parts:
        current /= part
        if _is_reparse(os.lstat(current)):
            raise ValueError("declared result report contains a link or reparse point")
    flags = os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NONBLOCK", 0)
    try:
        return os.open(path, flags), path
    except OSError as error:
        raise ValueError("declared result report could not be opened safely") from error


def _contained_regular_file(
    checkout: Path, relative_path: str, maximum_bytes: int
) -> bytes:
    """Read one reviewed regular report through a bounded verified descriptor."""

    root = _assert_regular_checkout_root(checkout)
    parts = _result_path_parts(relative_path)
    path: Path | None = None
    if os.name == "nt":
        descriptor, path = _open_windows_report(root, parts)
    else:
        descriptor = _open_posix_report(root, parts)
    try:
        before = os.fstat(descriptor)
        if not stat.S_ISREG(before.st_mode):
            raise ValueError("declared result report is not a regular file")
        if before.st_size > maximum_bytes:
            raise ValueError("declared result report exceeds its byte limit")
        with os.fdopen(descriptor, "rb", closefd=False) as handle:
            data = handle.read(maximum_bytes + 1)
        if len(data) > maximum_bytes:
            raise ValueError("declared result report exceeds its byte limit")
        after = os.fstat(descriptor)
        if not _same_file_identity(before, after):
            raise ValueError("declared result report changed while being read")
    finally:
        os.close(descriptor)
    if path is not None:
        after_path = os.lstat(path)
        if _is_reparse(after_path) or not _same_file_identity(before, after_path):
            raise ValueError("declared result report changed while being read")
    return data


def _json_report(
    checkout: Path, relative_path: str, maximum_bytes: int
) -> dict[str, Any]:
    raw = _contained_regular_file(checkout, relative_path, maximum_bytes)
    loaded = json.loads(raw.decode("utf-8"))
    if not isinstance(loaded, dict):
        raise ValueError("declared result report must contain an object")
    return loaded


def _bounded_number(value: object, *, minimum: float, maximum: float) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError("declared result value is not numeric")
    number = float(value)
    if not minimum <= number <= maximum:
        raise ValueError("declared result value is out of bounds")
    return number


def _validated_result_contract(  # noqa: PLR0912 - closed validation remains explicit
    result_contract: Mapping[str, object] | None,
    parser_kind: ParserKind,
) -> Mapping[str, object] | None:
    """Validate the closed, source-controlled per-step parser descriptor."""

    if result_contract is None:
        return None
    if set(result_contract) != _RESULT_CONTRACT_FIELDS:
        raise ValueError("trusted result contract fields are invalid")
    if result_contract["parser_kind"] != parser_kind:
        raise ValueError("trusted result contract parser kind is invalid")
    source = result_contract["source"]
    source_path = result_contract["source_path"]
    if parser_kind == "quality-summary-v1":
        if source != "artifact" or source_path != "reports/quality-summary.json":
            raise ValueError("trusted quality result source is invalid")
    elif source != "stdout" or source_path is not None:
        raise ValueError("trusted result source is invalid")
    maximum_bytes = result_contract["maximum_parsed_bytes"]
    maximum_records = result_contract["maximum_parsed_records"]
    if (
        isinstance(maximum_bytes, bool)
        or not isinstance(maximum_bytes, int)
        or not 1 <= maximum_bytes <= _MAX_QUALITY_COVERAGE_BYTES
        or isinstance(maximum_records, bool)
        or not isinstance(maximum_records, int)
        or not 1 <= maximum_records <= _MAX_RESULT_RECORDS
    ):
        raise ValueError("trusted result contract bounds are invalid")
    minimum_coverage = result_contract["minimum_coverage_percent"]
    minimum_tests = result_contract["minimum_test_count"]
    if minimum_coverage is not None and (
        isinstance(minimum_coverage, bool)
        or not isinstance(minimum_coverage, int)
        or not 0 <= minimum_coverage <= _MAX_COVERAGE_PERCENT
    ):
        raise ValueError("trusted result coverage threshold is invalid")
    if minimum_tests is not None and (
        isinstance(minimum_tests, bool)
        or not isinstance(minimum_tests, int)
        or not 0 <= minimum_tests <= maximum_records
    ):
        raise ValueError("trusted result test threshold is invalid")
    fields = result_contract["required_summary_fields"]
    failures = result_contract["failure_conditions"]
    if not isinstance(fields, list) or not all(
        isinstance(field, str) for field in fields
    ):
        raise ValueError("trusted result required fields are invalid")
    if not isinstance(failures, list) or not all(
        isinstance(failure, str) for failure in failures
    ):
        raise ValueError("trusted result failure conditions are invalid")
    supported_failures = _RESULT_CONTRACT_FAILURES.get(parser_kind, frozenset())
    if not set(failures).issubset(supported_failures):
        raise ValueError("trusted result failure condition is unsupported")
    available_fields = {
        "pytest": {"tests"},
        "coverage": {"coverage"},
        "pytest-coverage": {"coverage", "tests"},
        "quality-summary-v1": {
            "coverage-threshold",
            "diagnostics",
            "operations",
            "profile",
            "status",
        },
        "dependency-audit": {"audit"},
        "dependency-health": {"audit"},
        "secret-scan": {"audit"},
    }.get(parser_kind, set())
    if not set(fields).issubset(available_fields):
        raise ValueError("trusted result required field is unsupported")
    if minimum_coverage is not None and parser_kind not in {
        "coverage",
        "pytest-coverage",
        "quality-summary-v1",
    }:
        raise ValueError("trusted result coverage parser is invalid")
    if minimum_tests is not None and parser_kind not in {"pytest", "pytest-coverage"}:
        raise ValueError("trusted result test parser is invalid")
    return result_contract


def _enforce_result_contract(
    parsed: ParsedResult,
    result_contract: Mapping[str, object] | None,
) -> ParsedResult:
    """Apply reviewed thresholds and failure semantics to parsed evidence."""

    if result_contract is None:
        return parsed
    maximum_records = result_contract["maximum_parsed_records"]
    assert isinstance(maximum_records, int)
    if (
        parsed.parser == "quality-summary-v1"
        and len(_QUALITY_OPERATIONS) > maximum_records
    ):
        raise ValueError("quality operation inventory exceeds reviewed record bound")
    if parsed.tests is not None:
        if parsed.tests.total > maximum_records:
            raise ValueError("parsed test count exceeds reviewed bound")
        minimum_tests = result_contract["minimum_test_count"]
        if minimum_tests is not None:
            assert isinstance(minimum_tests, int)
            if parsed.tests.total < minimum_tests:
                raise ValueError("parsed test count did not satisfy reviewed minimum")
    if parsed.coverage is not None:
        minimum_coverage = result_contract["minimum_coverage_percent"]
        if minimum_coverage is not None:
            assert isinstance(minimum_coverage, int)
            if parsed.coverage.measured_percent < minimum_coverage:
                raise ValueError("parsed coverage did not satisfy reviewed threshold")
    if parsed.audit is not None and parsed.audit.findings > maximum_records:
        raise ValueError("parsed audit findings exceed reviewed bound")
    failures = result_contract["failure_conditions"]
    assert isinstance(failures, list)
    if (
        "test-failure" in failures
        and parsed.tests is not None
        and (parsed.tests.failed or parsed.tests.errors)
    ):
        raise ValueError("parsed test result reported a reviewed failure")
    if {"dependency-health", "dependency-vulnerability", "baseline-validation"} & set(
        failures
    ) and (
        parsed.audit is None or parsed.audit.status != "passed" or parsed.audit.findings
    ):
        raise ValueError("parsed audit did not satisfy reviewed failure condition")
    return parsed


def _quality_operation_coverage(
    operation_name: str,
    details: dict[object, object],
    summary_threshold: object,
) -> float | None:
    """Validate exact coverage/diagnostics details and return summary coverage."""

    if operation_name == "coverage":
        if set(details) != {"coverage_percent", "coverage_threshold"}:
            raise ValueError("quality coverage operation details are invalid")
        operation_threshold = _bounded_number(
            details["coverage_threshold"],
            minimum=_QUALITY_COVERAGE_THRESHOLD,
            maximum=_QUALITY_COVERAGE_THRESHOLD,
        )
        if operation_threshold != summary_threshold:
            raise ValueError("quality coverage thresholds are inconsistent")
        return _bounded_number(
            details["coverage_percent"],
            minimum=_QUALITY_COVERAGE_THRESHOLD,
            maximum=_MAX_COVERAGE_PERCENT,
        )
    if operation_name == "diagnostics" and details:
        raise ValueError("quality diagnostics operation details are invalid")
    return None


def _quality_summary_result(checkout: Path, maximum_bytes: int) -> ParsedResult:
    """Validate only the declared Zscripts summary without retaining its bytes."""

    summary = _json_report(
        checkout,
        "reports/quality-summary.json",
        min(maximum_bytes, _MAX_QUALITY_SUMMARY_BYTES),
    )
    if set(summary) != {
        "profile",
        "status",
        "coverage_threshold",
        "operations",
        "duration_seconds",
    }:
        raise ValueError("quality summary fields are invalid")
    if summary["profile"] != "quality" or summary["status"] != "passed":
        raise ValueError("quality summary did not report the reviewed profile")
    if (
        _bounded_number(
            summary["coverage_threshold"],
            minimum=_QUALITY_COVERAGE_THRESHOLD,
            maximum=_QUALITY_COVERAGE_THRESHOLD,
        )
        != _QUALITY_COVERAGE_THRESHOLD
    ):
        raise ValueError("quality summary coverage threshold is invalid")
    _bounded_number(summary["duration_seconds"], minimum=0, maximum=86_400)
    operations = summary["operations"]
    if not isinstance(operations, list) or len(operations) != len(_QUALITY_OPERATIONS):
        raise ValueError("quality summary operation inventory is invalid")
    coverage_percent: float | None = None
    for expected_name, operation in zip(_QUALITY_OPERATIONS, operations, strict=True):
        if not isinstance(operation, dict) or set(operation) != {
            "operation",
            "status",
            "duration_seconds",
            "details",
        }:
            raise ValueError("quality operation fields are invalid")
        if operation["operation"] != expected_name or operation["status"] != "passed":
            raise ValueError("quality operation did not satisfy the reviewed contract")
        _bounded_number(operation["duration_seconds"], minimum=0, maximum=86_400)
        details = operation["details"]
        if not isinstance(details, dict):
            raise ValueError("quality operation details are invalid")
        operation_coverage = _quality_operation_coverage(
            expected_name, details, summary["coverage_threshold"]
        )
        if operation_coverage is not None:
            coverage_percent = operation_coverage
    if coverage_percent is None:  # pragma: no cover - fixed inventory contains it
        raise ValueError("quality coverage operation is unavailable")

    return ParsedResult(
        parser="quality-summary-v1",
        status="parsed",
        coverage=ParsedCoverage(measured_percent=coverage_percent),
        audit=AuditSummary(
            kind="quality", status="passed", tool="quality-gate", findings=0
        ),
    )


def parse_result(  # noqa: PLR0913 - parser inputs must remain explicit
    parser_kind: ParserKind,
    *,
    stdout_path: Path,
    stderr_path: Path,
    command_succeeded: bool,
    checkout: Path | None = None,
    result_contract: Mapping[str, object] | None = None,
) -> ParsedResult:
    """Parse only a trusted declared result kind without changing command truth."""

    try:
        contract = _validated_result_contract(result_contract, parser_kind)
        maximum_bytes = (
            contract["maximum_parsed_bytes"]
            if contract is not None
            else _MAX_PARSE_BYTES
        )
        assert isinstance(maximum_bytes, int)
        if parser_kind in {"pytest", "pytest-coverage"}:
            text = _combined(
                stdout_path, stderr_path, min(maximum_bytes, _MAX_PARSE_BYTES)
            )
            tests = _pytest_counts(text)
            coverage = _coverage(text) if parser_kind == "pytest-coverage" else None
            if tests is None or (parser_kind == "pytest-coverage" and coverage is None):
                raise ValueError("declared pytest result was not found")
            return _enforce_result_contract(
                ParsedResult(
                    parser=parser_kind,
                    status="parsed",
                    tests=tests,
                    coverage=coverage,
                ),
                contract,
            )
        if parser_kind == "coverage":
            text = _combined(
                stdout_path, stderr_path, min(maximum_bytes, _MAX_PARSE_BYTES)
            )
            coverage = _coverage(text)
            if coverage is None:
                raise ValueError("declared coverage result was not found")
            return _enforce_result_contract(
                ParsedResult(parser=parser_kind, status="parsed", coverage=coverage),
                contract,
            )
        if parser_kind == "quality-summary-v1":
            if not command_succeeded or checkout is None:
                raise ValueError(
                    "quality summary requires a successful checked-out run"
                )
            return _enforce_result_contract(
                _quality_summary_result(checkout, maximum_bytes), contract
            )
        if parser_kind in {
            "security-audit",
            "dependency-audit",
            "dependency-health",
            "critical-coverage",
            "secret-scan",
        }:
            text = _combined(
                stdout_path, stderr_path, min(maximum_bytes, _MAX_PARSE_BYTES)
            )
            if parser_kind == "security-audit" and _BANDIT_MANAGER_ERROR in text:
                raise ValueError("Bandit did not scan every requested file")
            issue_count = text.count(">> Issue:")
            findings = 0 if command_succeeded else max(1, issue_count)
            audit_kind = cast(
                Literal["security", "dependency", "quality"],
                {
                    "security-audit": "security",
                    "secret-scan": "security",
                    "dependency-audit": "dependency",
                    "dependency-health": "dependency",
                    "critical-coverage": "quality",
                }[parser_kind],
            )
            tool = {
                "security-audit": "bandit",
                "secret-scan": "secret-scan",
                "dependency-audit": "pip-audit",
                "dependency-health": "pip",
                "critical-coverage": "critical-coverage",
            }[parser_kind]
            return _enforce_result_contract(
                ParsedResult(
                    parser=parser_kind,
                    status="parsed",
                    audit=AuditSummary(
                        kind=audit_kind,
                        status="passed" if command_succeeded else "failed",
                        tool=tool,
                        findings=findings,
                    ),
                ),
                contract,
            )
        raise ValueError("unsupported trusted parser")
    except (OSError, UnicodeError, ValueError):
        return ParsedResult(
            parser=parser_kind,
            status="parser_failed",
            failure_reason="declared_result_unavailable",
        )


__all__ = ["parse_result"]
