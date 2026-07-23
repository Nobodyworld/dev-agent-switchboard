"""Small bounded parsers selected only by reviewed trusted manifest steps."""

from __future__ import annotations

import re
from pathlib import Path

from server.execution.evidence import (
    AuditSummary,
    ParsedCoverage,
    ParsedResult,
    ParsedTestCounts,
    ParserKind,
)

_MAX_PARSE_BYTES = 1024 * 1024
_PYTEST_COUNTS = {
    "passed": re.compile(r"(?P<count>\d+) passed\b"),
    "failed": re.compile(r"(?P<count>\d+) failed\b"),
    "skipped": re.compile(r"(?P<count>\d+) skipped\b"),
    "errors": re.compile(r"(?P<count>\d+) errors?\b"),
    "xfailed": re.compile(r"(?P<count>\d+) xfailed\b"),
    "xpassed": re.compile(r"(?P<count>\d+) xpassed\b"),
}
_COVERAGE_PERCENT = re.compile(r"(?P<percent>\d+(?:\.\d+)?)%\s*$")


def _bounded_text(path: Path) -> str:
    with path.open("rb") as handle:
        data = handle.read(_MAX_PARSE_BYTES + 1)
    return data[:_MAX_PARSE_BYTES].decode("utf-8", errors="replace")


def _combined(stdout_path: Path, stderr_path: Path) -> str:
    return f"{_bounded_text(stdout_path)}\n{_bounded_text(stderr_path)}"


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
        if not line.strip().startswith("TOTAL"):
            continue
        match = _COVERAGE_PERCENT.search(line.strip())
        if match:
            return ParsedCoverage(measured_percent=float(match.group("percent")))
    return None


def parse_result(
    parser_kind: ParserKind,
    *,
    stdout_path: Path,
    stderr_path: Path,
    command_succeeded: bool,
) -> ParsedResult:
    """Parse only a trusted declared result kind without changing command truth."""

    try:
        text = _combined(stdout_path, stderr_path)
        if parser_kind in {"pytest", "pytest-coverage"}:
            tests = _pytest_counts(text)
            coverage = _coverage(text) if parser_kind == "pytest-coverage" else None
            if tests is None or (parser_kind == "pytest-coverage" and coverage is None):
                raise ValueError("declared pytest result was not found")
            return ParsedResult(
                parser=parser_kind,
                status="parsed",
                tests=tests,
                coverage=coverage,
            )
        if parser_kind == "coverage":
            coverage = _coverage(text)
            if coverage is None:
                raise ValueError("declared coverage result was not found")
            return ParsedResult(parser=parser_kind, status="parsed", coverage=coverage)
        if parser_kind in {"security-audit", "dependency-audit"}:
            issue_count = text.count(">> Issue:")
            findings = 0 if command_succeeded else max(1, issue_count)
            return ParsedResult(
                parser=parser_kind,
                status="parsed",
                audit=AuditSummary(
                    kind=(
                        "security" if parser_kind == "security-audit" else "dependency"
                    ),
                    status="passed" if command_succeeded else "failed",
                    tool="bandit" if parser_kind == "security-audit" else "pip",
                    findings=findings,
                ),
            )
        raise ValueError("unsupported trusted parser")
    except (OSError, UnicodeError, ValueError):
        return ParsedResult(
            parser=parser_kind,
            status="parser_failed",
            failure_reason="declared_result_unavailable",
        )


__all__ = ["parse_result"]
