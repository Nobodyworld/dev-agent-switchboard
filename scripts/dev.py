#!/usr/bin/env python3
"""Developer utility CLI for Switchboard."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import subprocess
import sys
from collections.abc import Iterable, Mapping, Sequence
from datetime import datetime, timezone
from pathlib import Path
from shutil import which
from typing import Any, cast

TODO_PATTERN = re.compile(r"\b(?:TODO|FIXME)\(P[1-3],\s*[^)]+\)")


TRUSTED_EXECUTABLES = {
    "bandit",
    "mypy",
    "pip-audit",
    "pytest",
    "ruff",
}


def _resolve_executable(bin_name: str, venv_path: Path) -> Path:
    if os.name == "nt":
        candidate = venv_path / "Scripts" / f"{bin_name}.exe"
    else:
        candidate = venv_path / "bin" / bin_name
    return candidate


def _assert_trusted_command(command: Sequence[str]) -> None:
    """Ensure subprocess commands originate from trusted sources."""

    if not command:
        raise SystemExit("Refusing to execute empty command")
    executable = command[0]
    if executable == sys.executable:
        return
    if executable in TRUSTED_EXECUTABLES:
        return
    if os.path.isabs(executable):
        return
    raise SystemExit(f"Refusing to execute untrusted command: {' '.join(command)}")


def _run_command(command: Sequence[str]) -> None:
    """Execute a pre-validated subprocess command with strict checking."""

    _assert_trusted_command(command)
    subprocess.run(command, check=True)  # noqa: S603


def _render_template(template: str, context: Mapping[str, str]) -> str:
    rendered = template
    for key, value in context.items():
        rendered = rendered.replace(f"{{{{{key}}}}}", value)
    return rendered


def _json_default(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.isoformat()
    return value


def cmd_bootstrap(args: argparse.Namespace) -> None:
    """Create a virtualenv and install development dependencies."""

    venv_path = Path(args.venv).resolve()
    if not venv_path.exists():
        _run_command([sys.executable, "-m", "venv", str(venv_path)])
    pip_executable = _resolve_executable("pip", venv_path)
    _run_command(
        [str(pip_executable), "install", "-r", "server/requirements-dev.txt"]
    )
    _run_command([str(pip_executable), "install", "pre-commit"])
    python_executable = _resolve_executable("python", venv_path)
    _run_command(
        [str(python_executable), "-m", "pre_commit", "install", "--install-hooks"]
    )
    print(f"Development environment ready in {venv_path}")


def _load_coverage(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as fh:
        loaded = json.load(fh)
    if not isinstance(loaded, dict):
        raise SystemExit("Coverage JSON must contain a top-level object")
    return cast(dict[str, Any], loaded)


def _extract_coverage(data: Mapping[str, Any], target: str) -> float | None:
    files = data.get("files", {})
    if not isinstance(files, Mapping):
        return None
    for file_path, info in files.items():
        if not isinstance(info, Mapping):
            continue
        normalized = str(Path(file_path).as_posix())
        if normalized.endswith(target):
            summary = info.get("summary", {})
            if not isinstance(summary, Mapping):
                continue
            percent = summary.get("percent_covered", 0.0)
            try:
                return float(percent)
            except (TypeError, ValueError):
                return None
    return None


def cmd_coverage_gate(args: argparse.Namespace) -> None:
    """Validate per-module coverage thresholds."""

    data = _load_coverage(Path(args.json))
    failures: list[str] = []
    for module_spec in args.module:
        if "=" not in module_spec:
            raise SystemExit(
                f"Invalid module spec {module_spec!r}; expected path=threshold"
            )
        module_path, threshold_raw = module_spec.split("=", 1)
        try:
            threshold = float(threshold_raw)
        except ValueError as exc:  # pragma: no cover - user error
            raise SystemExit(
                f"Invalid threshold {threshold_raw!r} for {module_path}"
            ) from exc
        coverage = _extract_coverage(data, module_path)
        if coverage is None:
            failures.append(f"Missing coverage data for {module_path}")
            continue
        if coverage + 1e-6 < threshold:
            failures.append(
                f"{module_path} coverage {coverage:.2f}% "
                f"below threshold {threshold:.2f}%"
            )
    if failures:
        for failure in failures:
            print(failure)
        raise SystemExit(1)
    print("Coverage thresholds satisfied:")
    for module_spec in args.module:
        module_path, _ = module_spec.split("=", 1)
        coverage = _extract_coverage(data, module_path) or 0.0
        print(f"  {module_path}: {coverage:.2f}%")


def cmd_verify(args: argparse.Namespace) -> None:
    """Run lint, type-check, security scan, and coverage gates sequentially."""

    coverage_json = Path(args.coverage_json).resolve()
    coverage_json.parent.mkdir(parents=True, exist_ok=True)

    commands: list[list[str]] = [
        ["ruff", "check", "."],
        [
            "mypy",
            "--config-file",
            "mypy.ini",
            "server",
            "client",
            "scripts",
        ],
        ["bandit", "-q", "-r", "server"],
        [
            sys.executable,
            "-m",
            "pytest",
            "--cov=server.extensions",
            "--cov=server.application.task_service",
            "--cov=server.application.configuration_service",
            "--cov=server.observability.diagnostics",
            "--cov=server.observability.health",
            "--cov=server.observability.activity",
            "--cov-report=term-missing",
            f"--cov-report=json:{coverage_json}",
        ],
    ]

    for command in commands:
        print(f"→ {' '.join(str(part) for part in command)}")
        _run_command(command)

    gate_args = argparse.Namespace(
        json=str(coverage_json),
        module=[
            "server/extensions/loader.py=85",
            "server/extensions/runtime.py=85",
            "server/extensions/contracts.py=85",
            "server/extensions/builtin/task_metrics.py=85",
            "server/extensions/builtin/plan_metrics.py=85",
            "server/extensions/builtin/plan_latency.py=80",
            "server/extensions/builtin/plan_snapshot.py=80",
            "server/extensions/observability.py=80",
            "server/extensions/builtin/activity_feed.py=85",
            "server/observability/diagnostics.py=80",
            "server/observability/health.py=85",
            "server/observability/activity.py=80",
            "server/observability/overview.py=85",
            "server/application/configuration_service.py=85",
        ],
    )
    cmd_coverage_gate(gate_args)

    if not args.skip_audit:
        print("→ pip-audit")
        pip_audit = which("pip-audit")
        if pip_audit is None:
            raise SystemExit(
                "pip-audit not found on PATH; install it or pass --skip-audit"
            )
        _run_command([pip_audit, "--progress-spinner=off"])


def cmd_check_todos(args: argparse.Namespace) -> None:
    """Enforce priority/effort metadata on TODO and FIXME markers."""

    root = Path(args.root).resolve()
    violations: list[tuple[Path, int, str]] = []
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        if path.suffix in {".pyc", ".png", ".jpg", ".jpeg", ".gif", ".svg", ".ico"}:
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        for lineno, line in enumerate(text.splitlines(), start=1):
            if "TODO(" not in line and "FIXME(" not in line:
                continue
            stripped = line.lstrip()
            if not stripped.startswith(("#", "//", "/*", "*", "<!--")):
                continue
            if TODO_PATTERN.search(line):
                continue
            violations.append((path, lineno, line.strip()))

    if violations:
        for path, lineno, line in violations:
            print(f"{path}:{lineno}: TODO/FIXME missing priority/effort tag -> {line}")
        raise SystemExit(1)

    print("All TODO/FIXME annotations include priority and effort metadata.")


def cmd_scaffold_extension(args: argparse.Namespace) -> None:
    """Generate a starter extension module with contract metadata."""

    directory = Path(args.directory).resolve()
    template_path = Path("server/extensions/templates/extension.py.j2")
    if not template_path.exists():
        raise SystemExit(
            f"Template {template_path} is missing; reinstall the repository"
        )

    normalized = args.name.strip().replace("-", "_")
    if not normalized:
        raise SystemExit("Extension name must be non-empty")

    module_parts = [part for part in normalized.split(".") if part]
    module_dir = (
        directory.joinpath(*module_parts[:-1]) if len(module_parts) > 1 else directory
    )
    module_dir.mkdir(parents=True, exist_ok=True)
    module_filename = f"{module_parts[-1]}.py"
    module_path = module_dir / module_filename
    if module_path.exists() and not args.force:
        raise SystemExit(f"{module_path} already exists; pass --force to overwrite")

    descriptor_name = f"custom.{'.'.join(module_parts)}"
    class_name = "".join(piece.title() for piece in module_parts) + "Extension"

    template_text = template_path.read_text(encoding="utf-8")
    rendered = _render_template(
        template_text,
        {
            "module_doc": f"Extension stub for `{descriptor_name}`.",
            "descriptor_name": descriptor_name,
            "class_name": class_name,
            "module_basename": module_parts[-1],
            "extension_module": ".".join(module_parts),
        },
    ).strip()

    module_path.write_text(rendered + "\n", encoding="utf-8")
    print(f"Extension scaffold written to {module_path}")


def cmd_observability_overview(args: argparse.Namespace) -> None:
    """Emit a consolidated observability snapshot."""

    async def _collect() -> dict[str, Any]:
        from server.app import app  # noqa: PLC0415
        from server.db import AsyncSessionLocal  # noqa: PLC0415
        from server.observability.overview import (  # noqa: PLC0415
            collect_observability_overview,
        )

        async with AsyncSessionLocal() as session:
            overview = await collect_observability_overview(
                session, app_version=app.version
            )
        return overview.as_payload()

    payload = asyncio.run(_collect())
    text = json.dumps(payload, indent=2 if args.pretty else None, default=_json_default)
    if args.output:
        output_path = Path(args.output)
        output_path.write_text(text + "\n", encoding="utf-8")
        print(f"Observability overview written to {output_path}")
    else:
        print(text)


def cmd_list_extensions(_args: argparse.Namespace) -> None:
    """Print registered extensions and observability registrations."""

    from server.extensions import (  # noqa: PLC0415 - lazy import for CLI startup
        get_extension_bundle,
        get_observability_registrations,
    )

    bundle = get_extension_bundle()
    print(f"Extension contract: v{bundle.contract.api_version}")
    if bundle.contract.notes:
        print("Notes:")
        for note in bundle.contract.notes:
            print(f"  - {note}")
    descriptors = list(bundle.descriptors)
    if descriptors:
        print("Registered extensions:")
        for descriptor in descriptors:
            capabilities = ", ".join(descriptor.capabilities) or "-"
            version = descriptor.version or "n/a"
            descriptor_line = (
                "  - "
                f"{descriptor.name} "
                f"(capabilities: {capabilities}, version: {version})"
            )
            print(descriptor_line)
            if descriptor.description:
                print(f"      {descriptor.description}")
    else:
        print("No extensions registered.")
    snapshot = get_observability_registrations()
    registrations = snapshot.registrations
    if registrations:
        print("Observability registrations:")
        for name, registration in registrations.items():
            payload = registration.as_payload()
            details = payload.get("details", {})
            print(f"  - {name}: {details}")
            notes = payload.get("notes") or []
            for note in notes:
                print(f"      note: {note}")
    else:
        print("Observability registrations: none")


_VERSION_RE = re.compile(r'version="(?P<version>\d+\.\d+\.\d+)"')


def _current_version(app_path: Path) -> str:
    text = app_path.read_text(encoding="utf-8")
    match = _VERSION_RE.search(text)
    if match is None:
        raise SystemExit("Unable to locate version string in server/app.py")
    return match.group("version")


def _bump_version(version: str, part: str) -> str:
    major, minor, patch = (int(piece) for piece in version.split("."))
    if part == "major":
        major += 1
        minor = 0
        patch = 0
    elif part == "minor":
        minor += 1
        patch = 0
    else:
        patch += 1
    return f"{major}.{minor}.{patch}"


def _update_app_version(app_path: Path, new_version: str) -> None:
    text = app_path.read_text(encoding="utf-8")
    new_text, count = _VERSION_RE.subn(f'version="{new_version}"', text, count=1)
    if count != 1:
        raise SystemExit("Failed to update version string in server/app.py")
    app_path.write_text(new_text, encoding="utf-8")


def _ensure_changelog_entry(path: Path, new_version: str) -> None:
    today = datetime.now(timezone.utc).date().isoformat()
    marker = f"## v{new_version}"
    content = path.read_text(encoding="utf-8")
    if marker in content:
        return
    insertion = (
        f"## v{new_version} - {today}\n\n"
        "### Added\n- _TBD_\n\n"
        "### Changed\n- _TBD_\n\n"
        "### Fixed\n- _TBD_\n\n"
    )
    if "## Unreleased" in content:
        anchor = content.index("## Unreleased")
        next_break = content.find("\n", anchor)
        if next_break == -1:
            next_break = anchor + len("## Unreleased")
        next_break += 1
        content = content[:next_break] + insertion + content[next_break:]
    else:
        content = content + "\n" + insertion
    path.write_text(content, encoding="utf-8")


def _ensure_release_notes_entry(path: Path, new_version: str) -> None:
    today = datetime.now(timezone.utc).date().isoformat()
    marker = f"## v{new_version}"
    content = path.read_text(encoding="utf-8")
    if marker in content:
        return
    insertion = f"## v{new_version} — {today}\n\n- _Document key changes here._\n\n"
    path.write_text(insertion + content, encoding="utf-8")


def cmd_bump_version(args: argparse.Namespace) -> None:
    app_path = Path("server/app.py")
    current = _current_version(app_path)
    new_version = args.version or _bump_version(current, args.part)
    _update_app_version(app_path, new_version)
    _ensure_changelog_entry(Path("CHANGELOG.md"), new_version)
    _ensure_release_notes_entry(Path("RELEASE_NOTES.md"), new_version)
    print(f"Version bumped: {current} -> {new_version}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Switchboard developer utilities")
    subparsers = parser.add_subparsers(dest="command", required=True)

    bootstrap = subparsers.add_parser(
        "bootstrap", help="Create a venv and install tooling"
    )
    bootstrap.add_argument("--venv", default=".venv", help="Virtualenv directory")
    bootstrap.set_defaults(func=cmd_bootstrap)

    coverage = subparsers.add_parser(
        "coverage-gate", help="Enforce coverage thresholds"
    )
    coverage.add_argument("--json", required=True, help="Path to coverage JSON report")
    coverage.add_argument(
        "--module",
        action="append",
        default=[],
        help="Module coverage specification path=threshold",
    )
    coverage.set_defaults(func=cmd_coverage_gate)

    verify = subparsers.add_parser(
        "verify", help="Run lint, type-check, security, and coverage gates"
    )
    verify.add_argument(
        "--coverage-json",
        default="reports/coverage.json",
        help="Path for coverage JSON report",
    )
    verify.add_argument(
        "--skip-audit",
        action="store_true",
        help="Skip pip-audit execution",
    )
    verify.set_defaults(func=cmd_verify)

    todos = subparsers.add_parser(
        "check-todos", help="Ensure TODO/FIXME comments include priority metadata"
    )
    todos.add_argument("--root", default=".", help="Root directory to scan")
    todos.set_defaults(func=cmd_check_todos)

    scaffold = subparsers.add_parser(
        "scaffold-extension", help="Generate a starter extension module"
    )
    scaffold.add_argument("name", help="Module name without file extension")
    scaffold.add_argument(
        "--directory",
        default="server/extensions/community",
        help="Directory for the generated module",
    )
    scaffold.add_argument(
        "--force",
        action="store_true",
        help="Overwrite existing module files",
    )
    scaffold.set_defaults(func=cmd_scaffold_extension)

    overview = subparsers.add_parser(
        "observability-overview",
        help="Print an aggregated observability snapshot",
    )
    overview.add_argument(
        "--pretty",
        action="store_true",
        help="Pretty-print the JSON payload",
    )
    overview.add_argument(
        "--output",
        help="Optional path to write the JSON payload",
    )
    overview.set_defaults(func=cmd_observability_overview)

    extensions = subparsers.add_parser(
        "extensions", help="List registered extensions and observability hooks"
    )
    extensions.set_defaults(func=cmd_list_extensions)

    bump = subparsers.add_parser(
        "bump-version", help="Bump server version and changelog stubs"
    )
    bump.add_argument("--part", choices=["major", "minor", "patch"], default="patch")
    bump.add_argument("--version", help="Explicit semantic version override")
    bump.set_defaults(func=cmd_bump_version)

    return parser


def main(argv: Iterable[str] | None = None) -> None:
    parser = build_parser()
    args = parser.parse_args(list(argv) if argv is not None else None)
    args.func(args)


if __name__ == "__main__":  # pragma: no cover - CLI entry point
    main()
