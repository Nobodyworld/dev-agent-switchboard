# Every subprocess call in this module uses fixed Git argv assembled only from the
# operator repository registry, an internally generated path, and a validated SHA.
# ruff: noqa: S603, S607
"""Containment-checked detached Git worktrees owned by one worker run."""

from __future__ import annotations

import json
import os
import re
import shutil
import stat
import subprocess
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any

_SHA = re.compile(r"^[0-9a-fA-F]{40}$")
_MARKER_NAME = "ownership.json"


def _absolute(path: Path) -> Path:
    return Path(os.path.abspath(path.expanduser()))


def _contains(child: Path, root: Path) -> bool:
    try:
        child.resolve(strict=False).relative_to(root.resolve(strict=False))
    except ValueError:
        return False
    return True


def _assert_no_reparse_points(path: Path) -> None:
    """Reject symlink and Windows reparse-point ancestry without elevation."""

    absolute = _absolute(path)
    current = Path(absolute.anchor)
    for part in absolute.parts[1:]:
        current /= part
        if not current.exists() and not current.is_symlink():
            continue
        metadata = os.lstat(current)
        attributes = getattr(metadata, "st_file_attributes", 0)
        reparse = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
        if stat.S_ISLNK(metadata.st_mode) or attributes & reparse:
            raise ValueError(f"unsafe symlink or reparse-point path: {current}")


def _assert_contained(path: Path, root: Path, *, label: str) -> None:
    _assert_no_reparse_points(path)
    if not _contains(path, root):
        raise ValueError(f"{label} escaped worker run directory")


def _git(
    canonical: Path, *argv: str, check: bool = True
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", "-C", str(canonical), *argv],
        check=check,
        shell=False,
        capture_output=True,
        text=True,
    )


@dataclass(frozen=True, slots=True)
class CanonicalSnapshot:
    """Stable proof that the canonical checkout source state did not change."""

    head: str
    branch: str
    index: str
    working_tree: str
    untracked: str
    tracked_tree: str


def _canonical_snapshot(canonical: Path) -> CanonicalSnapshot:
    branch = _git(canonical, "symbolic-ref", "--quiet", "--short", "HEAD", check=False)
    status = _git(
        canonical,
        "status",
        "--porcelain=v1",
        "--untracked-files=all",
    ).stdout
    return CanonicalSnapshot(
        head=_git(canonical, "rev-parse", "HEAD").stdout.strip(),
        branch=branch.stdout.strip() if branch.returncode == 0 else "DETACHED",
        index=_git(canonical, "diff", "--cached", "--no-ext-diff", "--binary").stdout,
        working_tree=_git(canonical, "diff", "--no-ext-diff", "--binary").stdout,
        untracked="\n".join(
            line for line in status.splitlines() if line.startswith("??")
        ),
        tracked_tree=_git(canonical, "ls-files", "-s").stdout,
    )


def _registered_worktree(canonical: Path, checkout: Path) -> bool:
    checkout_resolved = checkout.resolve(strict=False)
    lines = _git(canonical, "worktree", "list", "--porcelain").stdout.splitlines()
    for line in lines:
        if not line.startswith("worktree "):
            continue
        candidate = Path(line.removeprefix("worktree "))
        if candidate.resolve(strict=False) == checkout_resolved:
            return True
    return False


def _remove_owned_directory(path: Path, root: Path) -> None:
    _assert_contained(path, root, label="cleanup target")
    if path.exists() or path.is_symlink():
        metadata = os.lstat(path)
        if stat.S_ISLNK(metadata.st_mode):
            raise RuntimeError("refusing to remove symlinked worker checkout")
        shutil.rmtree(path)


