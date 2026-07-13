"""Worker capability comparison helpers for execution checkout."""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Protocol

from .enums import NetworkPolicy

_VERSION_PATTERN = re.compile(r"^(\d+)(?:\.(\d+))?(?:\.(\d+))?")
_BOOLEAN_CAPABILITIES = {
    "docker": ("docker_available", "docker_not_available"),
    "gpu": ("gpu_available", "gpu_not_available"),
    "unity": ("unity_available", "unity_not_available"),
    "desktop": ("desktop_available", "desktop_not_available"),
}


class WorkerCapabilitySource(Protocol):
    """Fields needed to determine whether a worker can safely receive work."""

    operating_system: str
    architecture: str
    python_version: str | None
    node_version: str | None
    docker_available: bool
    browsers: list[str]
    gpu_available: bool
    unity_available: bool
    desktop_available: bool
    capabilities: dict[str, Any]
    network_policy_capability: NetworkPolicy
    repository_write_capability: bool


@dataclass(frozen=True, slots=True)
class CapabilityMatch:
    """Eligibility decision plus useful machine-readable mismatch reasons."""

    eligible: bool
    reasons: tuple[str, ...]


def match_worker_capabilities(
    worker: WorkerCapabilitySource,
    *,
    manifest_requirements: Mapping[str, Any],
    requested_requirements: Mapping[str, Any],
    network_policy: NetworkPolicy,
) -> CapabilityMatch:
    """Evaluate every trusted and request-scoped capability requirement."""

    reasons: list[str] = []
    _match_capability_mapping(worker, manifest_requirements, reasons)
    _match_capability_mapping(worker, requested_requirements, reasons)
    _match_network_policy(worker, network_policy, reasons)
    if worker.repository_write_capability:
        reasons.append("repository_write_capability_must_be_false")
    return CapabilityMatch(eligible=not reasons, reasons=tuple(dict.fromkeys(reasons)))


def _match_capability_mapping(
    worker: WorkerCapabilitySource,
    requirements: Mapping[str, Any],
    reasons: list[str],
) -> None:
    for name, required in requirements.items():
        mismatch = _capability_mismatch(worker, str(name).lower(), required)
        if mismatch is not None:
            reasons.append(mismatch)


def _capability_mismatch(
    worker: WorkerCapabilitySource, name: str, required: Any
) -> str | None:
    mismatch: str | None
    if name == "operating_system":
        mismatch = _platform_mismatch(
            worker.operating_system,
            required,
            name="operating_system",
        )
    elif name == "architecture":
        mismatch = _platform_mismatch(
            worker.architecture,
            required,
            name="architecture",
        )
    elif name in {"python", "node"}:
        mismatch = _version_mismatch(worker, name, required)
    elif name in _BOOLEAN_CAPABILITIES:
        mismatch = _boolean_capability_mismatch(worker, name, required)
    elif name in {"browser", "browsers"}:
        mismatch = _browser_mismatch(worker, required)
    elif name == "repository_write":
        mismatch = _repository_write_mismatch(required)
    elif name == "network_policy":
        mismatch = _network_policy_mismatch(worker, required)
    else:
        mismatch = _custom_capability_mismatch(worker, name, required)
    return mismatch


def _platform_mismatch(actual: str, required: Any, *, name: str) -> str | None:
    allowed = _as_string_set(required)
    if allowed is None:
        return f"invalid_capability_requirement:{name}"
    if allowed and actual.lower() not in allowed:
        return f"{name}_not_supported"
    return None


def _version_mismatch(
    worker: WorkerCapabilitySource, name: str, required: Any
) -> str | None:
    actual = worker.python_version if name == "python" else worker.node_version
    minimum = _minimum_version(required)
    if minimum is None:
        return f"invalid_capability_requirement:{name}"
    if not _at_least(actual, minimum):
        return f"{name}_version_too_old_or_missing"
    return None


def _boolean_capability_mismatch(
    worker: WorkerCapabilitySource, name: str, required: Any
) -> str | None:
    if not isinstance(required, bool):
        return f"invalid_capability_requirement:{name}"
    attribute, reason = _BOOLEAN_CAPABILITIES[name]
    if required is True and not getattr(worker, attribute):
        return reason
    return None


def _browser_mismatch(worker: WorkerCapabilitySource, required: Any) -> str | None:
    required_browsers = _as_string_set(required)
    if required_browsers is None:
        return "invalid_capability_requirement:browsers"
    available_browsers = {browser.lower() for browser in worker.browsers}
    if not required_browsers.issubset(available_browsers):
        return "browser_capability_missing"
    return None


def _custom_capability_mismatch(
    worker: WorkerCapabilitySource, name: str, required: Any
) -> str | None:
    actual = worker.capabilities.get(name)
    if isinstance(required, bool):
        return None if actual is required else f"capability_missing:{name}"
    if isinstance(required, str):
        available = _as_string_set(actual)
        if available is None or required.lower() not in available:
            return f"capability_missing:{name}"
        return None
    required_values = _as_string_set(required)
    if required_values is None:
        return f"invalid_capability_requirement:{name}"
    available = _as_string_set(actual)
    if available is None or not required_values.issubset(available):
        return f"capability_missing:{name}"
    return None


def _repository_write_mismatch(required: Any) -> str | None:
    if not isinstance(required, bool):
        return "invalid_capability_requirement:repository_write"
    return "repository_write_not_permitted" if required else None


def _network_policy_mismatch(
    worker: WorkerCapabilitySource, required: Any
) -> str | None:
    try:
        policy = NetworkPolicy(required)
    except (TypeError, ValueError):
        return "invalid_capability_requirement:network_policy"
    if policy == NetworkPolicy.DISABLED:
        return None
    if worker.network_policy_capability != NetworkPolicy.WORKER_RESTRICTED:
        return "network_policy_not_supported"
    return None


def _match_network_policy(
    worker: WorkerCapabilitySource,
    required: NetworkPolicy,
    reasons: list[str],
) -> None:
    if required == NetworkPolicy.DISABLED:
        return
    if worker.network_policy_capability != NetworkPolicy.WORKER_RESTRICTED:
        reasons.append("network_policy_not_supported")


def _as_string_set(value: Any) -> set[str] | None:
    if isinstance(value, str):
        return {value.lower()}
    if isinstance(value, (list, tuple, set)):
        if not all(isinstance(item, str) for item in value):
            return None
        return {item.lower() for item in value}
    return None


def _minimum_version(value: Any) -> str | None:
    if isinstance(value, Mapping):
        minimum = value.get("minimum")
        return minimum if isinstance(minimum, str) else None
    if isinstance(value, str):
        return value
    return None


def _at_least(actual: str | None, minimum: str) -> bool:
    if actual is None:
        return False
    actual_match = _VERSION_PATTERN.match(actual)
    minimum_match = _VERSION_PATTERN.match(minimum)
    if actual_match is None or minimum_match is None:
        return False
    actual_parts = tuple(int(part or 0) for part in actual_match.groups())
    minimum_parts = tuple(int(part or 0) for part in minimum_match.groups())
    return actual_parts >= minimum_parts
