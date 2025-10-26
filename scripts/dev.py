#!/usr/bin/env python3
"""Developer utility CLI for Switchboard."""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from collections.abc import Iterable
from datetime import date
from pathlib import Path
from textwrap import dedent

TODO_PATTERN = re.compile(r"\b(?:TODO|FIXME)\(P[1-3],\s*[^)]+\)")


def _resolve_executable(bin_name: str, venv_path: Path) -> Path:
    if os.name == "nt":
        candidate = venv_path / "Scripts" / f"{bin_name}.exe"
    else:
        candidate = venv_path / "bin" / bin_name
    return candidate


def cmd_bootstrap(args: argparse.Namespace) -> None:
    """Create a virtualenv and install development dependencies."""

    venv_path = Path(args.venv).resolve()
    if not venv_path.exists():
        subprocess.check_call([sys.executable, "-m", "venv", str(venv_path)])
    pip_executable = _resolve_executable("pip", venv_path)
    subprocess.check_call([str(pip_executable), "install", "-r", "server/requirements-dev.txt"])
    subprocess.check_call([str(pip_executable), "install", "pre-commit"])
    python_executable = _resolve_executable("python", venv_path)
    subprocess.check_call([str(python_executable), "-m", "pre_commit", "install", "--install-hooks"])
    print(f"Development environment ready in {venv_path}")


def _load_coverage(path: Path) -> dict:
    with path.open(encoding="utf-8") as fh:
        return json.load(fh)


def _extract_coverage(data: dict, target: str) -> float | None:
    files = data.get("files", {})
    for file_path, info in files.items():
        normalized = str(Path(file_path).as_posix())
        if normalized.endswith(target):
            summary = info.get("summary", {})
            return float(summary.get("percent_covered", 0.0))
    return None


def cmd_coverage_gate(args: argparse.Namespace) -> None:
    """Validate per-module coverage thresholds."""

    data = _load_coverage(Path(args.json))
    failures: list[str] = []
    for module_spec in args.module:
        if "=" not in module_spec:
            raise SystemExit(f"Invalid module spec {module_spec!r}; expected path=threshold")
        module_path, threshold_raw = module_spec.split("=", 1)
        try:
            threshold = float(threshold_raw)
        except ValueError as exc:  # pragma: no cover - user error
            raise SystemExit(f"Invalid threshold {threshold_raw!r} for {module_path}") from exc
        coverage = _extract_coverage(data, module_path)
        if coverage is None:
            failures.append(f"Missing coverage data for {module_path}")
            continue
        if coverage + 1e-6 < threshold:
            failures.append(
                f"{module_path} coverage {coverage:.2f}% below threshold {threshold:.2f}%"
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

    commands = [
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
            "--cov=server.observability.diagnostics",
            "--cov-report=term-missing",
            f"--cov-report=json:{coverage_json}",
        ],
    ]

    for command in commands:
        print(f"→ {' '.join(str(part) for part in command)}")
        subprocess.check_call(command)

    gate_args = argparse.Namespace(
        json=str(coverage_json),
        module=[
            "server/extensions/loader.py=85",
            "server/extensions/runtime.py=85",
            "server/extensions/builtin/task_metrics.py=85",
            "server/extensions/builtin/plan_metrics.py=85",
            "server/observability/diagnostics.py=80",
        ],
    )
    cmd_coverage_gate(gate_args)

    if not args.skip_audit:
        print("→ pip-audit")
        subprocess.check_call(["pip-audit", "--progress-spinner=off"])


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
    directory.mkdir(parents=True, exist_ok=True)
    module_path = directory / f"{args.name}.py"
    if module_path.exists() and not args.force:
        raise SystemExit(f"{module_path} already exists; pass --force to overwrite")

    template = dedent(
        """
        \"\"\"Extension stub for `{name}`.\"\"\"

        from __future__ import annotations

        from server.extensions.interfaces import ExtensionDescriptor, ExtensionRegistry


        def register_extension(registry: ExtensionRegistry) -> None:
            \"\"\"Register the {name} extension with Switchboard.\"\"\"

            registry.append_contract_note(
                "{name} extension depends on deployment-specific configuration."
            )
            registry.register_extension(
                ExtensionDescriptor(
                    name="custom.{name}",
                    capabilities=("sample",),
                    version="0.1.0",
                    description="Describe what this extension does.",
                    config={{"enabled": False}},
                )
            )
            # TODO(P3, 1d) - Implement lifecycle hooks for this extension.
        """
    ).format(name=args.name).strip()

    module_path.write_text(template + "\n", encoding="utf-8")
    print(f"Extension scaffold written to {module_path}")


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
    today = date.today().isoformat()
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
    today = date.today().isoformat()
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

    bootstrap = subparsers.add_parser("bootstrap", help="Create a venv and install tooling")
    bootstrap.add_argument("--venv", default=".venv", help="Virtualenv directory")
    bootstrap.set_defaults(func=cmd_bootstrap)

    coverage = subparsers.add_parser("coverage-gate", help="Enforce coverage thresholds")
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

    bump = subparsers.add_parser("bump-version", help="Bump server version and changelog stubs")
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
