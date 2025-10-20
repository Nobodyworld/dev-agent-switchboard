"""Property-style tests for the live file store helpers."""

from __future__ import annotations

import random
import string
from collections.abc import Iterable
from pathlib import Path

import pytest
from fastapi import HTTPException

from server import file_store
from server.file_store import FILES_ROOT, full_path


def _candidate_paths(rng: random.Random, *, count: int) -> Iterable[str]:
    alphabet = string.ascii_letters + string.digits + "._-/"
    for _ in range(count):
        length = rng.randint(0, 40)
        yield "".join(rng.choice(alphabet) for _ in range(length))


def test_full_path_never_escapes_storage_root() -> None:
    rng = random.Random(1337)  # noqa: S311 - deterministic fuzzing for tests
    for candidate in _candidate_paths(rng, count=200):
        try:
            resolved = full_path(candidate)
        except HTTPException:
            continue

        assert Path(resolved).is_relative_to(Path(FILES_ROOT)), candidate
        assert not str(resolved).startswith(".."), candidate


@pytest.mark.parametrize(
    "malicious",
    [
        "../secret",  # traversal
        "../../etc/passwd",
        "..\\evil",
        "//absolute/path",
        "/absolute",  # absolute path after stripping
        "\\windows\\path",
    ],
)
def test_full_path_rejects_malicious_paths(malicious: str) -> None:
    with pytest.raises(HTTPException):
        full_path(malicious)


def test_ensure_root_detects_unwritable(monkeypatch, tmp_path):
    root = tmp_path / "store"
    monkeypatch.setattr(file_store, "FILES_ROOT", root)

    original_access = file_store.os.access

    def fake_access(path, mode):
        if Path(path) == root:
            return False
        return original_access(path, mode)

    monkeypatch.setattr(file_store.os, "access", fake_access)

    with pytest.raises(HTTPException):
        file_store.ensure_root()


def test_write_bytes_atomic_replaces_existing(tmp_path):
    target = tmp_path / "data.bin"
    file_store._write_bytes_atomic(target, b"first")
    assert target.read_bytes() == b"first"
    file_store._write_bytes_atomic(target, b"second")
    assert target.read_bytes() == b"second"


def test_write_bytes_atomic_cleans_temporary_files(monkeypatch, tmp_path):
    target = tmp_path / "data.bin"

    def failing_replace(_self, _other):  # pragma: no cover - executed in test
        raise RuntimeError("boom")

    monkeypatch.setattr(file_store.Path, "replace", failing_replace)

    with pytest.raises(RuntimeError):
        file_store._write_bytes_atomic(target, b"payload")

    leftovers = [
        path
        for path in target.parent.iterdir()
        if path.name.startswith(f".{target.name}.")
    ]
    assert leftovers == []