@dataclass(slots=True)
class DisposableWorktree:
    canonical: Path
    root: Path
    run_directory: Path
    checkout: Path
    sha: str
    worker_id: str
    execution_run_id: int
    run_identity: str
    _canonical_before: CanonicalSnapshot

    @property
    def marker(self) -> Path:
        return self.run_directory / _MARKER_NAME

    @property
    def logs(self) -> Path:
        logs = self.run_directory / "logs"
        _assert_contained(logs, self.run_directory, label="logs")
        logs.mkdir(parents=True, exist_ok=True)
        return logs

    def _expected_marker(self) -> dict[str, Any]:
        return {
            "canonical_repository": str(self.canonical),
            "execution_run_id": self.execution_run_id,
            "requested_sha": self.sha.lower(),
            "run_identity": self.run_identity,
            "worker_id": self.worker_id,
        }

    def _verify_ownership(self) -> None:
        if self.run_directory == self.root:
            raise RuntimeError("refusing to clean worker root")
        _assert_contained(self.run_directory, self.root, label="run directory")
        _assert_contained(self.checkout, self.run_directory, label="checkout")
        if not self.marker.is_file():
            raise RuntimeError("worker ownership marker is missing")
        try:
            marker = json.loads(self.marker.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            raise RuntimeError("worker ownership marker is unreadable") from error
        if marker != self._expected_marker():
            raise RuntimeError("worker ownership marker does not match this run")

    def verify_canonical_integrity(self) -> None:
        if _canonical_snapshot(self.canonical) != self._canonical_before:
            raise RuntimeError("canonical checkout integrity changed")

    def cleanup(self) -> None:
        """Remove only this registered disposable checkout; retain run logs/record."""

        self._verify_ownership()
        if _registered_worktree(self.canonical, self.checkout):
            _git(self.canonical, "worktree", "remove", "--force", str(self.checkout))
        if self.checkout.exists() or self.checkout.is_symlink():
            _remove_owned_directory(self.checkout, self.run_directory)
        self.verify_canonical_integrity()


def create_worktree(
    canonical: Path,
    root: Path,
    sha: str,
    *,
    worker_id: str,
    execution_run_id: int,
) -> DisposableWorktree:
    """Create an owned detached worktree without touching canonical source state."""

    if not _SHA.fullmatch(sha):
        raise ValueError("requested SHA must be exactly 40 hexadecimal characters")
    if not worker_id or execution_run_id < 1:
        raise ValueError("worker run ownership identity is required")
    canonical = _absolute(canonical)
    root = _absolute(root)
    _assert_no_reparse_points(canonical)
    _assert_no_reparse_points(root)
    if not canonical.is_dir() or not (canonical / ".git").exists():
        raise ValueError("configured repository is not a Git checkout")
    if canonical == root or _contains(canonical, root) or _contains(root, canonical):
        raise ValueError("worker root and canonical repository must not overlap")
    check = _git(canonical, "cat-file", "-e", f"{sha}^{{commit}}", check=False)
    if check.returncode != 0:
        raise ValueError("requested SHA is not a local commit")
    root.mkdir(parents=True, exist_ok=True)
    _assert_no_reparse_points(root)
    run_identity = uuid.uuid4().hex
    run = root / f"run-{run_identity}"
    checkout = run / "checkout"
    _assert_contained(run, root, label="run directory")
    run.mkdir()
    before = _canonical_snapshot(canonical)
    worktree = DisposableWorktree(
        canonical=canonical,
        root=root,
        run_directory=run,
        checkout=checkout,
        sha=sha,
        worker_id=worker_id,
        execution_run_id=execution_run_id,
        run_identity=run_identity,
        _canonical_before=before,
    )
    worktree.marker.write_text(
        json.dumps(worktree._expected_marker(), sort_keys=True), encoding="utf-8"
    )
    try:
        _git(canonical, "worktree", "add", "--detach", str(checkout), sha)
        _assert_contained(checkout, run, label="checkout")
        head = _git(checkout, "rev-parse", "HEAD").stdout.strip()
        if head.lower() != sha.lower():
            raise RuntimeError("detached worktree HEAD mismatch")
    except BaseException:
        # Creation may have registered a worktree before a later verification fails.
        # Remove only that exact Git registration and its owned checkout directory.
        if _registered_worktree(canonical, checkout):
            _git(canonical, "worktree", "remove", "--force", str(checkout))
        if checkout.exists() or checkout.is_symlink():
            _remove_owned_directory(checkout, run)
        worktree.verify_canonical_integrity()
        raise
    return worktree


__all__ = ["CanonicalSnapshot", "DisposableWorktree", "create_worktree"]
