"""Server-owned policy for excluding absolute local paths from API text."""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence

_WINDOWS_DRIVE_PATH = re.compile(r"(?i)(?<![A-Za-z0-9/\\])[A-Z]:[\\/]")
_WINDOWS_UNC_PATH = re.compile(r"(?<![:/\\A-Za-z0-9])\\{2,}(?!\s)")
_FILE_URI = re.compile(r"(?i)(?<![A-Za-z0-9+.-])file:")
_LOCAL_DATABASE_URI = re.compile(
    r"(?i)(?<![A-Za-z0-9+.-])sqlite(?:\+[A-Za-z0-9_.-]+)?:///"
)
_SAFE_NONLOCAL_URI = re.compile(
    r"(?i)(?<![A-Za-z0-9+.-])"
    r"(?:https?|wss?|ftps?|ssh|git|mailto|urn):"
    r"[^\s\r\n<>\"']+"
)
# A rooted POSIX path starts with a slash that is neither part of a relative
# ``./``/``../`` reference nor followed by whitespace.  Requiring the next
# character to be non-whitespace keeps ordinary rendered expressions such as
# ``tmp_path / "child.pid"`` and ``1 / 2`` out of the local-path policy while
# still rejecting ``/``, ``/tmp``, and prose such as ``retained at /var/log``.
_POSIX_ROOTED_PATH = re.compile(r"(?<![/A-Za-z0-9.])/(?!\s)")


def contains_absolute_local_path(value: str) -> bool:
    """Return whether text contains a prohibited absolute local path shape.

    Common non-local URI schemes are intentionally ignored. ``file:`` URIs are
    rejected because they identify local filesystem resources, while safe
    relative references contain no rooted path prefix and remain accepted.
    """

    if (
        _FILE_URI.search(value)
        or _LOCAL_DATABASE_URI.search(value)
        or _WINDOWS_DRIVE_PATH.search(value)
        or _WINDOWS_UNC_PATH.search(value)
    ):
        return True
    without_safe_uris = _SAFE_NONLOCAL_URI.sub("", value)
    return _POSIX_ROOTED_PATH.search(without_safe_uris) is not None


def validate_no_absolute_local_path(value: str) -> str:
    """Return safe text or raise when it contains an absolute local path."""

    if contains_absolute_local_path(value):
        raise ValueError("text must not contain an absolute local path")
    return value


def validate_optional_no_absolute_local_path(value: str | None) -> str | None:
    """Validate optional API text while preserving a missing value."""

    if value is None:
        return None
    return validate_no_absolute_local_path(value)


def validate_no_absolute_local_paths(value: object) -> object:
    """Recursively validate every string in one bounded JSON-like value."""

    if isinstance(value, str):
        return validate_no_absolute_local_path(value)
    if isinstance(value, Mapping):
        for nested in value.values():
            validate_no_absolute_local_paths(nested)
    elif isinstance(value, Sequence) and not isinstance(value, (bytes, bytearray)):
        for nested in value:
            validate_no_absolute_local_paths(nested)
    return value


__all__ = [
    "contains_absolute_local_path",
    "validate_no_absolute_local_path",
    "validate_no_absolute_local_paths",
    "validate_optional_no_absolute_local_path",
]
