"""Strict, bounded models for control-plane data before local side effects."""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

_SHA = re.compile(r"^[0-9a-fA-F]{40}$")
_DIGEST = re.compile(r"^[0-9a-f]{64}$")
_REPOSITORY = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
_RUN_STATUSES = {"assigned", "running", "succeeded", "failed", "timed_out", "cancelled"}


def _text(value: object, field: str, limit: int = 256) -> str:
    if not isinstance(value, str) or not value or len(value) > limit:
        raise ValueError(f"invalid {field}")
    return value


def _positive(value: object, field: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < 1:
        raise ValueError(f"invalid {field}")
    return value


@dataclass(frozen=True, slots=True)
class SafeManifest:
    name: str
    version: str
    digest: str
    timeout_seconds: int
    network_policy: str
    repository_write_policy: str

    @classmethod
    def from_payload(cls, payload: Mapping[str, Any]) -> SafeManifest:
        digest = _text(payload.get("digest"), "manifest digest", 64)
        if not _DIGEST.fullmatch(digest):
            raise ValueError("invalid manifest digest")
        network = _text(payload.get("network_policy"), "network policy")
        write = _text(payload.get("repository_write_policy"), "repository write policy")
        if network not in {"disabled", "worker_restricted"} or write != "read_only":
            raise ValueError("unsafe manifest policy")
        return cls(
            _text(payload.get("name"), "manifest name"),
            _text(payload.get("version"), "manifest version"),
            digest,
            _positive(payload.get("timeout_seconds"), "manifest timeout"),
            network,
            write,
        )


@dataclass(frozen=True, slots=True)
class AssignedWorkOrder:
    id: int
    repository_full_name: str
    commit_sha: str
    manifest_name: str
    manifest_version: str
    manifest_digest: str
    timeout_seconds: int
    network_policy: str

    @classmethod
    def from_payload(cls, payload: Mapping[str, Any]) -> AssignedWorkOrder:
        repository = _text(payload.get("repository_full_name"), "repository")
        sha = _text(payload.get("commit_sha"), "commit SHA", 40)
        digest = _text(payload.get("manifest_digest"), "manifest digest", 64)
        if (
            not _REPOSITORY.fullmatch(repository)
            or not _SHA.fullmatch(sha)
            or not _DIGEST.fullmatch(digest)
        ):
            raise ValueError("invalid work-order identity")
        if payload.get("repository_write_allowed") is not False:
            raise ValueError("repository writes are forbidden")
        network = _text(payload.get("network_policy"), "network policy")
        if network not in {"disabled", "worker_restricted"}:
            raise ValueError("invalid network policy")
        return cls(
            _positive(payload.get("id"), "work order id"),
            repository,
            sha,
            _text(payload.get("manifest_name"), "manifest name"),
            _text(payload.get("manifest_version"), "manifest version"),
            digest,
            _positive(payload.get("timeout_seconds"), "work order timeout"),
            network,
        )


@dataclass(frozen=True, slots=True)
class Checkout:
    run_id: int | None
    work_order_id: int | None
    reason: str | None

    @classmethod
    def from_payload(cls, payload: Mapping[str, Any]) -> Checkout:
        run = payload.get("run")
        if run is None:
            reason = payload.get("reason")
            return cls(None, None, _text(reason, "checkout reason") if reason else None)
        if not isinstance(run, Mapping):
            raise ValueError("invalid checkout run")
        status = _text(run.get("status"), "run status")
        if status not in {"assigned", "running"}:
            raise ValueError("checkout run is not active")
        return cls(
            _positive(run.get("id"), "run id"),
            _positive(run.get("work_order_id"), "work order id"),
            None,
        )


@dataclass(frozen=True, slots=True)
class ExecutionRun:
    id: int
    status: str

    @classmethod
    def from_payload(cls, payload: Mapping[str, Any]) -> ExecutionRun:
        status = _text(payload.get("status"), "run status")
        if status not in _RUN_STATUSES:
            raise ValueError("invalid run status")
        return cls(_positive(payload.get("id"), "run id"), status)
