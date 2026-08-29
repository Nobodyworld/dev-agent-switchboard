"""Strict operator configuration; local paths never enter public reports."""

from __future__ import annotations

import ipaddress
import json
import re
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path, PurePath
from typing import Any, Literal, cast

_SHA = re.compile(r"^[0-9a-f]{40}$")
_DIGEST = re.compile(r"^[0-9a-f]{64}$")
_REPOSITORY = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
_IDENTITY = re.compile(r"^[A-Za-z0-9_.-]{1,128}$")
_MANIFEST = re.compile(r"^[a-z0-9][a-z0-9-]{0,127}$")
_MAX_PATH_TEXT = 1024
_ALLOWED_KEYS = frozenset(
    {
        "schema_version",
        "repository_full_name",
        "canonical_checkout",
        "target_sha",
        "manifest_name",
        "manifest_version",
        "expected_manifest_digest",
        "mode",
        "runtime_root",
        "worker_id",
        "worker_display_name",
        "host",
        "port",
        "routing_policy",
        "work_order_timeout_seconds",
        "startup_timeout_seconds",
        "terminal_timeout_seconds",
        "shutdown_timeout_seconds",
        "poll_interval_seconds",
        "http_timeout_seconds",
        "evidence_retention_days",
        "maximum_artifact_count",
        "maximum_artifact_bytes",
        "maximum_total_evidence_bytes",
        "report_maximum_bytes",
    }
)


class OperatorConfigurationError(ValueError):
    """Safe configuration rejection containing field identities only."""


def _text(payload: Mapping[str, Any], key: str, *, maximum: int) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value or len(value) > maximum:
        raise OperatorConfigurationError(f"invalid_configuration:{key}")
    return value


def _integer(
    payload: Mapping[str, Any], key: str, default: int, minimum: int, maximum: int
) -> int:
    value = payload.get(key, default)
    if (
        not isinstance(value, int)
        or isinstance(value, bool)
        or not minimum <= value <= maximum
    ):
        raise OperatorConfigurationError(f"invalid_configuration:{key}")
    return value


def _number(
    payload: Mapping[str, Any], key: str, default: float, minimum: float, maximum: float
) -> float:
    value = payload.get(key, default)
    if (
        not isinstance(value, (int, float))
        or isinstance(value, bool)
        or not minimum <= float(value) <= maximum
    ):
        raise OperatorConfigurationError(f"invalid_configuration:{key}")
    return float(value)


def _absolute_path(value: str, field: str) -> Path:
    if "\x00" in value or len(value) > _MAX_PATH_TEXT:
        raise OperatorConfigurationError(f"invalid_configuration:{field}")
    path = Path(value)
    if not path.is_absolute() or any(part == ".." for part in PurePath(value).parts):
        raise OperatorConfigurationError(f"invalid_configuration:{field}")
    if value.startswith(("\\\\", "//")):
        raise OperatorConfigurationError(f"invalid_configuration:{field}")
    return path


