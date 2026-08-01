"""Strict, bounded models for control-plane data before local side effects."""

from __future__ import annotations

import datetime as dt
import math
import re
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from server.execution.evidence import ReuseCandidate

_SHA = re.compile(r"^[0-9a-fA-F]{40}$")
_DIGEST = re.compile(r"^[0-9a-f]{64}$")
_REPOSITORY = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
_RUN_STATUSES = {"assigned", "running", "succeeded", "failed", "timed_out", "cancelled"}
_WORK_ORDER_FIELDS = frozenset(
    {
        "id",
        "schema_version",
        "repository_full_name",
        "commit_sha",
        "manifest_name",
        "manifest_version",
        "manifest_digest",
        "manifest_parameters",
        "required_capabilities",
        "permitted_paths",
        "forbidden_scope_notes",
        "expected_artifact_kinds",
        "approval_policy",
        "status",
        "timeout_seconds",
        "resource_metadata",
        "network_policy",
        "repository_write_allowed",
        "preferred_executor",
        "cost_ceiling",
        "attempt_count",
        "created_at",
        "updated_at",
        "approved_at",
        "queued_at",
        "assigned_at",
        "started_at",
        "finished_at",
        "terminal_reason",
        "reuse_policy",
        "execution_policy_hash",
    }
)
_FORBIDDEN_EXECUTABLE_KEYS = frozenset(
    {
        "argv",
        "command",
        "command_string",
        "shell",
        "shell_command",
        "script",
        "script_contents",
        "executable",
        "executable_path",
    }
)
_REPOSITORY_WRITE_KEYS = frozenset(
    {
        "repository_write",
        "repository_write_allowed",
        "repository_write_capability",
        "repository_write_policy",
    }
)
_MAX_COLLECTION_ITEMS = 128
_MAX_METADATA_DEPTH = 16
_MAX_METADATA_NODES = 4096
_MAX_METADATA_STRING = 4000
_MAX_METADATA_KEY = 128
_MAX_SAFE_INTEGER = (1 << 63) - 1


def _text(
    value: object, field: str, limit: int = 256, *, allow_empty: bool = False
) -> str:
    if (
        not isinstance(value, str)
        or (not value and not allow_empty)
        or len(value) > limit
    ):
        raise ValueError(f"invalid {field}")
    return value


def _integer(
    value: object, field: str, *, minimum: int = 0, maximum: int = _MAX_SAFE_INTEGER
) -> int:
    if (
        not isinstance(value, int)
        or isinstance(value, bool)
        or not minimum <= value <= maximum
    ):
        raise ValueError(f"invalid {field}")
    return value


def _positive(value: object, field: str) -> int:
    return _integer(value, field, minimum=1)


