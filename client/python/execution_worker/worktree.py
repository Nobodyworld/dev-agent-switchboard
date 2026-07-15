# Every subprocess call in this module uses fixed Git argv assembled only from the
# operator repository registry, an internally generated path, and a validated SHA.
# ruff: noqa: S603, S607
"""Containment-checked detached Git worktrees owned by the worker."""

from __future__ import annotations

import re
import shutil
import subprocess
import uuid
from dataclasses import dataclass
from pathlib import Path

_SHA = re.compile(r"^[0-9a-fA-F]{40}$")


def _contained(child: Path, root: Path) -> bool:
    try:
        child.resolve(strict=False).relative_to(root.resolve(strict=False))
    except ValueError:
        return False
    return True


@dataclass(slots=True)
class DisposableWorktree:
    canonical: Path
    root: Path
    run_directory: Path
    checkout: Path
    sha: str

    def cleanup(self) -> None:
        if self.run_directory == self.root or not _contained(
            self.run_directory, self.root
        ):
            raise RuntimeError("refusing unsafe worker cleanup")
        subprocess.run(
            [
                "git",
                "-C",
                str(self.canonical),
                "worktree",
                "remove",
                "--force",
                str(self.checkout),
            ],
            check=True,
            shell=False,
            capture_output=True,
            text=True,
        )
        if self.run_directory.exists():
            shutil.rmtree(self.run_directory)
        subprocess.run(
            [
                "git",
                "-C",
                str(self.canonical),
                "worktree",
                "prune",
            ],
            check=True,
            shell=False,
            capture_output=True,
            text=True,
        )


def create_worktree(canonical: Path, root: Path, sha: str) -> DisposableWorktree:
    if not _SHA.fullmatch(sha):
        raise ValueError("requested SHA must be exactly 40 hexadecimal characters")
    canonical = canonical.resolve(strict=True)
    root = root.resolve(strict=False)
    if not canonical.is_dir() or not (canonical / ".git").exists():
        raise ValueError("configured repository is not a Git checkout")
    if not root.is_absolute() or _contained(canonical, root):
        raise ValueError("worker root is unsafe")
    check = subprocess.run(
        [
            "git",
            "-C",
            str(canonical),
            "cat-file",
            "-e",
            f"{sha}^{{commit}}",
        ],
        check=False,
        shell=False,
        capture_output=True,
        text=True,
    )
    if check.returncode != 0:
        raise ValueError("requested SHA is not a local commit")
    root.mkdir(parents=True, exist_ok=True)
    run = root / f"run-{uuid.uuid4().hex}"
    checkout = run / "checkout"
    if not _contained(run, root):
        raise ValueError("generated run path escaped root")
    run.mkdir()
    try:
        subprocess.run(
            [
                "git",
                "-C",
                str(canonical),
                "worktree",
                "add",
                "--detach",
                str(checkout),
                sha,
            ],
            check=True,
            shell=False,
            capture_output=True,
            text=True,
        )
        head = subprocess.run(
            [
                "git",
                "-C",
                str(checkout),
                "rev-parse",
                "HEAD",
            ],
            check=True,
            shell=False,
            capture_output=True,
            text=True,
        ).stdout.strip()
        if head.lower() != sha.lower():
            raise RuntimeError("detached worktree HEAD mismatch")
    except BaseException:
        if run.exists() and _contained(run, root):
            shutil.rmtree(run)
        raise
    return DisposableWorktree(canonical, root, run, checkout, sha)