@dataclass(frozen=True, slots=True)
class OperatorLifecycleConfig:
    """Immutable validated configuration for one new operator-owned runtime."""

    repository_full_name: str
    canonical_checkout: Path
    target_sha: str
    manifest_name: str
    manifest_version: str
    expected_manifest_digest: str | None
    mode: Literal["fresh-only", "fresh-then-exact-reuse"]
    runtime_root: Path
    worker_id: str
    worker_display_name: str
    host: str = "127.0.0.1"
    port: int = 8765
    routing_policy: Literal["first_available"] = "first_available"
    work_order_timeout_seconds: int = 3600
    startup_timeout_seconds: float = 30.0
    terminal_timeout_seconds: float = 3900.0
    shutdown_timeout_seconds: float = 15.0
    poll_interval_seconds: float = 1.0
    http_timeout_seconds: float = 10.0
    evidence_retention_days: int = 14
    maximum_artifact_count: int = 128
    maximum_artifact_bytes: int = 64 * 1024 * 1024
    maximum_total_evidence_bytes: int = 512 * 1024 * 1024
    report_maximum_bytes: int = 128 * 1024

    @classmethod
    def from_mapping(  # noqa: PLR0912 - each security boundary is explicit
        cls, payload: Mapping[str, Any]
    ) -> OperatorLifecycleConfig:
        if not isinstance(payload, Mapping):
            raise OperatorConfigurationError("invalid_configuration:root")
        if set(payload) - _ALLOWED_KEYS:
            raise OperatorConfigurationError("invalid_configuration:unknown_field")
        if payload.get("schema_version") != 1:
            raise OperatorConfigurationError("invalid_configuration:schema_version")
        repository = _text(payload, "repository_full_name", maximum=255)
        sha = _text(payload, "target_sha", maximum=40)
        manifest_name = _text(payload, "manifest_name", maximum=128)
        manifest_version = _text(payload, "manifest_version", maximum=64)
        mode = _text(payload, "mode", maximum=32)
        worker_id = _text(payload, "worker_id", maximum=128)
        display_name = _text(payload, "worker_display_name", maximum=255)
        host = cast(str, payload.get("host", "127.0.0.1"))
        routing_policy = cast(str, payload.get("routing_policy", "first_available"))
        expected_digest = payload.get("expected_manifest_digest")
        if not _REPOSITORY.fullmatch(repository):
            raise OperatorConfigurationError(
                "invalid_configuration:repository_full_name"
            )
        if not _SHA.fullmatch(sha):
            raise OperatorConfigurationError("invalid_configuration:target_sha")
        if not _MANIFEST.fullmatch(manifest_name):
            raise OperatorConfigurationError("invalid_configuration:manifest_name")
        if not _IDENTITY.fullmatch(worker_id):
            raise OperatorConfigurationError("invalid_configuration:worker_id")
        if mode not in {"fresh-only", "fresh-then-exact-reuse"}:
            raise OperatorConfigurationError("invalid_configuration:mode")
        if routing_policy != "first_available":
            raise OperatorConfigurationError("invalid_configuration:routing_policy")
        if not isinstance(host, str) or host not in {"127.0.0.1", "::1", "localhost"}:
            raise OperatorConfigurationError("invalid_configuration:host")
        try:
            if host != "localhost" and not ipaddress.ip_address(host).is_loopback:
                raise ValueError
        except ValueError as error:
            raise OperatorConfigurationError("invalid_configuration:host") from error
        if expected_digest is not None and (
            not isinstance(expected_digest, str)
            or not _DIGEST.fullmatch(expected_digest)
        ):
            raise OperatorConfigurationError(
                "invalid_configuration:expected_manifest_digest"
            )
        canonical = payload.get("canonical_checkout")
        runtime = payload.get("runtime_root")
        if not isinstance(canonical, str):
            raise OperatorConfigurationError("invalid_configuration:canonical_checkout")
        if not isinstance(runtime, str):
            raise OperatorConfigurationError("invalid_configuration:runtime_root")
        total_evidence = _integer(
            payload, "maximum_total_evidence_bytes", 512 * 1024 * 1024, 1, 1024**4
        )
        artifact_bytes = _integer(
            payload, "maximum_artifact_bytes", 64 * 1024 * 1024, 1, 1024**4
        )
        if artifact_bytes > total_evidence:
            raise OperatorConfigurationError("invalid_configuration:evidence_limits")
        return cls(
            repository_full_name=repository,
            canonical_checkout=_absolute_path(canonical, "canonical_checkout"),
            target_sha=sha,
            manifest_name=manifest_name,
            manifest_version=manifest_version,
            expected_manifest_digest=expected_digest,
            mode=cast(Literal["fresh-only", "fresh-then-exact-reuse"], mode),
            runtime_root=_absolute_path(runtime, "runtime_root"),
            worker_id=worker_id,
            worker_display_name=display_name,
            host=host,
            port=_integer(payload, "port", 8765, 1024, 65535),
            routing_policy=cast(Literal["first_available"], routing_policy),
            work_order_timeout_seconds=_integer(
                payload, "work_order_timeout_seconds", 3600, 1, 86400
            ),
            startup_timeout_seconds=_number(
                payload, "startup_timeout_seconds", 30.0, 1.0, 600.0
            ),
            terminal_timeout_seconds=_number(
                payload, "terminal_timeout_seconds", 3900.0, 1.0, 86400.0
            ),
            shutdown_timeout_seconds=_number(
                payload, "shutdown_timeout_seconds", 15.0, 1.0, 120.0
            ),
            poll_interval_seconds=_number(
                payload, "poll_interval_seconds", 1.0, 1.0, 30.0
            ),
            http_timeout_seconds=_number(
                payload, "http_timeout_seconds", 10.0, 0.1, 120.0
            ),
            evidence_retention_days=_integer(
                payload, "evidence_retention_days", 14, 1, 3650
            ),
            maximum_artifact_count=_integer(
                payload, "maximum_artifact_count", 128, 1, 128
            ),
            maximum_artifact_bytes=artifact_bytes,
            maximum_total_evidence_bytes=total_evidence,
            report_maximum_bytes=_integer(
                payload, "report_maximum_bytes", 128 * 1024, 4096, 1024 * 1024
            ),
        )

    @classmethod
    def from_file(cls, path: Path) -> OperatorLifecycleConfig:
        try:
            raw = path.read_bytes()
            if len(raw) > 64 * 1024:
                raise OperatorConfigurationError("invalid_configuration:file_size")
            payload = json.loads(raw.decode("utf-8"))
        except OperatorConfigurationError:
            raise
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
            raise OperatorConfigurationError("invalid_configuration:file") from error
        if not isinstance(payload, Mapping):
            raise OperatorConfigurationError("invalid_configuration:root")
        return cls.from_mapping(payload)