def _mapping(value: object, field: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError(f"invalid {field}")
    if not all(isinstance(key, str) for key in value):
        raise ValueError(f"invalid {field}")
    return value


def _list(
    value: object, field: str, *, limit: int = _MAX_COLLECTION_ITEMS
) -> list[Any]:
    if not isinstance(value, list) or len(value) > limit:
        raise ValueError(f"invalid {field}")
    return value


def _string_list(
    value: object, field: str, *, item_limit: int, limit: int
) -> tuple[str, ...]:
    items = _list(value, field, limit=limit)
    return tuple(
        _text(item, f"{field} entry", item_limit, allow_empty=True) for item in items
    )


def _optional_text(value: object, field: str, limit: int) -> str | None:
    if value is None:
        return None
    return _text(value, field, limit, allow_empty=True)


def _optional_datetime(value: object, field: str) -> dt.datetime | None:
    if value is None:
        return None
    raw = _text(value, field, 64)
    if "T" not in raw:
        raise ValueError(f"invalid {field}")
    try:
        parsed = dt.datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError as error:
        raise ValueError(f"invalid {field}") from error
    return parsed


def _required_datetime(value: object, field: str) -> dt.datetime:
    parsed = _optional_datetime(value, field)
    if parsed is None:
        raise ValueError(f"invalid {field}")
    return parsed


def _optional_number(value: object, field: str) -> float | None:
    if value is None:
        return None
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        raise ValueError(f"invalid {field}")
    parsed = float(value)
    if not math.isfinite(parsed) or parsed < 0:
        raise ValueError(f"invalid {field}")
    return parsed


def _normalized_key(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", value.lower()).strip("_")


def _validated_metadata(
    value: object,
    *,
    field: str,
    allow_root_repository_write_false: bool = False,
) -> object:
    """Validate bounded JSON metadata and reject executable/write policy keys."""

    nodes = 0

    def visit(  # noqa: PLR0912 - recursive JSON type/security cases are explicit
        nested: object, depth: int, *, root: bool = False
    ) -> object:
        nonlocal nodes
        nodes += 1
        if nodes > _MAX_METADATA_NODES or depth > _MAX_METADATA_DEPTH:
            raise ValueError(f"invalid {field}")
        if nested is None or isinstance(nested, bool):
            return nested
        if isinstance(nested, int):
            if abs(nested) > _MAX_SAFE_INTEGER:
                raise ValueError(f"invalid {field}")
            return nested
        if isinstance(nested, float):
            if not math.isfinite(nested):
                raise ValueError(f"invalid {field}")
            return nested
        if isinstance(nested, str):
            return _text(nested, field, _MAX_METADATA_STRING, allow_empty=True)
        if isinstance(nested, Mapping):
            if len(nested) > _MAX_COLLECTION_ITEMS or not all(
                isinstance(key, str) for key in nested
            ):
                raise ValueError(f"invalid {field}")
            result: dict[str, object] = {}
            for key, item in nested.items():
                if len(key) > _MAX_METADATA_KEY:
                    raise ValueError(f"invalid {field}")
                normalized = _normalized_key(key)
                if normalized in _FORBIDDEN_EXECUTABLE_KEYS:
                    raise ValueError(
                        f"{field} must not contain executable field '{normalized}'"
                    )
                if normalized in _REPOSITORY_WRITE_KEYS:
                    allowed = (
                        root
                        and allow_root_repository_write_false
                        and normalized == "repository_write"
                        and item is False
                    )
                    if not allowed:
                        raise ValueError(f"{field} contains repository-write policy")
                result[key] = visit(item, depth + 1)
            return result
        if isinstance(nested, (list, tuple)):
            if len(nested) > _MAX_COLLECTION_ITEMS:
                raise ValueError(f"invalid {field}")
            converted = [visit(item, depth + 1) for item in nested]
            return tuple(converted) if isinstance(nested, tuple) else converted
        raise ValueError(f"invalid {field}")

    return visit(value, 0, root=True)


def _metadata_mapping(
    value: object, *, field: str, allow_root_repository_write_false: bool = False
) -> Mapping[str, Any]:
    mapping = _mapping(value, field)
    validated = _validated_metadata(
        mapping,
        field=field,
        allow_root_repository_write_false=allow_root_repository_write_false,
    )
    assert isinstance(validated, dict)
    return validated


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
    schema_version: int
    repository_full_name: str
    commit_sha: str
    manifest_name: str
    manifest_version: str
    manifest_digest: str
    manifest_parameters: Mapping[str, Any]
    required_capabilities: Mapping[str, Any]
    permitted_paths: tuple[str, ...]
    forbidden_scope_notes: str
    expected_artifact_kinds: tuple[str, ...]
    approval_policy: str
    status: str
    timeout_seconds: int
    resource_metadata: Mapping[str, Any]
    network_policy: str
    repository_write_allowed: bool
    preferred_executor: str | None
    cost_ceiling: float | None
    attempt_count: int
    created_at: dt.datetime
    updated_at: dt.datetime
    approved_at: dt.datetime | None
    queued_at: dt.datetime | None
    assigned_at: dt.datetime | None
    started_at: dt.datetime | None
    finished_at: dt.datetime | None
    terminal_reason: str | None
    reuse_policy: str
    execution_policy_hash: str

    @classmethod
    def from_payload(cls, payload: Mapping[str, Any]) -> AssignedWorkOrder:
        payload = _mapping(payload, "work-order response")
        if set(payload) != _WORK_ORDER_FIELDS:
            raise ValueError("invalid work-order response fields")
        schema_version = _integer(
            payload.get("schema_version"), "schema version", minimum=1, maximum=1
        )
        repository = _repository_name(payload.get("repository_full_name"))
        sha = _text(payload.get("commit_sha"), "commit SHA", 40)
        digest = _text(payload.get("manifest_digest"), "manifest digest", 64)
        if not _SHA.fullmatch(sha) or not _DIGEST.fullmatch(digest):
            raise ValueError("invalid work-order identity")
        execution_policy_hash = _text(
            payload.get("execution_policy_hash"), "execution policy hash", 64
        )
        if not _DIGEST.fullmatch(execution_policy_hash):
            raise ValueError("invalid execution policy hash")
        reuse_policy = _text(payload.get("reuse_policy"), "reuse policy", 32)
        if reuse_policy not in {"never", "allow_exact", "require_exact"}:
            raise ValueError("invalid reuse policy")
        if payload.get("repository_write_allowed") is not False:
            raise ValueError("repository writes are forbidden")
        network = _text(payload.get("network_policy"), "network policy")
        if network not in {"disabled", "worker_restricted"}:
            raise ValueError("invalid network policy")
        approval_policy = _text(payload.get("approval_policy"), "approval policy")
        if approval_policy != "explicit":
            raise ValueError("invalid approval policy")
        status = _text(payload.get("status"), "work-order status")
        if status not in {"assigned", "running"}:
            raise ValueError("work order is not active")
        return cls(
            _positive(payload.get("id"), "work order id"),
            schema_version,
            repository,
            sha,
            _text(payload.get("manifest_name"), "manifest name", 128),
            _text(payload.get("manifest_version"), "manifest version", 64),
            digest,
            _metadata_mapping(
                payload.get("manifest_parameters"), field="manifest_parameters"
            ),
            _metadata_mapping(
                payload.get("required_capabilities"),
                field="required_capabilities",
                allow_root_repository_write_false=True,
            ),
            _string_list(
                payload.get("permitted_paths"),
                "permitted_paths",
                item_limit=512,
                limit=128,
            ),
            _text(
                payload.get("forbidden_scope_notes"),
                "forbidden_scope_notes",
                4000,
                allow_empty=True,
            ),
            _string_list(
                payload.get("expected_artifact_kinds"),
                "expected_artifact_kinds",
                item_limit=128,
                limit=64,
            ),
            approval_policy,
            status,
            _integer(
                payload.get("timeout_seconds"),
                "work order timeout",
                minimum=1,
                maximum=86400,
            ),
            _metadata_mapping(
                payload.get("resource_metadata"), field="resource_metadata"
            ),
            network,
            False,
            _optional_text(
                payload.get("preferred_executor"), "preferred_executor", 128
            ),
            _optional_number(payload.get("cost_ceiling"), "cost_ceiling"),
            _integer(payload.get("attempt_count"), "attempt_count"),
            _required_datetime(payload.get("created_at"), "created_at"),
            _required_datetime(payload.get("updated_at"), "updated_at"),
            _optional_datetime(payload.get("approved_at"), "approved_at"),
            _optional_datetime(payload.get("queued_at"), "queued_at"),
            _optional_datetime(payload.get("assigned_at"), "assigned_at"),
            _optional_datetime(payload.get("started_at"), "started_at"),
            _optional_datetime(payload.get("finished_at"), "finished_at"),
            _optional_text(payload.get("terminal_reason"), "terminal_reason", 4000),
            reuse_policy,
            execution_policy_hash,
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


@dataclass(frozen=True, slots=True)
class ReuseLookup:
    decision: str
    reason: str
    candidate: ReuseCandidate | None

    @classmethod
    def from_payload(cls, payload: Mapping[str, Any]) -> ReuseLookup:
        payload = _mapping(payload, "reuse candidate response")
        if set(payload) != {"decision", "reason", "candidate"}:
            raise ValueError("invalid reuse candidate response fields")
        decision = _text(payload.get("decision"), "reuse decision", 32)
        if decision not in {"candidate_available", "unavailable"}:
            raise ValueError("invalid reuse candidate decision")
        reason = _text(payload.get("reason"), "reuse reason", 64)
        candidate_payload = payload.get("candidate")
        candidate = (
            None
            if candidate_payload is None
            else ReuseCandidate.model_validate(candidate_payload)
        )
        if (decision == "candidate_available") != (candidate is not None):
            raise ValueError("reuse candidate response is inconsistent")
        return cls(decision, reason, candidate)
