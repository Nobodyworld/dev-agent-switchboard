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


def _mapping(value: object, field: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError(f"invalid {field}")
    if not all(isinstance(key, str) for key in value):
        raise ValueError(f"invalid {field}")
    return value


def _list(value: object, field: str) -> list[Any]:
    if not isinstance(value, list):
        raise ValueError(f"invalid {field}")
    return value


def _repository_name(value: object) -> str:
    repository = _text(value, "repository")
    if not _REPOSITORY.fullmatch(repository):
        raise ValueError("invalid work-order identity")
    owner, name = repository.split("/", maxsplit=1)
    if owner in {".", ".."} or name in {".", ".."}:
        raise ValueError("invalid work-order identity")
    return repository


@dataclass(frozen=True, slots=True)
class SafeManifest:
    name: str
    version: str
    digest: str
    timeout_seconds: int
    network_policy: str
    repository_write_policy: str
    schema_version: int
    required_capabilities: Mapping[str, Any]
    fixed_step_metadata: tuple[Mapping[str, Any], ...]
    environment_policy: Mapping[str, Any]
    artifact_declarations: tuple[Mapping[str, Any], ...]
    description: str
    trusted_registry_source: str

    @classmethod
    def from_payload(cls, payload: Mapping[str, Any]) -> SafeManifest:
        payload = _mapping(payload, "manifest response")
        digest = _text(payload.get("digest"), "manifest digest", 64)
        if not _DIGEST.fullmatch(digest):
            raise ValueError("invalid manifest digest")
        network = _text(payload.get("network_policy"), "network policy")
        write = _text(payload.get("repository_write_policy"), "repository write policy")
        if network not in {"disabled", "worker_restricted"} or write != "read_only":
            raise ValueError("unsafe manifest policy")
        metadata = _list(payload.get("fixed_step_metadata"), "fixed_step_metadata")
        artifacts = _list(payload.get("artifact_declarations"), "artifact_declarations")
        required_capabilities = _mapping(
            payload.get("required_capabilities"), "required_capabilities"
        )
        environment_policy = _mapping(
            payload.get("environment_policy"), "environment_policy"
        )
        if not all(isinstance(item, Mapping) for item in metadata + artifacts):
            raise ValueError("invalid manifest metadata")
        return cls(
            _text(payload.get("name"), "manifest name"),
            _text(payload.get("version"), "manifest version"),
            digest,
            _positive(payload.get("timeout_seconds"), "manifest timeout"),
            network,
            write,
            _positive(payload.get("schema_version"), "manifest schema version"),
            required_capabilities,
            tuple(_mapping(item, "fixed_step_metadata") for item in metadata),
            environment_policy,
            tuple(_mapping(item, "artifact_declarations") for item in artifacts),
            _text(payload.get("description"), "manifest description", 4000),
            _text(payload.get("trusted_registry_source"), "manifest registry source"),
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
    required_capabilities: Mapping[str, Any]

    @classmethod
    def from_payload(cls, payload: Mapping[str, Any]) -> AssignedWorkOrder:
        payload = _mapping(payload, "work-order response")
        repository = _repository_name(payload.get("repository_full_name"))
        sha = _text(payload.get("commit_sha"), "commit SHA", 40)
        digest = _text(payload.get("manifest_digest"), "manifest digest", 64)
        if not _SHA.fullmatch(sha) or not _DIGEST.fullmatch(digest):
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
            _mapping(payload.get("required_capabilities"), "required_capabilities"),
        )


@dataclass(frozen=True, slots=True)
class Checkout:
    run_id: int | None
    work_order_id: int | None
    reason: str | None

    @classmethod
    def from_payload(cls, payload: Mapping[str, Any]) -> Checkout:
        payload = _mapping(payload, "checkout response")
        run = payload.get("run")
        if run is None:
            reason = payload.get("reason")
            return cls(None, None, _text(reason, "checkout reason") if reason else None)
        run = _mapping(run, "checkout run")
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
        payload = _mapping(payload, "run response")
        status = _text(payload.get("status"), "run status")
        if status not in _RUN_STATUSES:
            raise ValueError("invalid run status")
        return cls(_positive(payload.get("id"), "run id"), status)
