"""Deterministic bounded Markdown for one server-managed PR comment."""

from __future__ import annotations

import re
from collections.abc import Sequence

from server.execution.evidence import AuditSummary, ExecutionEvidence
from server.models import GitHubValidationRequest

MARKER_VERSION = "v1"
SWITCHBOARD_COMMENT_VERSION = "1"
MAX_RENDERED_COMMENT_BYTES = 12 * 1024
_HEX_64 = re.compile(r"^[0-9a-f]{64}$")
_REASON = re.compile(r"^[a-z0-9][a-z0-9_.:-]{0,63}$")


def managed_comment_marker(idempotency_key: str) -> str:
    """Return the exact machine marker for one immutable request identity."""

    if not _HEX_64.fullmatch(idempotency_key):
        raise ValueError("invalid managed comment identity")
    return f"<!-- switchboard-validation:{MARKER_VERSION}:{idempotency_key} -->"


def has_exact_marker(body: str, marker: str) -> bool:
    """Return whether a bounded remote comment begins with the exact marker."""

    return (
        len(body.encode("utf-8")) <= MAX_RENDERED_COMMENT_BYTES
        and body.splitlines()[:1] == [marker]
    )


def render_managed_comment(
    request: GitHubValidationRequest,
    evidence: ExecutionEvidence,
    *,
    decision: str,
    decision_reason: str,
) -> str:
    """Render compact evidence without remote text, logs, paths, or commands."""

    if decision not in {"current", "stale"}:
        raise ValueError("invalid publication decision")
    safe_reason = (
        decision_reason
        if _REASON.fullmatch(decision_reason)
        else "github_publication_failed"
    )
    terminal_reason = (
        evidence.terminal_reason
        if evidence.terminal_reason and _REASON.fullmatch(evidence.terminal_reason)
        else evidence.terminal_status
    )
    marker = managed_comment_marker(request.idempotency_key)
    lines = [
        marker,
        "## Switchboard validation",
        "",
        f"- Switchboard comment schema: `{SWITCHBOARD_COMMENT_VERSION}`",
        (
            f"- Repository / PR: `{request.repository_full_name}` "
            f"`#{request.pull_request_number}`"
        ),
        f"- Exact tested SHA: `{request.head_sha}`",
        (
            f"- Manifest: `{request.manifest_name}@{request.manifest_version}` "
            f"(`{request.manifest_digest}`)"
        ),
        f"- Terminal status: `{evidence.terminal_status}`",
        f"- Terminal reason: `{terminal_reason}`",
        "- Execution provenance: `fresh`",
        f"- Evidence fingerprint: `{evidence.fingerprint}`",
        f"- Head decision: `{decision}` (`{safe_reason}`)",
    ]
    tests = next(
        (
            step.parsed_result.tests
            for step in evidence.steps
            if step.parsed_result is not None
            and step.parsed_result.status == "parsed"
            and step.parsed_result.tests is not None
        ),
        None,
    )
    if tests is not None:
        lines.append(
            "- Tests: "
            f"`{tests.passed} passed, {tests.failed} failed, "
            f"{tests.skipped} skipped, {tests.errors} errors`"
        )
    coverage = next(
        (
            step.parsed_result.coverage
            for step in evidence.steps
            if step.parsed_result is not None
            and step.parsed_result.status == "parsed"
            and step.parsed_result.coverage is not None
        ),
        None,
    )
    if coverage is not None:
        lines.append(f"- Measured coverage: `{coverage.measured_percent:.2f}%`")
    audits = [
        step.parsed_result.audit
        for step in evidence.steps
        if step.parsed_result is not None
        and step.parsed_result.status == "parsed"
        and step.parsed_result.audit is not None
    ]
    security = _first_audit(audits, "security")
    dependency = _first_audit(audits, "dependency")
    if security is not None:
        lines.append(
            f"- Security audit: `{security.status}; {security.findings} findings`"
        )
    if dependency is not None:
        lines.append(
            f"- Dependency audit: `{dependency.status}; {dependency.findings} findings`"
        )
    lines.extend(
        [
            "",
            "Full logs and artifact bytes remain local to the trusted worker.",
        ]
    )
    rendered = "\n".join(lines)
    if len(rendered.encode("utf-8")) > MAX_RENDERED_COMMENT_BYTES:
        raise ValueError("managed comment exceeds bounded size")
    return rendered


def _first_audit(
    audits: Sequence[AuditSummary], kind: str
) -> AuditSummary | None:
    return next((audit for audit in audits if audit.kind == kind), None)


__all__ = [
    "MAX_RENDERED_COMMENT_BYTES",
    "has_exact_marker",
    "managed_comment_marker",
    "render_managed_comment",
]
