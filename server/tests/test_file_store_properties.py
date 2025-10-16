"""Property-style tests for the live file store helpers."""

from __future__ import annotations

import random
import string
from pathlib import Path
from typing import Iterable

import pytest
from fastapi import HTTPException

from server.file_store import FILES_ROOT, full_path


def _candidate_paths(rng: random.Random, *, count: int) -> Iterable[str]:
    alphabet = string.ascii_letters + string.digits + "._-/"
    for _ in range(count):
        length = rng.randint(0, 40)
        yield "".join(rng.choice(alphabet) for _ in range(length))


def test_full_path_never_escapes_storage_root() -> None:
    rng = random.Random(1337)
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
