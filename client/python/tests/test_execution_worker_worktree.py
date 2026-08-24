# ruff: noqa: S603, S607
"""Disposable worktree ownership, containment, and canonical-integrity tests."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

from client.python.execution_worker.worktree import create_worktree


def _git(path: Path, *argv: str) -> str:
    return subprocess.run(
        ["git", "-C", str(path), *argv],
        check=True,
        shell=False,
        capture_output=True,
        text=True,
    ).stdout.strip()


def _repository(tmp_path: Path) -> tuple[Path, str]:
    repository = tmp_path / "canonical"
    subprocess.run(["git", "init", str(repository)], check=True, shell=False)
    _git(repository, "config", "user.email", "worker@example.test")
    _git(repository, "config", "user.name", "Worker Test")
    (repository / "README.md").write_text("initial\n", encoding="utf-8")
    _git(repository, "add", "README.md")
    _git(repository, "commit", "-m", "initial")
    return repository, _git(repository, "rev-parse", "HEAD")


def test_owned_worktree_cleanup_retains_run_logs_and_preserves_unrelated_worktree(
    tmp_path: Path,
) -> None:
    canonical, sha = _repository(tmp_path)
    unrelated = tmp_path / "unrelated"
    _git(canonical, "worktree", "add", "--detach", str(unrelated), sha)
    worktree = create_worktree(
        canonical,
        tmp_path / "worker-root",
        sha,
        worker_id="worker-1",
        execution_run_id=11,
    )
    assert _git(worktree.checkout, "rev-parse", "HEAD") == sha
    assert worktree.marker.is_file()
    worktree.cleanup()

    assert not worktree.checkout.exists()
    assert not worktree.run_directory.exists()
    assert unrelated.exists()
    assert unrelated.as_posix() in _git(canonical, "worktree", "list", "--porcelain")
    worktree.verify_canonical_integrity()


def test_cleanup_rejects_a_foreign_ownership_marker(tmp_path: Path) -> None:
    canonical, sha = _repository(tmp_path)
    worktree = create_worktree(
        canonical,
        tmp_path / "worker-root",
        sha,
        worker_id="worker-1",
        execution_run_id=11,
    )
    worktree.marker.write_text("{}", encoding="utf-8")

    with pytest.raises(RuntimeError, match="marker"):
        worktree.cleanup()

    assert worktree.checkout.exists()


def test_rejects_worker_root_and_canonical_repository_overlap(tmp_path: Path) -> None:
    canonical, sha = _repository(tmp_path)

    with pytest.raises(ValueError, match="must not overlap"):
        create_worktree(
            canonical,
            canonical,
            sha,
            worker_id="worker-1",
            execution_run_id=11,
        )
    with pytest.raises(ValueError, match="must not overlap"):
        create_worktree(
            canonical,
            canonical / "worker-root",
            sha,
            worker_id="worker-1",
            execution_run_id=11,
        )


@pytest.mark.skipif(os.name == "nt", reason="POSIX symlink containment coverage")
def test_rejects_worker_root_symlink_escape(tmp_path: Path) -> None:
    canonical, sha = _repository(tmp_path)
    outside = tmp_path / "outside"
    outside.mkdir()
    root_link = tmp_path / "worker-link"
    root_link.symlink_to(outside, target_is_directory=True)

    with pytest.raises(ValueError, match="symlink"):
        create_worktree(
            canonical,
            root_link,
            sha,
            worker_id="worker-1",
            execution_run_id=11,
        )


@pytest.mark.skipif(os.name != "nt", reason="Windows junction containment coverage")
def test_rejects_worker_root_junction_escape(tmp_path: Path) -> None:
    canonical, sha = _repository(tmp_path)
    outside = tmp_path / "outside"
    outside.mkdir()
    junction = tmp_path / "worker-junction"
    subprocess.run(
        ["cmd", "/c", "mklink", "/J", str(junction), str(outside)],
        check=True,
        shell=False,
        capture_output=True,
        text=True,
    )
    try:
        with pytest.raises(ValueError, match="reparse"):
            create_worktree(
                canonical,
                junction,
                sha,
                worker_id="worker-1",
                execution_run_id=11,
            )
    finally:
        subprocess.run(
            ["cmd", "/c", "rmdir", str(junction)],
            check=False,
            shell=False,
            capture_output=True,
            text=True,
        )


def test_cleanup_surfaces_canonical_checkout_mutation(tmp_path: Path) -> None:
    canonical, sha = _repository(tmp_path)
    worktree = create_worktree(
        canonical,
        tmp_path / "worker-root",
        sha,
        worker_id="worker-1",
        execution_run_id=11,
    )
    (canonical / "README.md").write_text("changed\n", encoding="utf-8")

    with pytest.raises(RuntimeError, match="canonical checkout integrity"):
        worktree.cleanup()


@pytest.mark.skipif(os.name == "nt", reason="POSIX checkout replacement coverage")
def test_checkout_integrity_rejects_post_creation_symlink_replacement(
    tmp_path: Path,
) -> None:
    canonical, sha = _repository(tmp_path)
    worktree = create_worktree(
        canonical,
        tmp_path / "worker-root",
        sha,
        worker_id="worker-1",
        execution_run_id=11,
    )
    original = worktree.run_directory / "checkout-original"
    outside = tmp_path / "outside"
    outside.mkdir()
    worktree.checkout.rename(original)
    worktree.checkout.symlink_to(outside, target_is_directory=True)

    with pytest.raises((RuntimeError, ValueError), match=r"(integrity|symlink)"):
        worktree.verify_checkout_integrity()

    worktree.checkout.unlink()
    original.rename(worktree.checkout)
    worktree.cleanup()
