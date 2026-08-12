"""Regression tests for development-tool version alignment."""

from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
RUFF_PRE_COMMIT_REPOSITORY = "https://github.com/astral-sh/ruff-pre-commit"


def test_pre_commit_ruff_matches_development_requirement() -> None:
    """Keep hosted lint on the same Ruff rules and formatter as local validation."""

    requirements = (ROOT / "server" / "requirements-dev.txt").read_text(
        encoding="utf-8"
    )
    ruff_requirement = next(
        line for line in requirements.splitlines() if line.startswith("ruff==")
    )
    ruff_version = ruff_requirement.partition("==")[2]

    configuration = yaml.safe_load(
        (ROOT / ".pre-commit-config.yaml").read_text(encoding="utf-8")
    )
    ruff_repository = next(
        item
        for item in configuration["repos"]
        if item["repo"] == RUFF_PRE_COMMIT_REPOSITORY
    )

    assert ruff_repository["rev"] == f"v{ruff_version}"
    hook_ids = {hook["id"] for hook in ruff_repository["hooks"]}
    assert {"ruff-check", "ruff-format"} <= hook_ids
