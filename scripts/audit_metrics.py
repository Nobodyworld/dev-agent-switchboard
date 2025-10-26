#!/usr/bin/env python3
"""Collect repository health metrics for stewardship reporting."""
from __future__ import annotations

import argparse
import ast
import json
import subprocess
import sys
import time
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

try:
    from radon.complexity import cc_rank, cc_visit
except ImportError as exc:  # pragma: no cover - tooling missing
    raise SystemExit("radon must be installed to run audit metrics") from exc


ROOT = Path(__file__).resolve().parents[1]
SERVER_ROOT = ROOT / "server"


@dataclass
class DependencyMetrics:
    module_count: int
    edge_count: int
    avg_out_degree: float
    max_depth: int


def _iter_python_files(root: Path) -> Iterable[Path]:
    for path in root.rglob("*.py"):
        if path.name == "__init__.py" or path.suffix == ".py":
            yield path


def _module_name(path: Path, root: Path) -> str:
    relative = path.relative_to(root)
    parts = list(relative.parts)
    if parts[-1] == "__init__.py":
        parts[-1] = "__init__"
    else:
        parts[-1] = parts[-1][:-3]
    return "server." + ".".join(parts)


def _collect_dependencies() -> DependencyMetrics:
    graph: dict[str, set[str]] = {}

    for file_path in _iter_python_files(SERVER_ROOT):
        module = _module_name(file_path, SERVER_ROOT)
        graph.setdefault(module, set())
        with file_path.open(encoding="utf-8") as handle:
            try:
                tree = ast.parse(handle.read(), filename=str(file_path))
            except SyntaxError:
                continue
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    name = alias.name
                    if name.startswith("server.") and name != module:
                        graph[module].add(name)
            elif (
                isinstance(node, ast.ImportFrom)
                and node.module
                and node.module.startswith("server")
            ):
                name = node.module
                if not name.startswith("server."):
                    name = "server." + name.split("server", 1)[-1].lstrip(".")
                if name != module:
                    graph[module].add(name)
    module_count = len(graph)
    edge_count = sum(len(targets) for targets in graph.values())
    avg_out_degree = edge_count / module_count if module_count else 0.0

    memo: dict[str, int] = {}

    def depth(node: str, seen: set[str]) -> int:
        if node in memo:
            return memo[node]
        max_depth = 1
        for neighbor in graph.get(node, ()):  # pragma: no branch - simple iteration
            if neighbor in seen:
                continue
            child_depth = 1 + depth(neighbor, seen | {neighbor})
            max_depth = max(max_depth, child_depth)
        memo[node] = max_depth
        return max_depth

    max_depth = 0
    for module in graph:
        candidate = depth(module, {module})
        max_depth = max(max_depth, candidate)

    return DependencyMetrics(
        module_count=module_count,
        edge_count=edge_count,
        avg_out_degree=avg_out_degree,
        max_depth=max_depth,
    )


def _collect_complexity() -> dict[str, float]:
    complexities = []
    for file_path in _iter_python_files(SERVER_ROOT):
        with file_path.open(encoding="utf-8") as handle:
            source = handle.read()
        for block in cc_visit(source):
            complexities.append(block.complexity)
    average = sum(complexities) / len(complexities) if complexities else 0.0
    return {
        "average_complexity": average,
        "grade": cc_rank(average) if complexities else "N/A",
        "blocks": len(complexities),
    }


def _run_pytest_with_coverage(output_dir: Path) -> dict[str, float]:
    output_dir.mkdir(parents=True, exist_ok=True)
    coverage_json = output_dir / "coverage.json"
    cmd = [
        sys.executable,
        "-m",
        "pytest",
        "--cov=server",
        "--cov-report=term-missing",
        f"--cov-report=json:{coverage_json}",
    ]
    start = time.perf_counter()
    subprocess.run(cmd, check=True)  # noqa: S603
    duration = time.perf_counter() - start
    with coverage_json.open(encoding="utf-8") as handle:
        data = json.load(handle)
    totals = data.get("totals", {})
    return {
        "percent_covered": float(totals.get("percent_covered", 0.0)),
        "covered_lines": float(totals.get("covered_lines", 0.0)),
        "num_statements": float(totals.get("num_statements", 0.0)),
        "duration_seconds": duration,
    }


def _load_coverage(output_dir: Path) -> dict[str, float]:
    coverage_json = output_dir / "coverage.json"
    if not coverage_json.exists():
        return _run_pytest_with_coverage(output_dir)
    with coverage_json.open(encoding="utf-8") as handle:
        data = json.load(handle)
    totals = data.get("totals", {})
    # Duration captured separately; best-effort fallback.
    return {
        "percent_covered": float(totals.get("percent_covered", 0.0)),
        "covered_lines": float(totals.get("covered_lines", 0.0)),
        "num_statements": float(totals.get("num_statements", 0.0)),
        "duration_seconds": 0.0,
    }


def collect_metrics(output_dir: Path, force: bool) -> dict[str, object]:
    output_dir = output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    if force:
        coverage = _run_pytest_with_coverage(output_dir)
    else:
        coverage = _load_coverage(output_dir)
        if coverage["duration_seconds"] == 0.0:
            coverage["duration_seconds"] = None

    complexity = _collect_complexity()
    dependencies = _collect_dependencies()

    metrics = {
        "coverage": coverage,
        "complexity": complexity,
        "dependencies": {
            "module_count": dependencies.module_count,
            "edge_count": dependencies.edge_count,
            "avg_out_degree": dependencies.avg_out_degree,
            "max_depth": dependencies.max_depth,
        },
    }

    output_path = output_dir / "system_metrics.json"
    with output_path.open("w", encoding="utf-8") as handle:
        json.dump(metrics, handle, indent=2, sort_keys=True)

    return metrics


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output",
        type=Path,
        default=ROOT / "reports",
        help="Directory to write metrics outputs",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Re-run pytest with coverage even if artifacts exist",
    )
    args = parser.parse_args(argv)

    metrics = collect_metrics(args.output, args.force)
    print(json.dumps(metrics, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
